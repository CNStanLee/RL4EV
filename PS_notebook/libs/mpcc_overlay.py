"""PYNQ driver for the AXI-Lite MPCC HLS accelerator."""

from __future__ import annotations

import struct
import threading
import time
from collections.abc import Sequence
from pathlib import Path


INPUT_NAMES = (
    "i_L",
    "i_ref",
    "V_in",
    "Ts",
    "L_in",
    "V_o",
    "theta_pll",
    "A3",
    "A5",
    "A7",
    "phi3",
    "phi5",
    "phi7",
    "use_harmonic",
)

FLOAT_REGISTERS = (
    0x10,
    0x18,
    0x20,
    0x28,
    0x30,
    0x38,
    0x40,
    0x48,
    0x50,
    0x58,
    0x60,
    0x68,
    0x70,
)

AP_CTRL = 0x00
USE_HARMONIC_REGISTER = 0x78
D_REGISTER = 0x80


def _float_to_u32(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def _u32_to_float(value: int) -> float:
    return struct.unpack("<f", struct.pack("<I", value))[0]


def load_mpcc_overlay(bit_path: str | Path, hwh_path: str | Path):
    """Load a matching .bit/.hwh pair and return the overlay and MPCC IP."""
    from pynq import Overlay

    bit_path = Path(bit_path).resolve()
    hwh_path = Path(hwh_path).resolve()
    if not bit_path.is_file():
        raise FileNotFoundError(bit_path)
    if not hwh_path.is_file():
        raise FileNotFoundError(hwh_path)
    if bit_path.stem != hwh_path.stem:
        raise ValueError("The .bit and .hwh files must have the same stem")

    overlay = Overlay(str(bit_path), download=True)
    if "mpcc_hls_0" not in overlay.ip_dict:
        raise RuntimeError(
            f"mpcc_hls_0 is missing from HWH: {list(overlay.ip_dict)}"
        )
    return overlay, overlay.mpcc_hls_0


class MPCCOverlayPredictor:
    """Execute one 14-input MPCC prediction through AXI-Lite."""

    def __init__(self, ip, timeout_seconds: float = 0.1) -> None:
        self.mmio = ip.mmio
        self.timeout_seconds = timeout_seconds
        self.lock = threading.Lock()
        self.call_count = 0
        self.total_hardware_seconds = 0.0

    def predict(self, frame: Sequence[float]) -> float:
        if len(frame) != len(INPUT_NAMES):
            raise ValueError(
                f"Expected {len(INPUT_NAMES)} inputs, received {len(frame)}"
            )

        started = time.perf_counter()
        with self.lock:
            for offset, value in zip(FLOAT_REGISTERS, frame[:13]):
                self.mmio.write(offset, _float_to_u32(value))
            self.mmio.write(
                USE_HARMONIC_REGISTER,
                int(bool(round(float(frame[13])))),
            )
            self.mmio.write(AP_CTRL, 0x01)

            deadline = time.perf_counter() + self.timeout_seconds
            while True:
                if self.mmio.read(AP_CTRL) & 0x02:
                    break
                if time.perf_counter() >= deadline:
                    raise TimeoutError("Timed out waiting for mpcc_hls_0 ap_done")

            prediction = _u32_to_float(self.mmio.read(D_REGISTER))

        self.call_count += 1
        self.total_hardware_seconds += time.perf_counter() - started
        return prediction

    @property
    def average_hardware_us(self) -> float:
        if self.call_count == 0:
            return 0.0
        return 1e6 * self.total_hardware_seconds / self.call_count
