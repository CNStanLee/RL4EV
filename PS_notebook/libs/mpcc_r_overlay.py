"""PYNQ driver for the MPCC_R overlay (Vivado_PRJ/MPCC_R): the four AXI-Lite HLS IPs of the
resilient controller chain.

    from mpcc_r_overlay import MpccROverlay
    ov = MpccROverlay("hardware/mpcc_r.bit")          # .hwh next to it
    feat = ov.features(buf, reset=True)              # 200 x 12 cycle buffer -> 48 features (emi_feat_hls)
    logit, amp, flags = ov.detect(feat)              # emi_detector_axi (persistence + hysteresis inside the IP)
    enc, peak, legacy = ov.estimate(wave80)          # harmonic_estimator_axi
    D = ov.mpcc_r(frame14, flags, amp[2], mask)      # mpcc_r_hls: the 14 MPCC inputs + detector state

Register offsets are taken from the .hwh (`overlay.ip_dict[ip]["registers"]`, PYNQ 3.0.1 verified on the
ZCU104 2026-09-05), so the driver does not depend on the HLS-generated address layout.  Arrays (feat[48], buf[2400], wave[80], ...) are written / read as
consecutive 32-bit words starting at the register's offset (the AXI-Lite array mapping of Vitis HLS).
Latency counters: every call records the ap_start -> ap_done wall time (PS side, includes the AXI
polling) in `timing[name]` (count, total_s, max_s); `ov.report()` prints them.
"""
from __future__ import annotations

import struct
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

AP_CTRL = 0x00
FLAG_NAMES = ("Vdc", "Vac", "Iac", "Vbat", "Ibat")
MPCC_INPUTS = ("i_L", "i_ref", "V_in", "Ts", "L_in", "V_o", "theta_pll", "A3", "A5", "A7", "phi3", "phi5", "phi7", "use_harmonic")


def _f2u(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(v)))[0]


def _u2f(u: int) -> float:
    return struct.unpack("<f", struct.pack("<I", u & 0xFFFFFFFF))[0]


ORDER_SCALE = np.array([1.0, 0.25, 0.20, 0.15], np.float32)


def decode_legacy(enc: np.ndarray, peak: float) -> np.ndarray:
    """[c1,s1,c3,s3,c5,s5,c7,s7], window peak -> [A1,A3,A5,A7,delta3,delta5,delta7] as harmonic_postprocess8_block (ema_alpha = 1)."""
    z = np.asarray(enc, np.float32).reshape(4, 2)
    amp = peak * ORDER_SCALE * np.hypot(z[:, 0], z[:, 1])
    ph = np.arctan2(z[:, 1], z[:, 0])
    rel = ph[1:] - np.array([3.0, 5.0, 7.0]) * ph[0]
    rel = np.arctan2(np.sin(rel), np.cos(rel))
    return np.concatenate([amp, rel]).astype(np.float32)


class _Ip:
    """One AXI-Lite HLS IP: named registers from the hwh, blocking start/done."""

    def __init__(self, ip, name: str, timing: dict, timeout_s: float = 0.05, description: dict | None = None):
        self.ip = ip; self.mmio = ip.mmio; self.name = name; self.timeout_s = timeout_s
        # PYNQ 3.x: the hwh register description lives in overlay.ip_dict[<ip>]["registers"]; array arguments of a
        # Vitis HLS AXI-Lite interface are listed as "Memory_<arg>" (or "Memory_<arg>_r" when the name clashes).
        desc = description if description is not None else getattr(ip, "description", {})
        self.regs = {k: int(v["address_offset"]) for k, v in desc.get("registers", {}).items()}
        try:
            self.words = self.mmio.array          # uint32 view of the register space (element access only, see write_f)
        except Exception:
            self.words = None
        self.timing = timing.setdefault(name, dict(count=0, total_s=0.0, max_s=0.0, last_s=0.0))

    def off(self, reg: str) -> int:
        for cand in (reg, f"Memory_{reg}", f"Memory_{reg}_r", f"{reg}_r"):
            if cand in self.regs:
                return self.regs[cand]
        raise KeyError(f"{self.name}: register {reg!r} not in {sorted(self.regs)}")

    def write_f(self, reg: str, values: Sequence[float]) -> None:
        # One aligned 32-bit store per word.  A numpy slice copy (memcpy) uses overlapping / unaligned 16-byte
        # accesses on AArch64, which raise SIGBUS on the AXI-Lite (device memory) window.
        base = self.off(reg) // 4
        arr = np.ascontiguousarray(np.asarray(values, np.float32)).view(np.uint32).tolist()
        w = self.words
        if w is not None:
            for i, u in enumerate(arr):
                w[base + i] = u
        else:
            for i, u in enumerate(arr):
                self.mmio.write(4 * (base + i), int(u))

    def write_u(self, reg: str, value: int) -> None:
        self.mmio.write(self.off(reg), int(value) & 0xFFFFFFFF)

    def read_f(self, reg: str, n: int) -> np.ndarray:
        base = self.off(reg) // 4
        w = self.words
        if w is not None:
            return np.array([w[base + i] for i in range(n)], np.uint32).view(np.float32)
        return np.array([_u2f(self.mmio.read(4 * (base + i))) for i in range(n)], np.float32)

    def read_u(self, reg: str) -> int:
        return self.mmio.read(self.off(reg))

    def run(self) -> None:
        t0 = time.perf_counter()
        self.mmio.write(AP_CTRL, 0x01)
        deadline = t0 + self.timeout_s
        while not (self.mmio.read(AP_CTRL) & 0x02):
            if time.perf_counter() > deadline:
                raise TimeoutError(f"{self.name}: ap_done timeout")
        dt = time.perf_counter() - t0
        self.timing["count"] += 1; self.timing["total_s"] += dt; self.timing["max_s"] = max(self.timing["max_s"], dt); self.timing["last_s"] = dt


