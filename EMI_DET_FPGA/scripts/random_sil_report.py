"""Unseen-condition SIL (plan step 3): paired comparison of MPCC_D_H1 and MPCC_R on the randomized
dataset-mode runs (same seed = same injection / benign events / operating point).

    python scripts/random_sil_report.py --dataset ../Simulation/PV_MEV/results/emi/dataset --seeds 301 320 \
        --base MPCC_D_H1 --res MPCC_R --out runs/random_sil_report

Outputs pairs.csv (one row per seed: injection description, per-variant THD50 during / power during / bus deviation
/ trip / peak current / recovery), summary.csv, and fig12b_random_pairs.png (paired scatter: power retention and THD
rise, base vs resilient, one point per run, colored by injected channel).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CAT = {"none": "#898781", "Vdc": "#2a78d6", "Vac": "#eb6834", "Iac": "#1baf7a", "Vbat": "#eda100", "Ibat": "#e87ba4"}
INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True); ap.add_argument("--seeds", nargs=2, type=int, required=True)
    ap.add_argument("--base", default="MPCC_D_H1"); ap.add_argument("--res", default="MPCC_R"); ap.add_argument("--out", required=True)
    a = ap.parse_args(); D = Path(a.dataset); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    # per-run label files are written as each run finishes; labels.csv only when a dataset call ends
    lf = sorted((D / "labels").glob("D*.csv"))
    L = pd.concat([pd.read_csv(f) for f in lf], ignore_index=True) if lf else pd.read_csv(D / "labels.csv")
    L["run_id"] = L["run_id"].astype(str)
    rows = []
    for k in range(a.seeds[0], a.seeds[1] + 1):
        rid = f"D{k:04d}"
        r = {"run_id": rid}
        lab = L[L.run_id == rid]
        for v in (a.base, a.res):
            f = D / f"{rid}_{v}.csv"
            if not f.exists():
                continue
            s = pd.read_csv(f).iloc[0]
            lr = lab[lab.VARIANT_NAME == v]
            if len(lr):
                lr = lr.iloc[0]; r.update(channel=str(lr.get("channel1", "")) if str(lr.get("channel1", "")) != "nan" else "none",
                                          shape=lr.get("shape1", ""), amp=lr.get("amp1", np.nan), n_inj=lr.get("n_inj", 0), op=lr.get("op", "cc"),
                                          chg_t=lr.get("chg_t", 0), vref_dV=lr.get("vref_dV", 0), noise_ch=lr.get("noise_ch", ""))
            r[f"{v}_thd_pre"] = s.get("THD50_pre_pct"); r[f"{v}_thd_dur"] = s.get("THD50_dur_pct")
            r[f"{v}_P_pre"] = s.get("P_charge_pre_kW"); r[f"{v}_P_dur"] = s.get("P_charge_dur_kW")
            r[f"{v}_dVdc"] = s.get("Vdc_dur_V", np.nan) - s.get("Vdc_pre_V", np.nan)
            r[f"{v}_trip"] = int(s.get("trip", 0) or 0); r[f"{v}_Ipk"] = s.get("I_peak_A"); r[f"{v}_trec"] = s.get("t_rec_ms"); r[f"{v}_Idc"] = s.get("I_dc_A")
        rows.append(r)
    T = pd.DataFrame(rows)
    if "n_inj" not in T.columns:
        T["n_inj"] = 0
    T["n_inj"] = T["n_inj"].fillna(0).astype(int); T["channel"] = T.get("channel", pd.Series(["none"] * len(T))).fillna("none")
    for v in (a.base, a.res):
        T[f"{v}_ret"] = 100 * T[f"{v}_P_dur"] / T[f"{v}_P_pre"].replace(0, np.nan)
        T[f"{v}_thd_rise"] = T[f"{v}_thd_dur"] - T[f"{v}_thd_pre"]
    T.to_csv(out / "pairs.csv", index=False)
    inj = T[T["n_inj"] > 0]; ben = T[T["n_inj"] == 0]
    S = pd.DataFrame({
        "runs": [len(T)], "injected": [len(inj)], "benign": [len(ben)],
        f"{a.base}_ret_mean": [inj[f"{a.base}_ret"].mean()], f"{a.res}_ret_mean": [inj[f"{a.res}_ret"].mean()],
        f"{a.base}_dVdc_abs": [inj[f"{a.base}_dVdc"].abs().mean()], f"{a.res}_dVdc_abs": [inj[f"{a.res}_dVdc"].abs().mean()],
        f"{a.base}_thd_rise": [inj[f"{a.base}_thd_rise"].mean()], f"{a.res}_thd_rise": [inj[f"{a.res}_thd_rise"].mean()],
        f"{a.base}_trips": [int((inj[f"{a.base}_trip"] > 0).sum())], f"{a.res}_trips": [int((inj[f"{a.res}_trip"] > 0).sum())],
        f"{a.base}_benign_thd": [ben[f"{a.base}_thd_dur"].mean()], f"{a.res}_benign_thd": [ben[f"{a.res}_thd_dur"].mean()],
        f"{a.base}_benign_trips": [int((ben[f"{a.base}_trip"] > 0).sum())], f"{a.res}_benign_trips": [int((ben[f"{a.res}_trip"] > 0).sum())],
        "res_better_ret": [int((inj[f"{a.res}_ret"] > inj[f"{a.base}_ret"] + 1).sum())], "res_worse_ret": [int((inj[f"{a.res}_ret"] < inj[f"{a.base}_ret"] - 1).sum())],
        "res_better_thd": [int((inj[f"{a.res}_thd_rise"] < inj[f"{a.base}_thd_rise"] - 0.2).sum())], "res_worse_thd": [int((inj[f"{a.res}_thd_rise"] > inj[f"{a.base}_thd_rise"] + 0.2).sum())],
    })
    S.to_csv(out / "summary.csv", index=False); print(S.T.round(2).to_string(header=False))
    print(T[["run_id", "channel", "shape", "amp", "n_inj", "op", f"{a.base}_ret", f"{a.res}_ret", f"{a.base}_dVdc", f"{a.res}_dVdc",
             f"{a.base}_thd_rise", f"{a.res}_thd_rise", f"{a.base}_trip", f"{a.res}_trip"]].round(1).to_string(index=False))
    fig, axs = plt.subplots(1, 2, figsize=(9, 4), constrained_layout=True)
    for ax, key, lab, lim in ((axs[0], "ret", "charging power retention (%)", (0, 135)), (axs[1], "thd_rise", "THD50 rise (pp)", None)):
        for _, r in T.iterrows():
            c = CAT.get(str(r.get("channel", "none")), CAT["none"])
            ax.scatter(r[f"{a.base}_{key}"], r[f"{a.res}_{key}"], s=36, color=c, edgecolor="#ffffff", lw=0.8, zorder=3)
        lo = np.nanmin([T[f"{a.base}_{key}"].min(), T[f"{a.res}_{key}"].min()]); hi = np.nanmax([T[f"{a.base}_{key}"].max(), T[f"{a.res}_{key}"].max()])
        if lim: lo, hi = lim
        ax.plot([lo, hi], [lo, hi], color="#898781", lw=1, ls="--", zorder=1)
        if key == "thd_rise":      # a charging stop gives THD rises of thousands of pp: symlog keeps the 0..20 pp region readable
            ax.set_xscale("symlog", linthresh=10); ax.set_yscale("symlog", linthresh=10)
        ax.set_xlabel(f"{a.base}: {lab}", color=INK2); ax.set_ylabel(f"{a.res}: {lab}", color=INK2); ax.grid(color="#e6e5e1", lw=0.5)
    for ch, c in CAT.items():
        axs[0].scatter([], [], color=c, label=ch)
    axs[0].legend(title="injected channel", frameon=False, fontsize=8, loc="lower right")
    fig.suptitle(f"Fig. 12b  Random unseen conditions, seeds {a.seeds[0]}..{a.seeds[1]}: {a.res} vs {a.base} (one point per run)", x=0.01, ha="left", color=INK)
    fig.savefig(out / "fig12b_random_pairs.png", dpi=150); plt.close(fig)
    print("->", out)


if __name__ == "__main__":
    main()
