"""Reference vectors for the feature-extraction IP (HLS_PRJ/emi_feat): raw 200 x 12 cycle buffers of
the Simulink EMI Detector (10 kHz, columns Vdc_int Vac_int Iac_int Iref theta D Vref Vbat_int Ibat_int
D_dcdc state Iref_bat) and the 48 features of features.cycle_features_v3 computed on the same cycles.

    python scripts/make_feat_vectors.py --ts ../Simulation/PV_MEV/results/emi/ts/E-AC-02b_MPCC_D_H1.csv \
        [--ts ...] --out ../HLS_PRJ/emi_feat/tb_data [--max-cycles 400]

Cycles of every listed run are written consecutively (the delta features depend on the previous cycle
of the same run; the IP is reset at the start of each run through its `reset` argument, so the file
also carries a run-boundary flag per cycle).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emi_det.features import FS, NCYC, T0, FEATURE_NAMES_V3, cycle_features_v3, vref_series  # noqa: E402

COLS = ["Vdc_int", "Vac_int", "Iac_int", "Iref", "theta_pll", "D", "Vref", "Vbat_int", "Ibat_int", "D_dcdc", "state", "Iref_bat"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", action="append", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--max-cycles", type=int, default=400)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    X_all, F_all, first = [], [], []
    for p in a.ts:
        df = pd.read_csv(p)
        t = df["t"].to_numpy(); vr = vref_series(t)
        df["Vref"] = vr
        cf = cycle_features_v3(df, vr)
        phase = int(round((t[0] - T0) * FS)) % NCYC; k0 = (NCYC - phase) % NCYC
        n = min(cf.X.shape[0], a.max_cycles)
        for i in range(n):
            sl = slice(k0 + i * NCYC, k0 + (i + 1) * NCYC)
            xb = df[COLS].to_numpy()[sl]
            # the first logged sample of a restored run is NaN in some columns: the IP gets zeros there and the
            # cycle (and the next one, whose deltas refer to it) is excluded from the comparison via valid = 0
            ok = bool(np.isfinite(xb).all() and np.isfinite(cf.X[i]).all())
            X_all.append(np.nan_to_num(xb)); F_all.append(np.nan_to_num(cf.X[i])); first.append((1 if i == 0 else 0) + (0 if ok else 2))
        print(f"{Path(p).stem}: {n} cycles")
    X = np.asarray(X_all, np.float32); F = np.asarray(F_all, np.float64)
    np.savetxt(out / "buf_raw.dat", X.reshape(len(X), -1), fmt="%.8g")           # one cycle per line: 200*12 values, row-major (sample, column)
    np.savetxt(out / "ref_feat.dat", F, fmt="%.10g")
    np.savetxt(out / "run_start.dat", np.asarray(first, int), fmt="%d")   # bit0 = first cycle of a run (IP reset), bit1 = exclude from comparison
    (out / "feature_names.txt").write_text("\n".join(FEATURE_NAMES_V3) + "\n")
    print(f"{len(X)} cycles -> {out}")


if __name__ == "__main__":
    main()
