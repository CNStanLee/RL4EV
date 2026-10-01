"""attack_window.py: whole-window scores per (case, variant) from the 10 kHz records, written to rev_report/attack_window_metrics.csv.
Window 0.7-1.0 s. energy_deficit_J = integral of max(0, 6900 W - P_charge); peak_bus_V = max |Vdc_real - 400|; viol_ms = time with a true
quantity beyond a protection threshold (Vdc < 300 or > 450 V, |Iac| > 65 A, Vbat > 355 V, Ibat > 25 A); power_err_pp and latched from the
per-run summary; joint = |power_err| <= 1 pp and not latched.  V6MAP=1 renames the v6 runs to the v5 variant names (rev_report.v6map)."""
import sys, os, pandas as pd, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); from rev_report import v6map, V6MAP
R = Path(__file__).resolve().parents[2]; EMI = R / "Simulation/PV_MEV/results/emi"; OUT = R / "EMI_DET_FPGA/runs/rev_report"
CASES = ["E-DC-01b", "E-DC-01c", "E-DC-02b", "E-AC-01a", "E-AC-01b", "E-AC-02b", "E-AC-02h", "E-AC-02s", "E-BAT-01b", "E-BAT-01n", "E-BAT-02b", "E-BAT-02c", "E-MUL-01"]
VARS_V5 = ["MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_OR1", "MPCC_R_OR2", "MPCC_R_OR3", "MPCC_R_B", "MPCC_R_BR", "MPCC_R_P1", "CRPR", "MPCC_P", "MPCC_D"]
VARS_V6 = ["MPCC_H6", "MPCC_R6", "MPCC_R6_OR", "MPCC_R6_OR1", "MPCC_R6_OR2", "MPCC_R6_OR3", "MPCC_R_REG", "MPCC_R6_BR", "MPCC_R6_P1", "MPCC_R6_B", "CRPR", "MPCC_P", "MPCC_D", "MPCC_H6_S", "MPCC_R6_noM11", "MPCC_R6_noM14", "MPCC_R6_RES", "MPCC_H6_L55"]


def score(case, var):
    f = EMI / f"{case}_{var}.csv"; g = EMI / "ts" / f"{case}_{var}.csv"
    if not f.exists() or not g.exists(): return None
    r = pd.read_csv(f).iloc[0]; t = pd.read_csv(g); w = t[(t.t >= 0.7) & (t.t < 1.0)]; dt = 1e-4
    ded = float((np.clip(6900.0 - w.P_charge.values, 0, None) * dt).sum())
    peak = float((w.Vdc_real - 400).abs().max())
    viol = ((w.Vdc_real < 300) | (w.Vdc_real > 450) | (w.Iac_real.abs() > 65) | (w.Vbat_real > 355) | (w.Ibat_real > 25)).sum() * dt * 1e3
    perr = float(r.power_retention_pct - 100); lat = int(r.trip > 0)
    return dict(case=case, variant=var, energy_deficit_J=ded, peak_bus_V=peak, viol_ms=float(viol), power_err_pp=perr, latched=lat, joint=int(abs(perr) <= 1 and lat == 0))


def main():
    v6 = os.environ.get("V6MAP") == "1"; vars_ = VARS_V6 if v6 else VARS_V5; rows = []
    for v in vars_:
        for c in CASES:
            s = score(c, v)
            if s: rows.append(s)
    D = pd.DataFrame(rows); D = v6map(D, "variant") if v6 else D
    out = OUT / ("attack_window_metrics.csv" if v6 or "--write-v5" in sys.argv else "attack_window_metrics_check.csv")
    D.to_csv(out, index=False); print("wrote", out, len(D), "rows"); return D


if __name__ == "__main__":
    D = main()
    if "--check" in sys.argv:
        O = pd.read_csv(OUT / "attack_window_metrics.csv"); M = O.merge(D, on=["case", "variant"], suffixes=("_old", "_new"))
        for c in ["energy_deficit_J", "peak_bus_V", "viol_ms", "power_err_pp", "latched", "joint"]:
            print(f"{c:18s} max |old-new| = {(M[c+'_old'] - M[c+'_new']).abs().max():.4g}  over {len(M)} rows")
