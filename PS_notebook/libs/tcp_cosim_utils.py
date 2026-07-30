"""Generic multi-output TCP utilities for Simulink co-simulation."""

from __future__ import annotations

import errno
import queue
import select
import socket
import struct
import threading
import time
from collections.abc import Callable, MutableMapping, Sequence
from typing import Any


Number = int | float
SampleProcessor = Callable[[Number], Number]


def identity(value: Number) -> Number:
    return value


_DATA_TYPES = {
    "int8": ("int8", "b", -128, 127),
    "uint8": ("uint8", "B", 0, 255),
    "int16": ("int16", "h", -32768, 32767),
    "uint16": ("uint16", "H", 0, 65535),
    "int32": ("int32", "i", -2147483648, 2147483647),
    "uint32": ("uint32", "I", 0, 4294967295),
    "single": ("single", "f", None, None),
    "float32": ("single", "f", None, None),
    "double": ("double", "d", None, None),
    "float64": ("double", "d", None, None),
}


class SampleCodec:
    """Encode/decode one fixed-size, little-endian numeric frame."""

    def __init__(
        self,
        data_type: str,
        batch_size: int,
        overflow: str = "wrap",
    ) -> None:
        type_key = data_type.lower()
        if type_key not in _DATA_TYPES:
            supported = ", ".join(sorted(_DATA_TYPES))
            raise ValueError(
                f"Unsupported data_type {data_type!r}; choose from {supported}"
            )
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if overflow not in {"wrap", "saturate", "error"}:
            raise ValueError("overflow must be 'wrap', 'saturate', or 'error'")

        canonical, format_code, minimum, maximum = _DATA_TYPES[type_key]
        self.data_type = canonical
        self.batch_size = batch_size
        self.overflow = overflow
        self.minimum = minimum
        self.maximum = maximum
        self.struct = struct.Struct(f"<{batch_size}{format_code}")
        self.frame_bytes = self.struct.size

    def decode(self, payload: bytes) -> tuple[Number, ...]:
        return self.struct.unpack(payload)

    def _cast_integer(self, value: Number) -> int:
        integer = int(value)
        assert self.minimum is not None and self.maximum is not None
        if self.minimum <= integer <= self.maximum:
            return integer
        if self.overflow == "error":
            raise OverflowError(
                f"{integer} is outside {self.data_type} range "
                f"[{self.minimum}, {self.maximum}]"
            )
        if self.overflow == "saturate":
            return min(max(integer, self.minimum), self.maximum)
        width = self.maximum - self.minimum + 1
        return (integer - self.minimum) % width + self.minimum

    def encode(self, values: Sequence[Number]) -> bytes:
        if len(values) != self.batch_size:
            raise ValueError(
                f"Expected {self.batch_size} values, received {len(values)}"
            )
        if self.minimum is None:
            cast_values = [float(value) for value in values]
        else:
            cast_values = [self._cast_integer(value) for value in values]
        return self.struct.pack(*cast_values)


def _peer_closed(connection: socket.socket) -> bool:
    try:
        readable, _, _ = select.select([connection], [], [], 0)
        return bool(readable) and connection.recv(
            1,
            socket.MSG_PEEK,
        ) == b""
    except (ConnectionResetError, OSError):
        return True