class MpccROverlay:
    def __init__(self, bit_path: str | Path):
        from pynq import Overlay

        bit_path = Path(bit_path).resolve()
        self.overlay = Overlay(str(bit_path), download=True)
        self.timing: dict = {}
        ipd = self.overlay.ip_dict
        def get(prefix):
            for k in ipd:
                if k.startswith(prefix):
                    return _Ip(getattr(self.overlay, k), prefix, self.timing, description=ipd[k])
            raise RuntimeError(f"{prefix}* missing from the overlay: {list(ipd)}")
        self.mpcc = get("mpcc_r_hls")
        self.feat = get("emi_feat_hls")
        self.det = get("emi_detector_axi")
        self.est = get("harmonic_estimator_axi")

    # ---- emi_feat_hls(buf[2400], reset, feat[48])
    def features(self, buf: np.ndarray, reset: bool = False) -> np.ndarray:
        b = np.asarray(buf, np.float32).reshape(-1)
        if b.size != 2400:
            raise ValueError("buf must be 200 x 12")
        self.feat.write_f("buf", b); self.feat.write_u("reset", 1 if reset else 0); self.feat.run()
        return self.feat.read_f("feat", 48)

    # ---- emi_detector_axi(feat[48], logit[5], amp[5], flags, reset)
    def detect(self, feat: np.ndarray, reset: bool = False) -> tuple[np.ndarray, np.ndarray, int]:
        self.det.write_f("feat", np.asarray(feat, np.float32)); self.det.write_u("reset", 1 if reset else 0); self.det.run()
        return self.det.read_f("logit", 5), self.det.read_f("amp", 5), self.det.read_u("flags")

    # ---- harmonic_estimator_axi(wave[80], enc[8], peak)
    def estimate(self, wave: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
        self.est.write_f("wave", np.asarray(wave, np.float32)); self.est.run()
        enc = self.est.read_f("enc", 8); peak = float(self.est.read_f("peak", 1)[0])
        return enc, peak, decode_legacy(enc, peak)

    # ---- mpcc_r_hls(14 MPCC inputs, flags, amp_iac, mask, t_ramp) -> D, dbg[6]
    def mpcc_r(self, frame: Sequence[float], flags: int = 0, amp_iac: float = 0.0, mask: int = 511, t_ramp: float = 0.06) -> tuple[float, np.ndarray]:
        if len(frame) != 14:
            raise ValueError("frame must hold the 14 MPCC inputs")
        for name, v in zip(MPCC_INPUTS[:13], frame[:13]):
            self.mpcc.write_f(name, [v])
        self.mpcc.write_u("use_harmonic", 1 if round(float(frame[13])) else 0)
        self.mpcc.write_u("flags", flags); self.mpcc.write_f("amp_iac", [amp_iac]); self.mpcc.write_u("mask", mask); self.mpcc.write_f("t_ramp", [t_ramp])
        self.mpcc.run()
        return float(self.mpcc.read_f("D", 1)[0]), self.mpcc.read_f("dbg", 6)

    def reset_pl(self) -> None:
        """Reload the bitstream: clears the static state of every IP (mpcc_r ramp gains / peak tracker / held phasors,
        detector persistence counters).  Used between Simulink runs by ps_server_mpcc_r.py."""
        self.overlay.download()

    def report(self) -> str:
        lines = [f"{'IP':24s} {'calls':>7s} {'mean us':>9s} {'max us':>9s}"]
        for k, v in self.timing.items():
            lines.append(f"{k:24s} {v['count']:7d} {1e6 * v['total_s'] / max(v['count'], 1):9.1f} {1e6 * v['max_s']:9.1f}")
        return "\n".join(lines)


__all__ = ["MpccROverlay", "decode_legacy", "FLAG_NAMES", "MPCC_INPUTS"]
