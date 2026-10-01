"""ZCU104 PS server for the MPCC_R overlay: the three TCP paths used by the Simulink HIL blocks
(Simulation/PV_MEV/docs/HIL_TEST_PLAN.md, section 2; same frame formats as x86_pl_emulator.py).

    sudo bash -lc "python3 -u ps_server_mpcc_r.py [--bit hardware/mpcc_r.bit] [--no-mpcc] [--no-det] [--no-est] [--log ../logs]"

  5010 -> 5011  mpcc_r   : 14 or 18 singles (MPCC inputs [+ flags, amp_iac, mask, t_ramp]) -> 1 single (D)
  5020 -> 5021  detector : 2400 singles (200 x 12 cycle buffer, row-major) -> 21 singles
                           [5 logits, 10 zeros, 5 amplitudes (0 unless flagged, as the IP gives them), flags word]
  5030 -> 5031  estimator: 80 singles (raw current window) -> 8 singles (enc)
Every path listens on its two ports; Simulink's TCP/IP Send connects to the input port and TCP/IP Receive
to the output port.  One connection pair = one Simulink run: when the sender disconnects the bitstream is
reloaded (clears the static IP state) and the path waits for the next run.  Per frame the server logs
(<log>/<path>_<start time>.csv): frame index, arrival time, PL ap_start->ap_done time, PS service time
(AXI-Lite traffic + PL), gap since the previous frame, and the main outputs.
"""
from __future__ import annotations

import argparse
import select
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "libs"))
from mpcc_r_overlay import MpccROverlay  # noqa: E402

LOCK = threading.Lock()          # the paths share one AXI-Lite master; serialise the PL calls
ACTIVE = set()                   # paths currently inside a run (bitstream reload only when nobody else is running)


def recv_exact(conn: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


class Path_:
    def __init__(self, name, in_port, out_port, n_in, n_out, fn, log_dir, ov, ip_name):
        self.name, self.in_port, self.out_port, self.n_in, self.n_out, self.fn = name, in_port, out_port, n_in, n_out, fn
        self.log_dir = Path(log_dir); self.ov = ov; self.ip_name = ip_name
        self.n_in_alt = 14 if name == "mpcc" else None      # legacy 14-value MPCC frame
        self.frames = 0

    def listen(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port)); s.listen(4); return s

    def accept_pair(self, ls_in, ls_out):
        """Sender (input port) then receiver (output port).  A Simulink run that aborts during block setup leaves a
        sender without a receiver: drop it as soon as it closes instead of blocking the path forever."""
        while True:
            cin, ain = ls_in.accept(); cin.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            ls_out.settimeout(1.0)
            try:
                while True:
                    try:
                        cout, _ = ls_out.accept(); cout.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        return cin, cout, ain
                    except socket.timeout:
                        r, _, _ = select.select([cin], [], [], 0)
                        if r:
                            try:
                                peek = cin.recv(1, socket.MSG_PEEK)
                            except OSError:
                                peek = b""
                            if peek == b"":
                                print(f"[{self.name}] sender {ain[0]} left before its receiver connected, dropped", flush=True); cin.close(); break
            finally:
                ls_out.settimeout(None)

    def serve(self):
        ls_in, ls_out = self.listen(self.in_port), self.listen(self.out_port)
        print(f"[{self.name}] listening {self.in_port} -> {self.out_port}", flush=True)
        while True:
            cin, cout, ain = self.accept_pair(ls_in, ls_out)
            tag = time.strftime("%Y%m%d_%H%M%S"); self.log_dir.mkdir(parents=True, exist_ok=True)
            log = open(self.log_dir / f"{self.name}_{tag}.csv", "w")
            log.write("n,t_s,pl_us,ps_us,gap_us," + self.fn.log_header + "\n")
            print(f"[{self.name}] run started {tag} from {ain[0]}", flush=True)
            self.fn.start(); n = 0; t_prev = None; t_run0 = time.perf_counter(); ACTIVE.add(self.name)
            first = None
            try:
                while True:
                    raw = recv_exact(cin, 4 * (self.n_in_alt or self.n_in)) if first is None and self.n_in_alt else None
                    if raw is None:
                        raw = recv_exact(cin, 4 * self.n_in) if first is None else recv_exact(cin, 4 * first)
                        if raw is None:
                            break
                        first = first or self.n_in
                    else:
                        # mpcc: try to detect the 18-value frame by reading the 4 extra values with a short timeout
                        cin.settimeout(0.05)
                        try:
                            extra = recv_exact(cin, 4 * (self.n_in - self.n_in_alt)); raw = raw + (extra or b"")
                        except socket.timeout:
                            pass
                        cin.settimeout(None); first = len(raw) // 4
                    vals = np.frombuffer(raw, "<f4")
                    t_arr = time.perf_counter()
                    with LOCK:
                        out, extra_log = self.fn(vals)
                    t_done = time.perf_counter()
                    cout.sendall(np.asarray(out, "<f4").tobytes())
                    pl_us = 1e6 * self.ov.timing[self.ip_name]["last_s"]
                    log.write(f"{n},{t_arr - t_run0:.6f},{pl_us:.1f},{1e6 * (t_done - t_arr):.1f},{0 if t_prev is None else 1e6 * (t_arr - t_prev):.1f},{extra_log}\n")
                    t_prev = t_arr; n += 1
                    if n % 2000 == 0 or (self.name == "det" and n % 10 == 0):
                        log.flush()
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f"[{self.name}] connection error: {e}", flush=True)
            finally:
                log.close(); cin.close(); cout.close()
            self.frames += n; ACTIVE.discard(self.name)
            print(f"[{self.name}] run ended: {n} frames in {time.perf_counter() - t_run0:.1f} s (log {self.name}_{tag}.csv)", flush=True)
            if ACTIVE:
                print(f"[{self.name}] PL reset skipped, {sorted(ACTIVE)} still running (detector / feature IPs reset through their reset input; "
                      "mpcc_r static state decays within t_ramp)", flush=True)
            else:
                with LOCK:
                    self.ov.reset_pl()
                print(f"[{self.name}] PL reset (bitstream reloaded)", flush=True)