class OutputChannel:
    """Generic result port bound to one replaceable sample processor."""

    def __init__(
        self,
        *,
        name: str,
        host: str,
        output_port: int,
        process_function: SampleProcessor,
        data_type: str,
        batch_size: int,
        overflow: str,
        stop_event: threading.Event,
    ) -> None:
        if not name:
            raise ValueError("Output channel name cannot be empty")
        if not callable(process_function):
            raise TypeError(f"Processor for channel {name!r} must be callable")
        self.name = name
        self.host = host
        self.output_port = output_port
        self.codec = SampleCodec(data_type, batch_size, overflow)
        self.stop_event = stop_event
        self.results: queue.Queue[bytes] = queue.Queue(maxsize=1)
        self._process_function = process_function
        self._process_lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._connection: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def set_process_function(
        self,
        process_function: SampleProcessor,
    ) -> None:
        if not callable(process_function):
            raise TypeError("process_function must be callable")
        with self._process_lock:
            self._process_function = process_function

    def process(self, input_values: Sequence[Number]) -> bytes:
        with self._process_lock:
            process_function = self._process_function
        output_values = [process_function(value) for value in input_values]
        return self.codec.encode(output_values)

    def publish(self, input_values: Sequence[Number]) -> None:
        payload = self.process(input_values)
        try:
            self.results.put_nowait(payload)
        except queue.Full:
            try:
                self.results.get_nowait()
            except queue.Empty:
                pass
            self.results.put_nowait(payload)

    def clear(self) -> None:
        while True:
            try:
                self.results.get_nowait()
            except queue.Empty:
                return

    def _serve(self) -> None:
        assert self._listener is not None
        print(
            f"Output channel {self.name!r} listening on port",
            self.output_port,
        )
        normal_disconnects = {
            errno.ECONNRESET,
            errno.EPIPE,
            errno.ENOTCONN,
            errno.ECONNABORTED,
        }
        while not self.stop_event.is_set():
            connection = None
            try:
                connection, address = self._listener.accept()
                connection.setsockopt(
                    socket.IPPROTO_TCP,
                    socket.TCP_NODELAY,
                    1,
                )
                self._connection = connection
                print(
                    f"Simulink Receive [{self.name}] connected from",
                    address,
                )
                while not self.stop_event.is_set():
                    if _peer_closed(connection):
                        break
                    try:
                        payload = self.results.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if _peer_closed(connection):
                        try:
                            self.results.put_nowait(payload)
                        except queue.Full:
                            pass
                        break
                    connection.sendall(payload)
            except socket.timeout:
                continue
            except OSError as error:
                if (
                    not self.stop_event.is_set()
                    and error.errno not in normal_disconnects
                ):
                    print(f"Output channel {self.name!r} error:", error)
            finally:
                self._connection = None
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.settimeout(1.0)
        try:
            listener.bind((self.host, self.output_port))
            listener.listen(5)
        except Exception:
            listener.close()
            raise
        self._listener = listener
        self._thread = threading.Thread(
            target=self._serve,
            daemon=True,
            name=f"cosim-output-{self.name}",
        )
        self._thread.start()

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        if self._connection is not None:
            try:
                self._connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._connection.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._listener = None
        self._connection = None
        self._thread = None


class CoSimulationServer:
    """One generic input stream and one generic processed-result stream."""

    def __init__(
        self,
        process_function: SampleProcessor = identity,
        host: str = "0.0.0.0",
        input_port: int = 5000,
        output_port: int = 5001,
        data_type: str = "single",
        batch_size: int = 1,
        overflow: str = "wrap",
    ) -> None:
        self.host = host
        self.input_port = input_port
        self.input_codec = SampleCodec(data_type, batch_size, overflow)
        self.data_type = self.input_codec.data_type
        self.batch_size = batch_size
        self.stop_event = threading.Event()
        self._input_listener: socket.socket | None = None
        self._input_connection: socket.socket | None = None
        self._input_thread: threading.Thread | None = None

        if output_port == input_port:
            raise ValueError("input_port and output_port must be different")
        self.output_channel = OutputChannel(
            name="result",
            host=host,
            output_port=output_port,
            process_function=process_function,
            data_type=data_type,
            batch_size=batch_size,
            overflow=overflow,
            stop_event=self.stop_event,
        )

    def set_process_function(
        self,
        process_function: SampleProcessor,
    ) -> None:
        self.output_channel.set_process_function(process_function)

    def _input_server(self) -> None:
        assert self._input_listener is not None
        print("Input server listening on port", self.input_port)
        while not self.stop_event.is_set():
            connection = None
            try:
                connection, address = self._input_listener.accept()
                connection.setsockopt(
                    socket.IPPROTO_TCP,
                    socket.TCP_NODELAY,
                    1,
                )
                connection.settimeout(1.0)
                self._input_connection = connection
                print("Simulink Send connected from", address)
                self.output_channel.clear()

                receive_buffer = bytearray()
                while not self.stop_event.is_set():
                    try:
                        raw_data = connection.recv(4096)
                    except socket.timeout:
                        continue
                    if not raw_data:
                        break
                    receive_buffer.extend(raw_data)
                    frame_size = self.input_codec.frame_bytes
                    while len(receive_buffer) >= frame_size:
                        raw_frame = bytes(receive_buffer[:frame_size])
                        del receive_buffer[:frame_size]
                        input_values = self.input_codec.decode(raw_frame)
                        self.output_channel.publish(input_values)
            except socket.timeout:
                continue
            except OSError as error:
                if not self.stop_event.is_set() and error.errno not in {
                    errno.ECONNRESET,
                    errno.EPIPE,
                    errno.ENOTCONN,
                    errno.ECONNABORTED,
                }:
                    print("Input socket error:", error)
            except Exception as error:
                if not self.stop_event.is_set():
                    print("Processing error:", error)
            finally:
                self._input_connection = None
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass

    def start(self) -> "CoSimulationServer":
        try:
            self.output_channel.start()
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.settimeout(1.0)
            listener.bind((self.host, self.input_port))
            listener.listen(5)
            self._input_listener = listener
        except Exception:
            self.output_channel.stop()
            raise

        self._input_thread = threading.Thread(
            target=self._input_server,
            daemon=True,
            name="cosim-input",
        )
        self._input_thread.start()
        return self

    def stop(self) -> None:
        self.stop_event.set()
        if self._input_listener is not None:
            try:
                self._input_listener.close()
            except OSError:
                pass
        if self._input_connection is not None:
            try:
                self._input_connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._input_connection.close()
            except OSError:
                pass
        self.output_channel.stop()
        if self._input_thread is not None:
            self._input_thread.join(timeout=2.0)
        self._input_listener = None
        self._input_connection = None
        self._input_thread = None


