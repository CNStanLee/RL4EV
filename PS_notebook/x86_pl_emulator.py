"""x86 stand-in for the ZCU104 PS + PL of the MPCC_R overlay (HIL plan stage H0).

    python x86_pl_emulator.py [--host 0.0.0.0] [--no-mpcc] [--no-det] [--no-est]

Serves the three TCP pairs the Simulink HIL blocks use, with the same frame formats as the board:
  5010 -> 5011  mpcc_r   : 14 singles (MPCC inputs) or 18 (+ flags, amp_iac, mask, t_ramp)  -> 1 single (D)
  5020 -> 5021  detector : 2400 singles (200 x 12 cycle buffer, row-major)                  -> 21 singles
                           [5 logits, 10 zeros, 5 amplitudes (0 unless flagged), flags word]
  5030 -> 5031  estimator: 80 singles (raw current window, amperes)                          -> 8 singles (enc)
The mpcc_r path runs the float reference of mpcc_r_hls (bit-identical to the IP when flags = 0), the detector path
runs features.cycle_features_v3 + the bit-exact v5 ONNX + the IP's persistence / hysteresis rule, the estimator path
CycleNorm + the v2 ONNX.  So a Simulink run against this emulator must reproduce the SIL numbers; differences that
appear only on the board are then attributable to the board.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE / "libs"))
sys.path.insert(0, str(REPO / "EMI_DET_FPGA" / "src"))
from tcp_cosim_utils import initialize_server  # noqa: E402

DET_COLS = ["Vdc_int", "Vac_int", "Iac_int", "Iref", "theta_pll", "D", "Vref", "Vbat_int", "Ibat_int", "D_dcdc", "state", "Iref_bat"]


# ---------------------------------------------------------------- mpcc_r reference (port of HLS_PRJ/mpcc_r/mpcc_r_hls.cpp)
class MpccR:
    def __init__(self):
        self.theta_prev = 0.0; self.init = False
        self.g_vac = 0.0; self.g_iac = 0.0; self.pkp = 0.0; self.pkn = 0.0; self.V_amp = 0.0; self.th_prev = 0.0
        self.held = [0.0] * 6; self.holding = False
        self.n = 0; self.t0 = time.perf_counter()

    def core(self, i_L, i_ref, V_in, Ts, L_in, V_o, th, A3, A5, A7, p3, p5, p7, use_h):
        f = np.float32
        if not self.init:
            self.theta_prev = th; self.init = True
        L = max(L_in, 1e-9); Ts = max(Ts, 1e-9); Vo = max(abs(V_o), 1.0)
        ui = abs(i_L); ui_safe = max(ui, 1e-6)
        sgn = 1.0 if V_in > 0 else -1.0
        iref_s = f(sgn * abs(i_ref))
        plant_gain = f(sgn * L / (Vo * Ts))
        D_ff = f(1.0 - abs(V_in) / Vo)
        if use_h:
            d = th - self.theta_prev; d = math.atan2(math.sin(d), math.cos(d)); self.theta_prev = th
            thc = th + d / Ts * Ts
            ih = f(abs(A3) * math.sin(3 * thc + p3)) + f(1.08 * abs(A5) * math.sin(5 * thc + p5)) + f(abs(A7) * math.sin(7 * thc + p7))
            iref_s = f(iref_s - ih)
        ierr = f(iref_s - i_L)
        return float(f(D_ff + f(plant_gain * f(0.35) * ierr) + f(-sgn * 0.015 * (i_L - iref_s) / ui_safe)))

    def __call__(self, frame):
        v = [float(x) for x in frame]
        if len(v) not in (14, 18):
            raise ValueError(f"mpcc_r frame must have 14 or 18 values, got {len(v)}")
        i_L, i_ref, V_in, Ts, L, Vo, th, A3, A5, A7, p3, p5, p7, use_h = v[:14]
        flags, amp_iac, mask, t_ramp = (int(round(v[14])), v[15], int(round(v[16])), v[17]) if len(v) == 18 else (0, 0.0, 511, 0.06)
        f_vac = bool(flags & 2); f_iac = bool(flags & 4)
        m_vac, m_iac, m_hold, m_ramp = bool(mask & 4), bool(mask & 8), bool(mask & 16), bool(mask & 128)
        Ts_eff = max(Ts, 1e-9); dg = Ts_eff / max(t_ramp, Ts_eff)
        self.g_vac = 1.0 if f_vac else ((self.g_vac - dg if self.g_vac > dg else 0.0) if m_ramp else 0.0)
        self.g_iac = 1.0 if f_iac else ((self.g_iac - dg if self.g_iac > dg else 0.0) if m_ramp else 0.0)
        if th < self.th_prev - 3.0:
            self.V_amp = 0.5 * (self.pkp - self.pkn); self.pkp = 0.0; self.pkn = 0.0
        self.th_prev = th; self.pkp = max(self.pkp, V_in); self.pkn = min(self.pkn, V_in)
        V_used = V_in
        if m_vac and self.g_vac > 0 and self.V_amp > 50.0:
            V_used = V_in + self.g_vac * (self.V_amp * math.sin(th) - V_in)
        i_used = i_L - self.g_iac * amp_iac * 20.0 if m_iac else i_L
        hold = m_hold and self.g_iac > 0
        if not hold:
            self.held = [A3, A5, A7, p3, p5, p7]
        uA3, uA5, uA7, up3, up5, up7 = self.held if hold else (A3, A5, A7, p3, p5, p7)
        self.n += 1
        return [self.core(i_used, i_ref, V_used, Ts, L, Vo, th, uA3, uA5, uA7, up3, up5, up7, bool(round(use_h)))]


# ---------------------------------------------------------------- detector path: features + ONNX + IP decision rule
class Detector:
    def __init__(self):
        import onnxruntime as ort
        import pandas as pd
        from emi_det.features import cycle_features_v3, vref_series
        self.pd = pd; self.feat = cycle_features_v3; self.vref = vref_series
        cfg = json.load(open(REPO / "EMI_DET_FPGA/artifacts/detector.json"))
        self.names = cfg["features"]; self.mu = np.array(cfg["mu"], np.float32)
        thr = np.array(cfg["thr"]); self.lthr = np.log(thr / (1 - thr)); self.lclr = np.log((cfg.get("hyst", 0.6) * thr) / (1 - cfg.get("hyst", 0.6) * thr))
        self.persist = int(cfg.get("persist", 2))
        self.sess = ort.InferenceSession(str(REPO / "EMI_DET_FPGA/artifacts/detector_bitexact.onnx"), providers=["CPUExecutionProvider"])
        self.cnt = np.zeros(5, int); self.on = np.zeros(5, bool); self.first = True; self.n = 0

    def __call__(self, frame):
        v = np.asarray(frame, np.float32)
        if v.size != 2400:
            raise ValueError(f"detector frame must have 2400 values, got {v.size}")
        X = v.reshape(200, 12)
        df = self.pd.DataFrame(X, columns=DET_COLS); df["t"] = 0.6 + np.arange(200) / 1e4
        cf = self.feat(df, df["Vref"].to_numpy())
        x = cf.X[0].astype(np.float32); x = np.where(np.isfinite(x), x, self.mu)
        # cycle-to-cycle delta features (d_*): the feature function is stateless per call, keep the previous cycle here
        if self.first:
            self.prev_row = x[:36].copy(); self.first = False
        x[36:43] = [x[15] - self.prev_row[15], x[18] - self.prev_row[18], x[4] - self.prev_row[4], x[3] - self.prev_row[3],
                    x[24] - self.prev_row[24], x[25] - self.prev_row[25], x[33] - self.prev_row[33]]
        self.prev_row = x[:36].copy()
        out = self.sess.run(None, {"features": x[None, :]})
        logit = np.asarray(out[0], np.float32)[0]; amp = np.asarray(out[2], np.float32)[0]
        above = logit >= self.lthr; below = logit < self.lclr
        self.cnt = np.where(above, self.cnt + 1, 0); self.on = np.where(self.on, ~below, self.cnt >= self.persist)
        flags = int(sum(1 << k for k in range(5) if self.on[k]))
        self.n += 1
        return list(map(float, logit)) + [0.0] * 10 + [float(a) if o else 0.0 for a, o in zip(amp, self.on)] + [float(flags)]


# ---------------------------------------------------------------- estimator path: CycleNorm + ONNX
class Estimator:
    def __init__(self):
        import onnxruntime as ort
        p = REPO / "FFT_HGQ_BLS_FPGA/artifacts/harmonic_residual_bls_simulink.onnx"
        self.sess = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"]); self.inp = self.sess.get_inputs()[0]
        self.n = 0

    def __call__(self, frame):
        w = np.asarray(frame, np.float32)
        if w.size != 80:
            raise ValueError(f"estimator frame must have 80 values, got {w.size}")
        A = max(float(np.max(np.abs(w))), 1e-6)
        x = (w / A).astype(np.float32)
        x = x.reshape(1, 80, 1) if len(self.inp.shape) == 3 else x.reshape(1, 80)
        enc = np.asarray(self.sess.run(None, {self.inp.name: x})[0], np.float32).reshape(-1)[:8]
        self.n += 1
        return list(map(float, enc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--no-mpcc", action="store_true"); ap.add_argument("--no-det", action="store_true"); ap.add_argument("--no-est", action="store_true")
    a = ap.parse_args()
    servers = {}; procs = {}
    if not a.no_mpcc:
        procs["mpcc"] = MpccR()
        servers["mpcc"] = initialize_server(procs["mpcc"], host=a.host, input_port=5010, output_port=5011, data_type="single",
                                            batch_size=18, output_batch_size=1, processing_mode="frame", namespace_key="mpcc")
    if not a.no_det:
        procs["det"] = Detector()
        servers["det"] = initialize_server(procs["det"], host=a.host, input_port=5020, output_port=5021, data_type="single",
                                           batch_size=2400, output_batch_size=21, processing_mode="frame", namespace_key="det")
    if not a.no_est:
        procs["est"] = Estimator()
        servers["est"] = initialize_server(procs["est"], host=a.host, input_port=5030, output_port=5031, data_type="single",
                                           batch_size=80, output_batch_size=8, processing_mode="frame", namespace_key="est")
    print("x86 PL emulator up:", ", ".join(f"{k} ({v.__class__.__name__})" for k, v in procs.items()), "- Ctrl-C to stop")
    try:
        while True:
            time.sleep(10)
            print("frames:", {k: p.n for k, p in procs.items()})
    except KeyboardInterrupt:
        pass
    for s in servers.values():
        s.stop()


if __name__ == "__main__":
    main()
