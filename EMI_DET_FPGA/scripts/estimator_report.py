"""Harmonic-estimator comparison from the injection scorecard: MPCC_D_F1 / F10 / R
(FFT, RLS) versus MPCC_D_M1 (HGQ2 raw) and MPCC_D_H1 (FFT+HGQ2 fusion).

    python scripts/estimator_report.py --scorecard ../Simulation/PV_MEV/results/emi/scorecard.csv \
        --baselines ../Simulation/PV_MEV/results/emi [--out runs/estimator_report]

Tables: baseline THD50 / full-band THD / PF; per case THD50 during the bias and
after removal, recovery time, trips; figure: THD50 before/during/after per case
for the five estimator variants.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

V = ["MPCC_D", "MPCC_D_F1", "MPCC_D_F10", "MPCC_D_R", "MPCC_D_M1", "MPCC_D_H1"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorecard", required=True); ap.add_argument("--baselines", required=True); ap.add_argument("--out", default="runs/estimator_report")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    B = []
    for v in V:
        p = Path(args.baselines) / f"baseline_{v}.csv"
        if p.exists():
            b = pd.read_csv(p).iloc[0]; B.append(dict(variant=v, THD50=b["THD50_pct"], THD_full=b["THD_full_pct"], PF=b["PF"], I2=b["I2_pct"]))
    B = pd.DataFrame(B); print("baseline (charger load, 6.9 kW):"); print(B.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    S = pd.read_csv(args.scorecard); S = S[S.VARIANT_NAME.isin(V) & (S.get("status", "OK") == "OK")]
    cols = ["THD50_pre_pct", "THD50_dur_pct", "THD50_post_pct", "THD_full_dur_pct", "PF_dur", "t_rec_ms", "trip", "I_peak_A", "P_charge_dur_kW"]
    P = S.pivot_table(index="test_id", columns="VARIANT_NAME", values="THD50_dur_pct")
    print("\nTHD50 during the bias (%):"); print(P.reindex(columns=[v for v in V if v in P.columns]).to_string(float_format=lambda x: f"{x:.2f}"))
    P2 = S.pivot_table(index="test_id", columns="VARIANT_NAME", values="t_rec_ms")
    print("\nrecovery time (ms):"); print(P2.reindex(columns=[v for v in V if v in P2.columns]).to_string(float_format=lambda x: f"{x:.0f}"))
    P3 = S.pivot_table(index="test_id", columns="VARIANT_NAME", values="trip")
    print("\nprotection trips (0 none 1 UV 2 OV 3 OC 4 BOV 5 BOC):"); print(P3.reindex(columns=[v for v in V if v in P3.columns]).to_string(float_format=lambda x: f"{x:.0f}"))
    S[["test_id", "VARIANT_NAME"] + cols].to_csv(out / "estimator_cases.csv", index=False); B.to_csv(out / "estimator_baseline.csv", index=False)
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        cases = sorted(S.test_id.unique()); fig, ax = plt.subplots(figsize=(12, 4.5))
        w = 0.8 / len(V)
        for i, v in enumerate(V):
            s = S[S.VARIANT_NAME == v].set_index("test_id").reindex(cases)
            ax.bar(np.arange(len(cases)) + i * w, s["THD50_dur_pct"].clip(upper=40), w, label=v)
        ax.set_xticks(np.arange(len(cases)) + 0.4); ax.set_xticklabels(cases, rotation=30); ax.set_ylabel("THD50 during bias (%, clipped at 40)")
        ax.legend(ncol=6, fontsize=8); ax.grid(axis="y", alpha=0.4); ax.set_title("Harmonic-compensated MPCC variants under sensor-chain injection")
        fig.tight_layout(); fig.savefig(out / "estimator_thd_cases.png", dpi=130); print("figure:", out / "estimator_thd_cases.png")
    except Exception as e:
        print("figure skipped:", e)


if __name__ == "__main__":
    main()