def _release_legacy_notebook_server(
    namespace: MutableMapping[str, Any],
    input_port: int,
    output_ports: Sequence[int],
) -> None:
    legacy_threads = [
        namespace.get("input_thread"),
        namespace.get("output_thread"),
    ]
    if not any(
        isinstance(thread, threading.Thread) and thread.is_alive()
        for thread in legacy_threads
    ):
        return
    namespace["running"] = False
    for port in (input_port, *output_ports):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                pass
        except OSError:
            pass
    for thread in legacy_threads:
        if isinstance(thread, threading.Thread):
            thread.join(timeout=2.0)


def initialize_server(
    process_function: SampleProcessor = identity,
    *,
    namespace: MutableMapping[str, Any] | None = None,
    host: str = "0.0.0.0",
    input_port: int = 5000,
    output_port: int = 5001,
    data_type: str = "single",
    batch_size: int = 1,
    overflow: str = "wrap",
    namespace_key: str = "cosim_server",
) -> CoSimulationServer:
    """Initialize one reusable input/process/output server instance."""
    if namespace is not None:
        previous_server = namespace.get(namespace_key)
        if previous_server is not None and hasattr(previous_server, "stop"):
            previous_server.stop()
        # Migration cleanup for earlier notebook layouts.
        if namespace_key == "main_server":
            old_server = namespace.get("cosim_server")
            if (
                old_server is not None
                and old_server is not previous_server
                and hasattr(old_server, "stop")
            ):
                old_server.stop()
        if namespace_key == "fft_server":
            old_analyzer = namespace.get("fft_analyzer")
            if old_analyzer is not None and hasattr(old_analyzer, "stop"):
                old_analyzer.stop()
        _release_legacy_notebook_server(
            namespace,
            input_port,
            [output_port],
        )

    time.sleep(0.1)
    server = CoSimulationServer(
        process_function=process_function,
        host=host,
        input_port=input_port,
        output_port=output_port,
        data_type=data_type,
        batch_size=batch_size,
        overflow=overflow,
    ).start()
    print("Co-simulation server configured")
    print(
        f"Input: port={input_port}, type={server.data_type}, "
        f"batch={batch_size}, bytes={server.input_codec.frame_bytes}"
    )
    channel = server.output_channel
    print(
        f"Output: port={channel.output_port}, "
        f"type={channel.codec.data_type}"
    )
    return server