class MpccFn:
    log_header = "D,flags,g_vac,g_iac,V_amp,hold"

    def __init__(self, ov):
        self.ov = ov

    def start(self):
        pass

    def __call__(self, v):
        if v.size == 18:
            flags, amp_iac, mask, t_ramp = int(round(float(v[14]))), float(v[15]), int(round(float(v[16]))), float(v[17])
        else:
            flags, amp_iac, mask, t_ramp = 0, 0.0, 511, 0.06
        D, dbg = self.ov.mpcc_r(v[:14], flags=flags, amp_iac=amp_iac, mask=mask, t_ramp=t_ramp)
        return [D], f"{D:.7g},{flags},{dbg[0]:.3f},{dbg[1]:.3f},{dbg[2]:.1f},{int(dbg[3])}"


class DetFn:
    log_header = "flags,l1,l2,l3,l4,l5,a1,a2,a3,a4,a5,feat_pl_us"

    def __init__(self, ov):
        self.ov = ov; self.first = True

    def start(self):
        self.first = True

    def __call__(self, v):
        feat = self.ov.features(v, reset=self.first)
        feat_us = 1e6 * self.ov.timing["emi_feat_hls"]["last_s"]
        logit, amp, flags = self.ov.detect(feat, reset=self.first); self.first = False
        out = list(map(float, logit)) + [0.0] * 10 + list(map(float, amp)) + [float(flags)]
        return out, f"{flags}," + ",".join(f"{x:.4f}" for x in logit) + "," + ",".join(f"{x:.4f}" for x in amp) + f",{feat_us:.1f}"


class EstFn:
    log_header = "peak,e0,e1"

    def __init__(self, ov):
        self.ov = ov

    def start(self):
        pass

    def __call__(self, v):
        enc, peak, _legacy = self.ov.estimate(v)
        return list(map(float, enc)), f"{peak:.4f},{enc[0]:.4f},{enc[1]:.4f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bit", default=str(HERE / "hardware/mpcc_r.bit"))
    ap.add_argument("--log", default=str(HERE.parent / "logs"))
    ap.add_argument("--no-mpcc", action="store_true"); ap.add_argument("--no-det", action="store_true"); ap.add_argument("--no-est", action="store_true")
    a = ap.parse_args()
    ov = MpccROverlay(a.bit)
    paths = []
    if not a.no_mpcc:
        paths.append(Path_("mpcc", 5010, 5011, 18, 1, MpccFn(ov), a.log, ov, "mpcc_r_hls"))
    if not a.no_det:
        paths.append(Path_("det", 5020, 5021, 2400, 21, DetFn(ov), a.log, ov, "emi_detector_axi"))
    if not a.no_est:
        paths.append(Path_("est", 5030, 5031, 80, 8, EstFn(ov), a.log, ov, "harmonic_estimator_axi"))
    threads = [threading.Thread(target=p.serve, daemon=True) for p in paths]
    for t in threads:
        t.start()
    print("PS server up:", ", ".join(p.name for p in paths), flush=True)
    try:
        while True:
            time.sleep(30)
            print("frames total:", {p.name: p.frames for p in paths}, flush=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
