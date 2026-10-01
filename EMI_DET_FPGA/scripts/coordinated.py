"""coordinated.py: rev_report/coordinated_drift.csv for the two-chain (identity-preserving) cases and the slow drifts, from the
scorecard (V6MAP-aware) and the per-cycle detector records: power retention, bus deviation, over/undershoot, THD rise, trip,
flagged channel set inside the attack window, first flag time and pre-attack false alarms."""
import sys, os, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); from rev_report import v6map, runname
R = Path(__file__).resolve().parents[2]; EMI = R / "Simulation/PV_MEV/results/emi"; OUT = R / "EMI_DET_FPGA/runs/rev_report"
CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]; CASES = ["E-MUL-01", "E-MUL-02", "E-MUL-03", "E-RP-50", "E-RP-100"]; VARS = ["MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_BR"]
S = v6map(pd.read_csv(EMI / "scorecard.csv")); S = S[(S.op.fillna("cc") == "cc") & (S.mm.fillna("") == "") & (S.get("hold", pd.Series([""] * len(S))).fillna("") == "")]
rows = []
for c in CASES:
    for v in VARS:
        q = S[(S.test_id == c) & (S.VARIANT_NAME == v)]
        if q.empty: continue
        r = q.iloc[0]; f = EMI / "ts" / f"{c}_{runname(v)}_det.csv"; flagged = ""; first = np.nan; fa = 0
        if f.exists():
            d = pd.read_csv(f); F = d[[f"chan_{k}" for k in range(1, 6)]].to_numpy() > 0.5; w = (d.t.values >= 0.7 - 1e-9) & (d.t.values < 1.0 + 1e-9)
            flagged = "+".join(CH[k] for k in np.flatnonzero(F[w].any(0))) or "none"; hit = np.flatnonzero(F.any(1) & w); first = 1e3 * (d.t.values[hit[0]] - 0.7) if hit.size else np.nan; fa = int(F[d.t.values < 0.7].any(1).sum())
        rows.append(dict(case=c, variant=v, power=r.power_retention_pct, bus=r.dVdc_V, over=r.Vdc_over_on_V, under=r.Vdc_under_on_V, dTHD=r.THD50_dur_pct - r.THD50_pre_pct, trip=int(r.trip), t_trip_ms=r.t_trip_ms, flagged=flagged, first_flag_ms=first, fa_pre=fa))
D = pd.DataFrame(rows); D.to_csv(OUT / "coordinated_drift.csv", index=False); print(D.round(1).to_string(index=False))
