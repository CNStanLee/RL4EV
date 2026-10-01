"""Collect every table and figure of the HIL-SAR paper into one folder (2026-09-06).

    python make_paper_assets.py --out EMI_DET_FPGA/runs/paper_assets

tables/*.csv + tables.md (markdown rendering of each table), figures/*.png (copied from the stage reports plus the
new summary figures drawn here), README.md (index: what each file is and where it came from).
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

R = Path(__file__).resolve().parents[2]; EMI = R / "Simulation/PV_MEV/results/emi"; RUNS = R / "EMI_DET_FPGA/runs"
CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
P1P2 = ["E-DC-01b", "E-DC-01c", "E-DC-02b", "E-AC-01a", "E-AC-01b", "E-AC-02b", "E-AC-02s", "E-AC-02h", "E-MUL-01", "E-BAT-01b", "E-BAT-02b", "E-BAT-02c", "E-BAT-01n"]
TRIP = {0: "-", 1: "UV", 2: "OV", 3: "OC", 4: "BOV", 5: "BOC"}


def md(df: pd.DataFrame, floatfmt="{:.2f}") -> str:
    d = df.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else floatfmt.format(v))
    cols = list(d.columns); lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in d.iterrows():
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r.tolist()) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(RUNS / "paper_assets")); a = ap.parse_args()
    out = Path(a.out); T = out / "tables"; F = out / "figures"; T.mkdir(parents=True, exist_ok=True); F.mkdir(parents=True, exist_ok=True)
    tables = {}; index = []

    def add(name, df, source, caption):
        df.to_csv(T / f"{name}.csv", index=False); tables[name] = (df, caption, source)

    def fig(name, src, caption):
        if Path(src).exists():
            shutil.copy(src, F / name); index.append((name, caption, str(Path(src).relative_to(R))))

    from rev_report import v6map
    SC = v6map(pd.read_csv(EMI / "scorecard.csv"))
    if "hold" in SC: SC = SC[SC.hold.fillna("").astype(str) == ""].copy()
    SC["op"] = SC["op"].fillna("cc") if "op" in SC else "cc"; SC = SC[SC.op != "cv"]      # CC segment tables; CV is in T7
    if "mm" in SC:
        SC = SC[SC.mm.fillna("") == ""]                                                    # nominal plant; mismatch runs are in rev_report.py
    SC["THD_rise_pp"] = SC.THD50_dur_pct - SC.THD50_pre_pct; SC["trip_code"] = SC.trip.map(lambda v: TRIP.get(int(v), str(v)) if pd.notna(v) else "")
    # ---- T1 attack impact, four controllers, 13 cases
    base = SC[SC.test_id.isin(P1P2) & SC.VARIANT_NAME.isin(["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_H1"])]
    piv = base.pivot_table(index="test_id", columns="VARIANT_NAME", values=["power_retention_pct", "dVdc_V", "THD_rise_pp"], aggfunc="first")
    piv.columns = [f"{v}_{m.replace('power_retention_pct', 'P%').replace('dVdc_V', 'dVdc').replace('THD_rise_pp', 'dTHD')}" for m, v in piv.columns]
    tr = base.pivot_table(index="test_id", columns="VARIANT_NAME", values="trip_code", aggfunc="first"); tr.columns = [f"{c}_trip" for c in tr.columns]
    T1 = piv.join(tr).reindex(P1P2).reset_index(); add("T1_attack_impact_controllers", T1, "results/emi/scorecard.csv", "Attack impact on four controllers (13 cases, CC segment): charging-power retention [%], real bus deviation [V], THD50 rise [pp], protection trip")
    # ---- T3 MPCC_R vs MPCC_D_H1 (+ oracle, bumpless)
    rows = []
    for v in ["MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_B"]:
        Q = SC[SC.test_id.isin(P1P2) & (SC.VARIANT_NAME == v)]
        rows.append(dict(variant=v, n=len(Q), power_retention_mean=Q.power_retention_pct.mean(), bus_dev_abs_mean=Q.dVdc_V.abs().mean(), THD_rise_mean=Q.THD_rise_pp.mean(), t_rec_mean_ms=Q.t_rec_ms.mean(), trips=int((Q.trip > 0).sum())))
    add("T3_resilience_summary", pd.DataFrame(rows), "results/emi/scorecard.csv", "Resilience summary over the 13 cases: unprotected hybrid MPCC, detector-driven MPCC_R, oracle flags (MPCC_R_OR), slew-limited fallback (MPCC_R_B)")
    per = SC[SC.test_id.isin(P1P2) & SC.VARIANT_NAME.isin(["MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_B"])].pivot_table(index="test_id", columns="VARIANT_NAME", values=["power_retention_pct", "dVdc_V", "THD_rise_pp", "trip_code"], aggfunc="first")
    per.columns = [f"{v}_{m.replace('power_retention_pct', 'P%').replace('dVdc_V', 'dVdc').replace('THD_rise_pp', 'dTHD').replace('trip_code', 'trip')}" for m, v in per.columns]
    add("T3b_resilience_per_case", per.reindex(P1P2).reset_index(), "results/emi/scorecard.csv", "Per-case resilience: MPCC_D_H1 / MPCC_R / MPCC_R_OR / MPCC_R_B")
    ab = RUNS / "resilience_report/per_bit/summary.csv"
    if ab.exists():
        add("T3c_per_bit_ablation", pd.read_csv(ab), "runs/resilience_report/per_bit/summary.csv", "Per-measure ablation of MPCC_R (M0..M8 removed / added)")
    rs = RUNS / "random_sil_report/summary.csv"
    if rs.exists():
        add("T3d_random_unseen", pd.read_csv(rs).T.reset_index().rename(columns={"index": "metric", 0: "value"}), "runs/random_sil_report/summary.csv", "20 random unseen scenarios (seeds 301-320), MPCC_D_H1 vs MPCC_R")
    # ---- T2 detector
    for name, f, cap in [("T2a_detector_feature_ablation", "detector_ablation/ablation.csv", "Feature-group ablation and single-residual baselines (random forest, run-level, 1 % FA budget, 2-cycle persistence)"),
                         ("T2b_detector_latency", "detector_ablation/latency.csv", "Detection latency distribution (cycles after the first attacked cycle)"),
                         ("T2d_float_vs_quantised", "detector_ablation/float_vs_quantised.csv", "Float vs HGQ2-quantised detector (v5 training report)"),
                         ("T2e_sil_detection_runs", "sil_report_v2/sil_runs.csv", "Per-run SIL detection record (6 variants x 13 cases)")]:
        p = RUNS / f
        if p.exists():
            D = pd.read_csv(p)
            if name == "T2a_detector_feature_ablation":
                D = D[["model", "n_features", "runs_attacked", "recall_exact", "recall_any", "latency_median", "latency_p90", "fa_pre_cycles", "fa_post_cycles", "benign_runs_with_alarm"] + [f"recall_{c}" for c in CH]]
            add(name, D, f"runs/{f}", cap)
    cm = RUNS / "detector_ablation/confusion_matrix.csv"
    if cm.exists():
        M = pd.read_csv(cm, index_col=0); add("T2c_confusion_matrix", M.reset_index().rename(columns={"index": "truth"}), "runs/detector_ablation/confusion_matrix.csv", "Channel confusion (test runs): rows true attacked channel, columns flagged channel")
        fig_, ax = plt.subplots(figsize=(5.5, 4.5)); im = ax.imshow(M.to_numpy(), cmap="Blues")
        ax.set_xticks(range(6)); ax.set_xticklabels([c.replace("det_", "") for c in M.columns]); ax.set_yticks(range(6)); ax.set_yticklabels([c.replace("truth_", "") for c in M.index])
        for i in range(6):
            for j in range(6):
                ax.text(j, i, int(M.iloc[i, j]), ha="center", va="center", color="w" if M.iloc[i, j] > M.to_numpy().max() / 2 else "k", fontsize=9)
        ax.set_xlabel("flagged channel"); ax.set_ylabel("attacked channel"); ax.set_title("channel attribution (test runs)"); fig_.colorbar(im); fig_.tight_layout(); fig_.savefig(F / "fig20_confusion.png", dpi=150)
        index.append(("fig20_confusion.png", "Channel confusion heat map of the learned detector", "drawn here from T2c"))
    # ---- T4..T8 supplementary
    for name, f, cap in [("T4_oracle_vs_detector", "supp_report/paired_MPCC_R_vs_MPCC_R_OR.csv", "MPCC_R with detector flags vs oracle flags"),
                         ("T4b_bumpless", "supp_report/paired_MPCC_R_vs_MPCC_R_B.csv", "MPCC_R vs slew-limited fallback correction (MPCC_R_B)"),
                         ("T4c_bumpless_oracle", "supp_report/paired_MPCC_R_vs_MPCC_R_B_OR.csv", "MPCC_R vs MPCC_R_B_OR on the trip cases"),
                         ("T5_amplitude_sweep", "supp_report/sweep_rows.csv", "Amplitude sweep per chain, MPCC_D_H1 vs MPCC_R"),
                         ("T6_gain_family", "supp_report/gain_family.csv", "Multiplicative gain attacks (detector never trained on them)"),
                         ("T7_cv_vs_cc", "supp_report/cv_vs_cc.csv", "CC vs CV charging segment"),
                         ("T8_benign_false_alarms", "supp_report/benign.csv", "No-attack disturbances: flagged cycles per channel and control outcome")]:
        p = RUNS / f
        if p.exists():
            D = pd.read_csv(p)
            if name == "T5_amplitude_sweep":
                D = D[["test_id", "VARIANT_NAME", "channel", "amp", "power_retention_pct", "dVdc_V", "THD50_pre_pct", "THD50_dur_pct", "trip", "detected", "delay_cycles"]]
            add(name, D, f"runs/{f}", cap)
    # ---- T9 HIL equivalence, T10 latency, T11 cost
    eq = RUNS / "hil_report/equivalence.csv"
    if eq.exists():
        E = pd.read_csv(eq); cols = [c for c in ["stage", "run", "max_dD", "n_dD_gt_1e5", "max_dVdc", "flag_mismatch_cycles", "board_flag_mismatch_cycles", "max_dlogit_board_from_cycle2", "t_detect_sil", "t_detect_hil", "d_power_retention_pct", "d_dVdc_V", "d_THD50_dur_pct", "sil_trip", "hil_trip"] if c in E]
        add("T9_hil_equivalence", E[cols], "runs/hil_report/equivalence.csv", "SIL-HIL equivalence per run and stage (x86 loopback, board mpcc / detector / estimator paths, full chain, random seeds)")
        S9 = E.groupby("stage").agg(runs=("run", "count"), bit_identical=("n_dD_gt_1e5", lambda x: int((x <= 2).sum())), max_dVdc=("max_dVdc", "max"), flag_mismatch=("flag_mismatch_cycles", "sum"), max_d_power=("d_power_retention_pct", lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan), max_d_dVdc=("d_dVdc_V", lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan), max_d_THD=("d_THD50_dur_pct", lambda x: np.nanmax(np.abs(x)) if x.notna().any() else np.nan)).reset_index()
        add("T9b_hil_equivalence_summary", S9, "runs/hil_report/equivalence.csv", "HIL equivalence summary per stage (bit_identical = runs with <= 2 ticks of |dD| > 1e-5)")
        fig_, ax = plt.subplots(figsize=(9, 3.8)); st = list(E.stage.unique()); x = np.arange(len(E)); c = [plt.cm.tab10(st.index(s)) for s in E.stage]
        ax.bar(x, E.n_dD_gt_1e5.clip(lower=0.5), color=c); ax.set_yscale("log"); ax.set_ylabel("ticks with |dD| > 1e-5 (of 14000)"); ax.set_xticks(x); ax.set_xticklabels(E.run, rotation=90, fontsize=6)
        for s in st:
            ax.bar([], [], color=plt.cm.tab10(st.index(s)), label=s)
        ax.legend(fontsize=8, ncol=6); ax.set_title("per-tick SIL-HIL difference per run (0.5 = none)"); fig_.tight_layout(); fig_.savefig(F / "fig21_hil_equivalence.png", dpi=150)
        index.append(("fig21_hil_equivalence.png", "Per-run SIL-HIL per-tick differences by stage", "drawn here from T9"))
    lat = RUNS / "hil_report/latency.csv"
    if lat.exists():
        add("T10_realtime_latency", pd.read_csv(lat)[["ip", "quantity", "n", "mean", "median", "p99", "max"]], "runs/hil_report/latency.csv", "PL / PS / TCP latency on the ZCU104 (DDR replay, C and Python PS loops, TCP path)")
    cost = RUNS / "hil_report/incremental_cost.csv"
    if cost.exists():
        add("T11_fpga_incremental_cost", pd.read_csv(cost), "runs/hil_report/incremental_cost.csv", "Implemented resources per IP and incremental cost of detection / estimation on the ZU7EV")
    # ---- controller comparison figure (T1) and benign FA figure (T8)
    fig_, axs = plt.subplots(1, 3, figsize=(15, 4.2)); vs = ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_H1", "MPCC_R"]; w = 0.16
    Q = SC[SC.test_id.isin(P1P2) & SC.VARIANT_NAME.isin(vs)]
    for k, (m, lab) in enumerate([("power_retention_pct", "charging power retention [%]"), ("dVdc_V", "real bus deviation [V]"), ("THD_rise_pp", "THD50 rise [pp]")]):
        for j, v in enumerate(vs):
            q = Q[Q.VARIANT_NAME == v].set_index("test_id").reindex(P1P2)
            axs[k].bar(np.arange(len(P1P2)) + (j - 2) * w, q[m], w, label=v)
        axs[k].set_xticks(range(len(P1P2))); axs[k].set_xticklabels(P1P2, rotation=60, fontsize=7); axs[k].set_ylabel(lab)
        if m == "THD_rise_pp":
            axs[k].set_yscale("symlog", linthresh=1)
    axs[0].legend(fontsize=7); fig_.suptitle("attack impact per controller (13 cases)"); fig_.tight_layout(); fig_.savefig(F / "fig22_controllers.png", dpi=150)
    index.append(("fig22_controllers.png", "Attack impact per controller, 13 cases", "drawn here from scorecard"))
    if "T8_benign_false_alarms" in tables:
        B = tables["T8_benign_false_alarms"][0]; B = B[B.VARIANT_NAME == "MPCC_R"].set_index("test_id")
        fig_, ax = plt.subplots(figsize=(9, 3.8)); bottom = np.zeros(len(B))
        for c, col in zip(CH, ["#4a7fb5", "#c97b3a", "#6aa84f", "#8e5ea2", "#e0a800"]):
            ax.bar(B.index, B[f"fa_{c}"], bottom=bottom, label=c, color=col); bottom += B[f"fa_{c}"].to_numpy()
        ax.set_ylabel("flagged cycles (of 35)"); ax.set_xticklabels(B.index, rotation=45, ha="right", fontsize=8); ax.legend(fontsize=8); ax.set_title("false alarms on no-attack disturbances (MPCC_R)"); fig_.tight_layout(); fig_.savefig(F / "fig23_benign_fa.png", dpi=150)
        index.append(("fig23_benign_fa.png", "False-alarm cycles per channel on benign disturbances", "drawn here from T8"))
    # ---- copy stage figures
    for name, src, cap in [("fig9_ablation_heatmap.png", RUNS / "resilience_report/fig9_ablation_heatmap.png", "Resilience ablation heat map (MPCC_D_H1, MPCC_R_OFF, MPCC_R, MPCC_R_ON)"),
                           ("fig9b_per_bit_heatmap.png", RUNS / "resilience_report/per_bit/fig9_ablation_heatmap.png", "Per-measure ablation heat map"),
                           ("fig10_timeline_E-DC-01b.png", RUNS / "resilience_report/fig10_timeline_E-DC-01b.png", "Timeline E-DC-01b: MPCC_H vs MPCC_R"),
                           ("fig10_timeline_E-AC-01b.png", RUNS / "resilience_report/fig10_timeline_E-AC-01b.png", "Timeline E-AC-01b"),
                           ("fig10_timeline_E-BAT-02b.png", RUNS / "resilience_report/fig10_timeline_E-BAT-02b.png", "Timeline E-BAT-02b"),
                           ("fig11_trips.png", RUNS / "resilience_report/fig11_trips.png", "Protection trips per variant"),
                           ("fig12b_random_pairs.png", RUNS / "random_sil_report/fig12b_random_pairs.png", "20 random unseen scenarios, paired"),
                           ("fig15_hil_vs_sil.png", RUNS / "hil_report/fig15_hil_vs_sil.png", "SIL vs HIL overlay (full chain on the board)"),
                           ("fig16_latency_hist.png", RUNS / "hil_report/fig16_latency_hist.png", "PL / PS latency histograms (DDR replay)"),
                           ("fig17_latency_breakdown.png", RUNS / "hil_report/fig17_latency_breakdown.png", "Latency breakdown per IP vs real-time budget"),
                           ("fig18_detector_ablation.png", RUNS / "detector_ablation/fig18_detector_ablation.png", "Feature-group ablation and baselines"),
                           ("fig19_amplitude_sweep.png", RUNS / "supp_report/fig19_amplitude_sweep.png", "Amplitude sweep per chain"),
                           ("estimator_thd_cases.png", RUNS / "estimator_report_v2/estimator_thd_cases.png", "Harmonic estimator THD per case")]:
        fig(name, src, cap)
    # ---- markdown + index
    with open(out / "tables.md", "w") as f:
        for name, (df, cap, src) in tables.items():
            f.write(f"## {name}\n\n{cap}  \nsource: `{src}`\n\n{md(df)}\n\n")
    with open(out / "README.md", "w") as f:
        f.write("# HIL-SAR paper assets (generated by EMI_DET_FPGA/scripts/make_paper_assets.py)\n\n## Tables (tables/*.csv, rendered in tables.md)\n\n")
        for name, (df, cap, src) in tables.items():
            f.write(f"- `{name}.csv` ({len(df)} rows): {cap} — from `{src}`\n")
        f.write("\n## Figures (figures/)\n\n")
        for name, cap, src in index:
            f.write(f"- `{name}`: {cap} — {src}\n")
    print(f"{len(tables)} tables, {len(index)} figures -> {out}")


if __name__ == "__main__":
    main()
