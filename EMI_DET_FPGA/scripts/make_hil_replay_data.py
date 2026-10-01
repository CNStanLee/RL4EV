"""Export the DDR-replay dataset for the ZCU104 real-time test (docs/HIL_TEST_PLAN.md stage H6) from one SIL record.

    python make_hil_replay_data.py --ts Simulation/PV_MEV/results/emi/ts --run E-DC-01b_MPCC_R --out runs/hil_report/replay_E-DC-01b_MPCC_R.npz

From <run>.csv (10 kHz waveforms) and <run>_det.csv (per-cycle detector record) it builds
  frames : (N_ticks, 18) float32  mpcc_r_hls inputs at the 20 kHz control rate (10 kHz record repeated twice):
           i_L i_ref V_in Ts L V_o theta A3 A5 A7 phi3 phi5 phi7 use_h flags amp_iac mask t_ramp
           (flags / amp_iac from the SIL detector decision of the cycle the tick belongs to; phases are not
           logged in the record and are set to 0 -- this dataset drives the PL for latency, not for equivalence)
  bufs   : (N_cycles, 2400) float32  the 200 x 12 cycle buffer of emi_feat_hls, row-major
           [Vdc_int Vac_int Iac_int Iref theta_pll D Vref Vbat_int Ibat_int D_dcdc state Iref_bat]
  waves  : (N_win, 80) float32  harmonic_estimator_axi windows: Iac_int resampled to 4 kHz, one window per sample
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

MASK, T_RAMP, TS, L, VREF = 437, 0.06, 5e-5, 600e-6, 400.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", default="Simulation/PV_MEV/results/emi/ts"); ap.add_argument("--run", default="E-DC-01b_MPCC_R")
    ap.add_argument("--out", default="EMI_DET_FPGA/runs/hil_report/replay_E-DC-01b_MPCC_R.npz")
    a = ap.parse_args()
    W = pd.read_csv(Path(a.ts) / f"{a.run}.csv").ffill().bfill()
    D = pd.read_csv(Path(a.ts) / f"{a.run}_det.csv")
    t = W["t"].to_numpy(); t0 = t[0]
    # ---- control ticks (20 kHz)
    W2 = W.iloc[np.repeat(np.arange(len(W) - 1), 2)].reset_index(drop=True)
    tk = t0 + np.arange(len(W2)) * TS
    cyc = np.clip(np.floor((tk - t0) / 0.02 + 1e-9).astype(int), 0, len(D) - 1)
    flags = sum((D[f"chan_{k}"].to_numpy()[cyc] > 0.5) << (k - 1) for k in range(1, 6)).astype(np.float32)
    amp_iac = D["amp_3"].to_numpy()[cyc].astype(np.float32) if "amp_3" in D else np.zeros(len(W2), np.float32)
    frames = np.column_stack([
        W2["Iac_int"], W2["Iref"], W2["Vac_int"], np.full(len(W2), TS), np.full(len(W2), L), W2["Vdc_int"], W2["theta_pll"],
        W2["amp_est_3"], W2["amp_est_5"], W2["amp_est_7"], np.zeros(len(W2)), np.zeros(len(W2)), np.zeros(len(W2)), np.ones(len(W2)),
        flags, amp_iac, np.full(len(W2), MASK), np.full(len(W2), T_RAMP)]).astype(np.float32)
    # ---- detector cycle buffers
    n_cyc = int(np.floor((t[-1] - t0) / 0.02 + 1e-9))
    cols = ["Vdc_int", "Vac_int", "Iac_int", "Iref", "theta_pll", "D", "Vref", "Vbat_int", "Ibat_int", "D_dcdc", "state", "Iref_bat"]
    W["Vref"] = VREF
    bufs = np.stack([W[cols].to_numpy()[200 * c: 200 * (c + 1)].reshape(-1) for c in range(n_cyc)]).astype(np.float32)
    # ---- estimator windows (4 kHz)
    t4 = t0 + np.arange(int((t[-1] - t0) * 4000) + 1) / 4000.0
    i4 = np.interp(t4, t, W["Iac_int"].to_numpy())
    waves = np.lib.stride_tricks.sliding_window_view(i4, 80).astype(np.float32)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, frames=frames, bufs=bufs, waves=waves, run=a.run)
    print(f"{out}: frames {frames.shape}, bufs {bufs.shape}, waves {waves.shape}; flags set on {int((flags > 0).sum())} ticks")


if __name__ == "__main__":
    main()
