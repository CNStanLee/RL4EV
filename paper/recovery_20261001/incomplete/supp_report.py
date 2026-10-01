"""Supplementary-experiment report (2026-09-06): amplitude sweep, gain family, oracle / bumpless variants, CV segment,
benign disturbances.  Reads results/emi/scorecard.csv (E-* rows incl. E-GN-* / E-SW-* and *_cv files), the per-cycle
detector records in results/emi/ts, and results/emi/benign/scorecard.csv.

    python supp_report.py --emi Simulation/PV_MEV/results/emi --out EMI_DET_FPGA/runs/supp_report
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
KEEP = ["test_id", "VARIANT_NAME", "channel", "shape", "amp", "power_retention_pct", "dVdc_V", "Vdc_over_on_V", "Vdc_under_on_V", "THD50_pre_pct", "THD50_dur_pct", "I_dc_A", "trip", "t_trip_ms", "t_rec_ms", "status"]


def detection(emi, run):
    """first flagged channel set and delay (cycles) from the per-cycle record; None when missing."""
    f = Path(emi) / "ts" / f"{run}_det.csv"
    if not f.exists():
        return None
    D = pd.read_csv(f); F = D[[f"chan_{k}" for k in range(1, 6)]].to_numpy() > 0.5
    on = np.flatnonzero((D.t >= 0.7 - 1e-9) & (D.t < 1.0))
    if not on.size:
        return dict(detected="none", delay_cycles=np.nan, fa_pre=int(F[D.t < 0.7].sum()))
    hit = [i for i in on if F[i].any()]
    det = "+".join(CH[c] for c in np.flatnonzero(F[on].any(0))) or "none"
    return dict(detected=det, delay_cycles=(hit[0] - on[0]) if hit else np.nan, fa_pre=int(F[D.t < 0.7].sum()), flagged_cycles_in_window=int(F[on].any(1).sum()))


def load_all(emi):
    rows = []
    for f in sorted(glob.glob(str(Path(emi) / "E-*.csv"))):
        T = pd.read_csv(f)
        if "status" in T and str(T.status.iloc[0]) != "OK":
            continue
        if "mm" in T and str(T.mm.iloc[0]) not in ("", "nan"):
            continue                                     # plant-mismatch runs are reported separately (rev_report.py)
        T["file"] = Path(f).stem; T["op"] = "cv" if Path(f).stem.endswith("_cv") else T.get("op", "cc")
        rows.append(T)
    A = pd.concat(rows, ignore_index=True)
    det = []
    for _, r in A.iterrows():
        d = detection(emi, r.file); det.append(d or {})
    A = pd.concat([A, pd.DataFrame(det)], axis=1)
    return A


def sweep(A, out):
    S = A[(A.test_id.str.startswith("E-SW-") | A.test_id.isin(["E-DC-01b", "E-DC-01c", "E-AC-01a", "E-AC-01b", "E-AC-02b", "E-BAT-02b", "E-BAT-02c", "E-BAT-01b", "E-BAT-01n"])) & (A.op == "cc") & (A["shape"] == "step")]
    S = S[S.VARIANT_NAME.isin(["MPCC_D_H1", "MPCC_R"])].copy()
    S.to_csv(out / "sweep_rows.csv", index=False)
    fig, axs = plt.subplots(3, 5, figsize=(17, 9), sharex="col")
    for j, ch in enumerate(CH):
        for v, c in [("MPCC_D_H1", "#c97b3a"), ("MPCC_R", "#4a7fb5")]:
            Q = S[(S.channel == ch) & (S.VARIANT_NAME == v)].sort_values("amp")
            if Q.empty:
                continue
            axs[0, j].plot(Q.amp, Q.power_retention_pct, "o-", color=c, label=v); axs[1, j].plot(Q.amp, Q.dVdc_V, "o-", color=c); axs[2, j].plot(Q.amp, Q.THD50_dur_pct - Q.THD50_pre_pct, "o-", color=c)
            tr = Q[Q.trip > 0]
            for ax, col in [(axs[0, j], "power_retention_pct"), (axs[1, j], "dVdc_V")]:
                ax.plot(tr.amp, tr[col], "x", color="k", ms=9)
            nd = Q[Q.detected == "none"]
            axs[0, j].plot(nd.amp, nd.power_retention_pct, "s", mfc="none", mec="r", ms=11)
        axs[0, j].set_title(f"{ch} chain step"); axs[2, j].set_xlabel("bias amplitude (V or A)")
    axs[0, 0].set_ylabel("charging power retention [%]"); axs[1, 0].set_ylabel("real bus deviation [V]"); axs[2, 0].set_ylabel("THD50 rise [pp]"); axs[0, 0].legend(fontsize=8)
    fig.suptitle("amplitude sweep (x = protection trip, red square = not detected)"); fig.tight_layout(); fig.savefig(out / "fig19_amplitude_sweep.png", dpi=130)
    return S


def table(A, out, name, variants, tests=None, op="cc"):
    Q = A[A.VARIANT_NAME.isin(variants) & (A.op == op)]
    if tests is not None:
        Q = Q[Q.test_id.isin(tests)]
    cols = [c for c in KEEP + ["detected", "delay_cycles", "fa_pre"] if c in Q]
    Q = Q[cols].sort_values(["test_id", "VARIANT_NAME"]); Q.to_csv(out / f"{name}.csv", index=False)
    return Q


def paired(A, out, name, base, variant, op="cc"):
    B = A[(A.VARIANT_NAME == base) & (A.op == op)].set_index("test_id"); V = A[(A.VARIANT_NAME == variant) & (A.op == op)].set_index("test_id")
    ids = sorted(set(B.index) & set(V.index)); rows = []
    for t in ids:
        rows.append(dict(test_id=t, **{f"{base}_{k}": B.loc[t, k] for k in ["power_retention_pct", "dVdc_V", "THD50_dur_pct", "trip", "t_rec_ms"]},
                         **{f"{variant}_{k}": V.loc[t, k] for k in ["power_retention_pct", "dVdc_V", "THD50_dur_pct", "trip", "t_rec_ms"]}))
    P = pd.DataFrame(rows); P.to_csv(out / f"{name}.csv", index=False); return P


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--emi", default="Simulation/PV_MEV/results/emi"); ap.add_argument("--out", default="EMI_DET_FPGA/runs/supp_report")
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    A = load_all(a.emi); A.to_csv(out / "all_rows.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
    print("== amplitude sweep"); S = sweep(A, out)
    print(S[["test_id", "VARIANT_NAME", "channel", "amp", "power_retention_pct", "dVdc_V", "THD50_dur_pct", "trip", "detected", "delay_cycles"]].round(2).to_string(index=False))
    print("== gain family"); G = table(A, out, "gain_family", ["MPCC_D_H1", "MPCC_R"], tests=[t for t in A.test_id.unique() if str(t).startswith("E-GN-")])
    print(G[["test_id", "VARIANT_NAME", "amp", "power_retention_pct", "dVdc_V", "THD50_dur_pct", "I_dc_A", "trip", "detected", "delay_cycles"]].round(2).to_string(index=False))
    print("== oracle / bumpless vs detector-driven MPCC_R")
    for v in ["MPCC_R_OR", "MPCC_R_B", "MPCC_R_B_OR"]:
        P = paired(A, out, f"paired_MPCC_R_vs_{v}", "MPCC_R", v)
        if len(P):
            print(f"-- {v}"); print(P.round(2).to_string(index=False))
    print("== CV segment vs CC"); rows = []
    for v in [v for v in ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_H1", "MPCC_R", "MPCC_R_OR"] if (A.VARIANT_NAME == v).any() and ((A.VARIANT_NAME == v) & (A.op == "cv")).any()]:
        C = A[(A.VARIANT_NAME == v) & (A.op == "cc")].set_index("test_id"); V = A[(A.VARIANT_NAME == v) & (A.op == "cv")].set_index("test_id")
        for t in sorted(set(C.index) & set(V.index)):
            rows.append(dict(test_id=t, variant=v, cc_power=C.loc[t, "power_retention_pct"], cv_power=V.loc[t, "power_retention_pct"], cc_dVdc=C.loc[t, "dVdc_V"], cv_dVdc=V.loc[t, "dVdc_V"],
                             cc_THD=C.loc[t, "THD50_dur_pct"], cv_THD=V.loc[t, "THD50_dur_pct"], cc_trip=C.loc[t, "trip"], cv_trip=V.loc[t, "trip"], cc_det=C.loc[t, "detected"], cv_det=V.loc[t, "detected"]))
    CV = pd.DataFrame(rows); CV.to_csv(out / "cv_vs_cc.csv", index=False)
    if len(CV):
        print(CV.round(2).to_string(index=False))
    print("== benign disturbances")
    bf = Path(a.emi) / "benign" / "scorecard.csv"
    if bf.exists():
        B = pd.read_csv(bf); cols = [c for c in ["test_id", "VARIANT_NAME", "benign_desc", "fa_cycles", "fa_Vdc", "fa_Vac", "fa_Iac", "fa_Vbat", "fa_Ibat", "t_first_fa", "THD50_pre_pct", "THD50_dur_pct", "P_charge_dur_kW", "dVdc_V", "trip", "status"] if c in B]
        B[cols].to_csv(out / "benign.csv", index=False); print(B[cols].round(2).to_string(index=False))
        att = B[B.status == "OK"]
        print(f"benign runs {len(att)}, runs with any alarm {(att.fa_cycles > 0).sum()}, alarm cycles {int(att.fa_cycles.sum())} of {len(att) * 35}")


if __name__ == "__main__":
    main()
