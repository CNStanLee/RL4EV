"""Resilient-MPCC ablation report (plan step 2.6 / 3.3): tables and figures 9 to 11 from the scorecard.

    python scripts/resilience_report.py --scorecard ../Simulation/PV_MEV/results/emi/scorecard.csv \
        --groups MPCC_D_H1 MPCC_R_OFF MPCC_R MPCC_R_ON --base MPCC_D_H1 --out runs/resilience_report \
        [--ts ../Simulation/PV_MEV/results/emi/ts --timeline E-DC-01b E-AC-01b]

Outputs: ablation.csv (one row per case x group: trip, power retention, real bus deviation, THD50 rise,
recovery, withdrawal peak current), summary.csv (per group), fig9_ablation_heatmap.png (cases x groups,
three panels), fig11_trips.png (protection trips and withdrawal peak current per group), and
fig10_timeline_<case>.png when --ts is given (real bus, charging power, Iref, detector flags and the
mitigation gains of the base strategy and MPCC_R).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

# reference palette (dataviz skill): categorical order, one-hue sequential ramp, status colors
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQ = LinearSegmentedColormap.from_list("blue_seq", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
STATUS = dict(good="#0ca30c", warning="#fab219", serious="#ec835a", critical="#d03b3b")
INK, INK2, MUTED, SURF = "#0b0b0b", "#52514e", "#898781", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF})


def table(sc: pd.DataFrame, groups: list[str], base: str) -> pd.DataFrame:
    rows = []
    for tid, g in sc.groupby("test_id", sort=False):
        for v in groups:
            r = g[g.VARIANT_NAME == v]
            if r.empty:
                continue
            r = r.iloc[0]
            # trip = Protection Monitor code (1 UV 2 OV 3 OC 4 BOV 5 BOC), 0 = none
            rows.append(dict(test_id=tid, group=v, trip=int(r.get("trip", 0) or 0), t_trip_ms=r.get("t_trip_ms", np.nan),
                             power_retention_pct=r.get("power_retention_pct", np.nan),
                             dVdc_real_V=r.get("Vdc_dur_V", np.nan) - r.get("Vdc_pre_V", np.nan),
                             thd_rise_pp=r.get("THD50_dur_pct", np.nan) - r.get("THD50_pre_pct", np.nan),
                             I_dc_A=r.get("I_dc_A", np.nan), t_rec_ms=r.get("t_rec_ms", np.nan), I_peak_A=r.get("I_peak_A", np.nan),
                             PF_dur=r.get("PF_dur", np.nan)))
    T = pd.DataFrame(rows)
    return T


def heatmap(ax, M: np.ndarray, rows, cols, title, fmt, vmin=None, vmax=None, cmap=SEQ, note=""):
    im = ax.imshow(M, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols, rotation=30, ha="right")
    ax.set_yticks(range(len(rows))); ax.set_yticklabels(rows)
    ax.set_title(title, loc="left", color=INK, fontsize=10)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            if np.isfinite(v):
                ax.text(j, i, fmt.format(v), ha="center", va="center", color=INK if (im.norm(v) < 0.6) else "#ffffff", fontsize=8)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    if note:
        ax.set_xlabel(note, color=MUTED, fontsize=8)


def fig9(T: pd.DataFrame, groups, out: Path):
    cases = list(dict.fromkeys(T.test_id))
    def M(col):
        return np.array([[T[(T.test_id == c) & (T.group == g)][col].iloc[0] if ((T.test_id == c) & (T.group == g)).any() else np.nan for g in groups] for c in cases])
    fig, axs = plt.subplots(1, 3, figsize=(3.2 * len(groups) + 4, 0.42 * len(cases) + 1.8), constrained_layout=True)
    heatmap(axs[0], M("power_retention_pct"), cases, groups, "Charging power retention during injection (%)", "{:.0f}", 0, 130)
    heatmap(axs[1], np.abs(M("dVdc_real_V")), cases, groups, "Real bus deviation |ΔVdc| (V)", "{:.0f}", 0, 110, note="lower is better")
    heatmap(axs[2], M("thd_rise_pp"), cases, groups, "THD50 rise during injection (pp)", "{:+.1f}", -1, 25, note="lower is better")
    # trips as a status ring on the cells
    trip = M("trip")
    for j in range(len(groups)):
        for i in range(len(cases)):
            if np.isfinite(trip[i, j]) and trip[i, j] > 0:
                for ax in axs:
                    ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor=STATUS["critical"], lw=2))
    fig.suptitle("Fig. 9  Resilient MPCC ablation: cases × groups (red frame = protection trip)", x=0.01, ha="left", color=INK)
    fig.savefig(out / "fig9_ablation_heatmap.png", dpi=150); plt.close(fig)


def fig11(T: pd.DataFrame, groups, out: Path):
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.2), constrained_layout=True)
    trips = [int((T[T.group == g].trip > 0).sum()) for g in groups]
    axs[0].bar(range(len(groups)), trips, color=CAT[:len(groups)], width=0.55)
    axs[0].set_xticks(range(len(groups))); axs[0].set_xticklabels(groups, rotation=20, ha="right")
    axs[0].set_title("Protection trips over the case set", loc="left", color=INK, fontsize=10); axs[0].set_ylabel("cases with a trip")
    for i, t in enumerate(trips):
        axs[0].text(i, t + 0.05, str(t), ha="center", color=INK2)
    pk = [T[T.group == g].I_peak_A.max() for g in groups]
    axs[1].bar(range(len(groups)), pk, color=CAT[:len(groups)], width=0.55)
    axs[1].axhline(65, color=STATUS["critical"], lw=1, ls="--"); axs[1].text(len(groups) - 0.5, 66, "OC threshold 65 A", ha="right", color=STATUS["critical"], fontsize=8)
    axs[1].set_xticks(range(len(groups))); axs[1].set_xticklabels(groups, rotation=20, ha="right")
    axs[1].set_title("Worst grid-current peak (A), all cases", loc="left", color=INK, fontsize=10)
    fig.suptitle("Fig. 11  Trips and current peaks per group", x=0.01, ha="left", color=INK)
    fig.savefig(out / "fig11_trips.png", dpi=150); plt.close(fig)


def fig10(ts_dir: Path, case: str, base: str, res: str, out: Path):
    f0 = ts_dir / f"{case}_{base}.csv"; f1 = ts_dir / f"{case}_{res}.csv"
    if not (f0.exists() and f1.exists()):
        print(f"[fig10] {case}: missing {f0.name if not f0.exists() else f1.name}"); return
    A = pd.read_csv(f0); B = pd.read_csv(f1)
    D0 = ts_dir / f"{case}_{base}_det.csv"; D1 = ts_dir / f"{case}_{res}_det.csv"
    fig, axs = plt.subplots(4, 1, figsize=(9, 8), sharex=True, constrained_layout=True)
    for X, name, col in ((A, base, CAT[0]), (B, res, CAT[1])):
        axs[0].plot(X.t, X.Vdc_real, color=col, lw=1.5, label=name)
        axs[1].plot(X.t, X.P_charge / 1e3, color=col, lw=1.5, label=name)
        axs[2].plot(X.t, X.Iref, color=col, lw=1.5, label=name)
    axs[0].set_ylabel("real Vdc (V)"); axs[1].set_ylabel("P_charge (kW)"); axs[2].set_ylabel("Iref amplitude (A)")
    if D1.exists():
        d = pd.read_csv(D1)
        for k, nm in enumerate(["Vdc", "Vac", "Iac", "Vbat", "Ibat"]):
            c = d.get(f"chan_{k + 1}")
            if c is not None:
                axs[3].step(d.t, c + 1.1 * k, where="post", color=CAT[k % len(CAT)], lw=1.5, label=f"flag {nm}")
        for k, nm in ((1, "g_vdc"), (5, "g_iac")):
            c = d.get(f"mit_{k}")
            if c is not None:
                axs[3].step(d.t, c + 5.6 + 1.1 * (k == 5), where="post", color=INK2, lw=1, ls="--", label=nm)
    axs[3].set_ylabel("detector flags / gains"); axs[3].set_yticks([])
    axs[3].set_xlabel("t (s)")
    for ax in axs:
        ax.legend(loc="upper right", frameon=False, fontsize=8); ax.grid(color="#e6e5e1", lw=0.5)
    fig.suptitle(f"Fig. 10  {case}: {base} vs {res}", x=0.01, ha="left", color=INK)
    fig.savefig(out / f"fig10_timeline_{case}.png", dpi=150); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorecard", required=True); ap.add_argument("--groups", nargs="+", required=True); ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--ts"); ap.add_argument("--timeline", nargs="*", default=[]); ap.add_argument("--res", default="MPCC_R")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    sc = pd.read_csv(a.scorecard)
    T = table(sc, a.groups, a.base); T.to_csv(out / "ablation.csv", index=False)
    S = T.groupby("group", sort=False).agg(cases=("test_id", "count"), trips=("trip", lambda x: int((x > 0).sum())), power_retention_mean=("power_retention_pct", "mean"),
                                           dVdc_abs_mean=("dVdc_real_V", lambda x: np.nanmean(np.abs(x))), thd_rise_mean=("thd_rise_pp", "mean"),
                                           t_rec_mean_ms=("t_rec_ms", "mean"), I_peak_max=("I_peak_A", "max"))
    S = S.reindex(a.groups); S.to_csv(out / "summary.csv"); print(S.round(2).to_string())
    fig9(T, a.groups, out); fig11(T, a.groups, out)
    if a.ts:
        for c in a.timeline:
            fig10(Path(a.ts), c, a.base, a.res, out)
    print("->", out)


if __name__ == "__main__":
    main()
