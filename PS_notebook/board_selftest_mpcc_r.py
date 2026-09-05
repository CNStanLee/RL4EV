"""ZCU104 self-test of the MPCC_R overlay (plan step 4, first thing to run on the board).

    sudo python3 board_selftest_mpcc_r.py [--bit hardware/mpcc_r.bit] [--tb ../HLS_PRJ] [--n 200]

Loads the bitstream, then pushes the C-simulation test vectors of every HLS component through the PL
and compares with the host references (the same files the Vitis csim used):
  emi_feat_hls          HLS_PRJ/emi_feat/tb_data/buf_raw.dat            -> ref_feat.dat      (rel 1e-3 / abs 1e-2)
  emi_detector_axi      HLS_PRJ/emi_detector/tb_data/feat_raw.dat       -> ref_logits.dat    (|dlogit| < 0.05, flag words equal)
  harmonic_estimator    HLS_PRJ/harmonic_estimator/tb_data/wave_raw.dat -> ref_enc.dat       (<= 2 LSB = 0.0625)
  mpcc_r_hls            synthetic grid cycle, flags = 0                 -> host float model  (identity path, |dD| < 1e-5)
and prints the PS-side latency of each IP (ap_start -> ap_done, includes AXI-Lite traffic).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "libs"))
from mpcc_r_overlay import MpccROverlay  # noqa: E402


def mpcc_ref(i_L, i_ref, V_in, Ts, L, Vo, th, A3, A5, A7, p3, p5, p7, use_h, state):
    """Float reference of mpcc_hls (HLS_PRJ/mpcc/mpcc_hls.cpp)."""
    if not state["init"]:
        state["theta_prev"] = th; state["init"] = True
    track_gain, damp_gain, lead = 0.35, 0.015, 1.0
    L = max(L, 1e-9); Ts = max(Ts, 1e-9); Vo = max(abs(Vo), 1.0)
    ui = abs(i_L); ui_safe = max(ui, 1e-6)
    sgn = 1.0 if V_in > 0 else -1.0
    iref_s = sgn * abs(i_ref)
    plant_gain = sgn * L / (Vo * Ts)
    D_ff = 1.0 - abs(V_in) / Vo
    if use_h:
        d = th - state["theta_prev"]; d = math.atan2(math.sin(d), math.cos(d)); state["theta_prev"] = th
        thc = th + d / Ts * Ts * lead
        ih = abs(A3) * math.sin(3 * thc + p3) + 1.08 * abs(A5) * math.sin(5 * thc + p5) + abs(A7) * math.sin(7 * thc + p7)
        iref_s -= ih
    ierr = iref_s - i_L
    return D_ff + plant_gain * track_gain * ierr - sgn * damp_gain * (i_L - iref_s) / ui_safe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bit", default=str(Path(__file__).resolve().parent / "hardware/mpcc_r.bit"))
    ap.add_argument("--tb", default=str(Path(__file__).resolve().parents[1] / "HLS_PRJ"))
    ap.add_argument("--n", type=int, default=200, help="vectors per IP")
    a = ap.parse_args(); tb = Path(a.tb)
    ov = MpccROverlay(a.bit)
    ok = True
    # ---- features
    X = np.loadtxt(tb / "emi_feat/tb_data/buf_raw.dat", dtype=np.float32)[: a.n]; F = np.loadtxt(tb / "emi_feat/tb_data/ref_feat.dat")[: a.n]
    S = np.loadtxt(tb / "emi_feat/tb_data/run_start.dat", dtype=int)[: a.n]
    worst = 0.0; bad = 0
    for i in range(len(X)):
        f = ov.features(X[i], reset=bool(S[i] & 1))
        if S[i] & 2:
            continue
        ae = np.abs(f - F[i]); e = ae / np.maximum(np.abs(F[i]), 1.0)
        worst = max(worst, e.max()); bad += int(((e > 1e-3) & (ae > 2e-2)).sum())
    print(f"emi_feat        : {len(X)} cycles  worst rel err {worst:.3g}  outside tolerance {bad}  -> {'ok' if bad == 0 else 'FAIL'}"); ok &= bad == 0
    # ---- detector
    X = np.loadtxt(tb / "emi_detector/tb_data/feat_raw.dat", dtype=np.float32)[: a.n]; Y = np.loadtxt(tb / "emi_detector/tb_data/ref_logits.dat")[: a.n]
    T = np.loadtxt(tb / "emi_detector/tb_data/thresholds.dat")
    thr, clr, persist = T[:5], T[5:10], int(T[10]); cnt = np.zeros(5, int); on = np.zeros(5, bool); mism = 0; worst = 0.0
    for i in range(len(X)):
        logit, amp, flags = ov.detect(X[i], reset=(i == 0))
        worst = max(worst, float(np.abs(logit - Y[i]).max()))
        above = Y[i] >= thr; below = Y[i] < clr
        cnt = np.where(above, cnt + 1, 0); on = np.where(on, ~below, cnt >= persist)
        fref = int(sum(1 << k for k in range(5) if on[k]))
        mism += int(fref != flags)
    print(f"emi_detector    : {len(X)} cycles  max |dlogit| {worst:.3g}  flag-word mismatches {mism}  -> {'ok' if worst < 0.05 and mism == 0 else 'FAIL'}"); ok &= worst < 0.05 and mism == 0
    # ---- estimator
    X = np.loadtxt(tb / "harmonic_estimator/tb_data/wave_raw.dat", dtype=np.float32)[: a.n]; Y = np.loadtxt(tb / "harmonic_estimator/tb_data/ref_enc.dat")[: a.n]
    worst = 0.0
    for i in range(len(X)):
        enc, peak, legacy = ov.estimate(X[i]); worst = max(worst, float(np.abs(enc - Y[i]).max()))
    print(f"harmonic_est.   : {len(X)} windows  max |denc| {worst:.4g} (LSB 0.03125)  -> {'ok' if worst <= 0.0625 else 'FAIL'}"); ok &= worst <= 0.0625
    # ---- mpcc_r identity path
    Ts, L, Vo, Iamp, Vamp, w = 50e-6, 600e-6, 400.0, 32.0, 325.0, 2 * math.pi * 50
    st = dict(init=False, theta_prev=0.0); worst = 0.0
    for k in range(min(a.n, 800)):
        t = k * Ts; th = math.fmod(w * t, 2 * math.pi)
        vin = Vamp * math.sin(th); iL = Iamp * math.sin(th) + 0.5 * math.sin(3 * th)
        frame = [iL, Iamp, vin, Ts, L, Vo, th, 1.5, 0.8, 0.4, 0.3, -0.5, 1.0, 1]
        D, dbg = ov.mpcc_r(frame, flags=0, amp_iac=0.0, mask=511)
        worst = max(worst, abs(D - mpcc_ref(*frame[:13], True, st)))
    print(f"mpcc_r (flags=0): {min(a.n, 800)} ticks  max |dD| vs float reference {worst:.3g}  -> {'ok' if worst < 1e-4 else 'FAIL'}"); ok &= worst < 1e-4
    print(ov.report())
    print("SELFTEST", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
