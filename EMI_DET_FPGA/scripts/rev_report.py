"""Revision report (review of 2026-09-07): tables that answer the ten major points.

    python rev_report.py            (writes EMI_DET_FPGA/runs/rev_report/*.csv and figures)

  unified_summary.csv        one detector protocol, five models, three test sets (point 5, 6)
  unified_channels.csv       per-channel precision / recall of the deployed model
  unified_confusion.csv      truth -> detected channel-set pairs of the deployed model on the 104 benchmark runs
  rt_sched.csv               concurrent three-task schedule on the PS (point 4)
  det_path.csv               C detector path breakdown (buffer write / feature IP / detector IP)
  power_baseline.csv         controller-only vs full bitstream, idle vs active (point 9)
  power_error.csv            charging-power retention as absolute error vs the pre-attack target (point 3)
  power_error_summary.csv    mean |error|, share within 1 / 5 pp, worst case per controller
  trip_events.csv            every latched limit violation over the 13 cases (point 2)
  delayed_oracle.csv         MPCC_R vs oracle with 0 / 1 / 2 / 3 cycles of fixed delay (point 7)   [when present]
  mismatch.csv               MPCC_R under plant-parameter mismatch (point 8)                          [when present]
  benign_paired.csv          MPCC-H / MPCC-R / MPCC-R-P1 on the same no-attack disturbances (point 1)
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

R = Path(__file__).resolve().parents[2]; RUNS = R / "EMI_DET_FPGA/runs"; EMI = R / "Simulation/PV_MEV/results/emi"; OUT = RUNS / "rev_report"
CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
P1P2 = ["E-DC-01b", "E-DC-01c", "E-DC-02b", "E-AC-01a", "E-AC-01b", "E-AC-02b", "E-AC-02s", "E-AC-02h", "E-MUL-01", "E-BAT-01b", "E-BAT-02b", "E-BAT-02c", "E-BAT-01n"]
TRIP = {0: "--", 1: "UV", 2: "OV", 3: "OC", 4: "BOV", 5: "BOC"}
BUDGET = {"mpcc": 50.0, "detector": 20000.0, "estimator": 250.0}

V6MAP = {"MPCC_R6": "MPCC_R", "MPCC_R6_OR": "MPCC_R_OR", "MPCC_R6_OR1": "MPCC_R_OR1", "MPCC_R6_OR2": "MPCC_R_OR2", "MPCC_R6_OR3": "MPCC_R_OR3", "MPCC_R6_ON": "MPCC_R_ON",
         "MPCC_R6_BR": "MPCC_R_BR", "MPCC_R6_P1": "MPCC_R_P1", "MPCC_R6_B": "MPCC_R_B", "MPCC_R6_noM11": "MPCC_R_noM11", "MPCC_R6_noM14": "MPCC_R_noM14", "MPCC_R6_RES": "MPCC_R_RES", "MPCC_H6_L55": "MPCC_H_L55", "MPCC_H6": "MPCC_D_H1", "MPCC_R_REG": "MPCC_R_v5", "MPCC_H6_S": "MPCC_H_S"}


V6INV = {v: k for k, v in V6MAP.items()}


def runname(variant):
    """Name under which a run's files are stored: the v6 run name when V6MAP=1, else the variant name itself."""
    import os
    return V6INV.get(variant, variant) if os.environ.get("V6MAP") == "1" else variant


def v6map(df, col="VARIANT_NAME"):
    """With V6MAP=1 in the environment: rename the v6 runs to the paper's variant names, dropping a v5 row only where a v6 run
    with the same keys (test / run id, operating point, mismatch tag, hold tag) exists; families that were not re-run keep v5."""
    import os
    if os.environ.get("V6MAP") != "1" or col not in df:
        return df
    df = df.copy(); keys = [k for k in ["test_id", "run_id", "op", "mm", "hold"] if k in df]
    for k, fill in (("op", "cc"), ("mm", ""), ("hold", "")):   # normalise the keys so that v5 and v6 rows of the same run compare equal
        if k in df: df[k] = df[k].fillna(fill).astype(str).replace({"nan": fill})
    v6 = df[df[col].isin(V6MAP.keys())]
    if keys:
        have = set(map(tuple, v6[[col] + keys].astype(str).values))
        drop = df.apply(lambda r: (r[col] in V6INV) and ((V6INV[r[col]],) + tuple(str(r[k]) for k in keys)) in have, axis=1)
        df = df[~drop]
    else:
        df = df[~df[col].isin(set(V6MAP.values()) - {"MPCC_R_v5", "MPCC_H_S"})]
    df[col] = df[col].replace(V6MAP)
    return df


def scorecard():
    S = v6map(pd.read_csv(EMI / "scorecard.csv")); S["op"] = S.op.fillna("cc") if "op" in S else "cc"
    S["mm"] = S.mm.fillna("").astype(str) if "mm" in S else ""
    if "hold" in S: S = S[S.hold.fillna("").astype(str) == ""].copy()   # tick-hold injection runs are scored separately (hold_injection.csv)
    S["THD_rise_pp"] = S.THD50_dur_pct - S.THD50_pre_pct
    return S


def unified():
    U = pd.read_csv(RUNS / "detector_unified/unified.csv"); U = U[U.priority_rule == True]  # noqa: E712
    order = ["rf_teacher", "mlp_float", "mlp_float_kd", "mlp_q_deployed", "joint_residual"]; sets = ["holdout", "phase1", "random20"]
    U["model"] = pd.Categorical(U.model, order); U["test_set"] = pd.Categorical(U.test_set, sets); U = U.sort_values(["model", "test_set"])
    cols = ["model", "test_set", "runs", "attacked", "any_pct", "exact_pct", "lat_cycles_median", "lat_ms_median", "lat_ms_max", "cycle_precision", "cycle_recall", "fa_pre_cycles", "fa_post_cycles", "benign_runs_alarm"]
    U[cols].to_csv(OUT / "unified_summary.csv", index=False)
    D = U[U.model == "mlp_q_deployed"]; rows = []
    for _, r in D.iterrows():
        for c in CH:
            rows.append(dict(test_set=r.test_set, channel=c, precision=r[f"prec_{c}"], recall=r[f"rec_{c}"]))
    pd.DataFrame(rows).to_csv(OUT / "unified_channels.csv", index=False)
    # attribution breakdown per model / test set: exact, superset (every attacked channel flagged plus others), partial (some attacked channels), miss
    rows = []
    for m in order:
        for s in sets:
            f = RUNS / f"detector_unified/runs_{m}_{s}.csv"
            if not f.exists():
                continue
            Rr = pd.read_csv(f); Rr = Rr[Rr.attacked == 1]
            tr = Rr.truth.map(lambda x: set(x.split("+"))); de = Rr.detected.map(lambda x: set() if x == "none" else set(x.split("+")))
            ex = np.array([t == d for t, d in zip(tr, de)]); sup = ~ex & np.array([t <= d for t, d in zip(tr, de)]); miss = np.array([len(t & d) == 0 for t, d in zip(tr, de)]); part = ~ex & ~sup & ~miss
            rows.append(dict(model=m, test_set=s, attacked=len(Rr), exact=int(ex.sum()), superset=int(sup.sum()), partial=int(part.sum()), miss=int(miss.sum()), truth_subset_of_flagged_pct=100 * (ex | sup).mean()))
    pd.DataFrame(rows).to_csv(OUT / "unified_breakdown.csv", index=False)
    Rn = pd.read_csv(RUNS / "detector_unified/runs_mlp_q_deployed_phase1.csv"); Rn = Rn[Rn.attacked == 1]
    C = Rn.groupby(["truth", "detected"]).size().reset_index(name="runs").sort_values(["truth", "runs"], ascending=[True, False]); C.to_csv(OUT / "unified_confusion.csv", index=False)
    # figure: any / exact per model and test set
    fig, axs = plt.subplots(1, 3, figsize=(14, 3.8)); w = 0.26; lab = {"rf_teacher": "RF teacher", "mlp_float": "MLP float", "mlp_float_kd": "MLP float, distilled", "mlp_q_deployed": "MLP quantised (deployed)", "joint_residual": "joint residual"}
    for k, (m, t) in enumerate([("any_pct", "any attacked channel flagged [%]"), ("exact_pct", "exact channel set [%]"), ("cycle_precision", "per-cycle channel precision [%]")]):
        for j, s in enumerate(sets):
            q = U[U.test_set == s].set_index("model").reindex(order)
            axs[k].bar(np.arange(len(order)) + (j - 1) * w, q[m], w, label={"holdout": "hold-out (72 runs)", "phase1": "benchmark (104 runs)", "random20": "random (20 runs)"}[s])
        axs[k].set_xticks(range(len(order))); axs[k].set_xticklabels([lab[o] for o in order], rotation=25, ha="right", fontsize=8); axs[k].set_ylabel(t); axs[k].set_ylim(0, 105); axs[k].grid(axis="y", alpha=0.3)
    axs[0].legend(fontsize=8); fig.suptitle("unified detector evaluation (2-cycle persistence, 0.6 hysteresis, Vdc priority)"); fig.tight_layout(); fig.savefig(OUT / "fig29_unified_detector.png", dpi=150)
    return U


def rt_sched():
    S = pd.read_csv(RUNS / "hil_report/h6_run1/rt_sched_summary.csv"); rows = []
    for t in ["mpcc", "detector", "estimator"]:
        q = S[S.task == t].set_index("quantity"); n = int(q.loc["service", "n"])
        rows.append(dict(task=t, period_us=BUDGET[t], n=n, jitter_p99_us=q.loc["release_jitter", "p99_us"], jitter_max_us=q.loc["release_jitter", "max_us"],
                         service_median_us=q.loc["service", "median_us"], service_p99_us=q.loc["service", "p99_us"], service_max_us=q.loc["service", "max_us"],
                         pl_median_us=q.loc["pl", "median_us"], pl_p99_us=q.loc["pl", "p99_us"], pl_max_us=q.loc["pl", "max_us"],
                         e2e_p99_us=q.loc["end_to_end", "p99_us"], e2e_max_us=q.loc["end_to_end", "max_us"], late=int(q.loc["late", "n"]), dropped=int(q.loc["dropped", "n"]),
                         late_ppm=1e6 * q.loc["late", "n"] / n, dropped_ppm=1e6 * q.loc["dropped", "n"] / n))
    D = pd.DataFrame(rows); D.to_csv(OUT / "rt_sched.csv", index=False)
    C = pd.read_csv(RUNS / "hil_report/h6_run1/rt_c_det.csv"); rows = []
    for c, lab in [("buf_write_us", "2400-word feature buffer write (PS -> BRAM)"), ("feat_us", "emi_feat IP (ap_start -> ap_done)"), ("det_us", "detector IP (ap_start -> ap_done)"), ("total_us", "total per 20 ms cycle")]:
        rows.append(dict(stage=lab, n=len(C), median_us=C[c].median(), p99_us=C[c].quantile(0.99), max_us=C[c].max()))
    pd.DataFrame(rows).to_csv(OUT / "det_path.csv", index=False)
    M = pd.read_csv(RUNS / "hil_report/h6_run1/rt_sched_mpcc.csv") if (RUNS / "hil_report/h6_run1/rt_sched_mpcc.csv").exists() else None
    if M is not None and "service_us" in M:
        fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
        ax[0].hist(M.service_us.clip(upper=60), bins=120, color="#4a7fb5"); ax[0].set_yscale("log"); ax[0].axvline(50, color="r", ls="--", label="50 us period"); ax[0].set_xlabel("mpcc_r service time under concurrent load [us]"); ax[0].set_ylabel("ticks"); ax[0].legend()
        if "pl_us" in M:
            ax[1].hist(M.pl_us.clip(upper=60), bins=120, color="#8e5ea2"); ax[1].set_yscale("log"); ax[1].set_xlabel("mpcc_r PL time (axi_timer) under concurrent load [us]"); ax[1].set_ylabel("ticks")
        fig.tight_layout(); fig.savefig(OUT / "fig30_rt_sched.png", dpi=150)
    return D


def power():
    P = pd.read_csv(RUNS / "hil_report/h6_run1/power2.csv"); rows = []
    for tag, lab in [("ctrl_only_idle", "controller-only bitstream, idle"), ("ctrl_only_active", "controller-only bitstream, mpcc_r loop"), ("full_idle", "full bitstream, idle"), ("full_active", "full bitstream, three loops")]:
        q = P[P.tag == tag]; rows.append(dict(configuration=lab, n=len(q), P12V_mean_W=q["12V"].mean(), P12V_max_W=q["12V"].max(), INT_mean_W=q.INT.mean(), INT_max_W=q.INT.max(), P1V2_W=q["1V2"].mean(), P1V8_W=q["1V8"].mean(), P3V3_W=q["3V3"].mean()))
    D = pd.DataFrame(rows)
    D.loc[len(D)] = dict(configuration="defence increment, idle", n=0, P12V_mean_W=D.P12V_mean_W[2] - D.P12V_mean_W[0], P12V_max_W=np.nan, INT_mean_W=D.INT_mean_W[2] - D.INT_mean_W[0], INT_max_W=np.nan, P1V2_W=np.nan, P1V8_W=np.nan, P3V3_W=np.nan)
    D.loc[len(D)] = dict(configuration="defence increment, active", n=0, P12V_mean_W=D.P12V_mean_W[3] - D.P12V_mean_W[1], P12V_max_W=np.nan, INT_mean_W=D.INT_mean_W[3] - D.INT_mean_W[1], INT_max_W=np.nan, P1V2_W=np.nan, P1V8_W=np.nan, P3V3_W=np.nan)
    D.to_csv(OUT / "power_baseline.csv", index=False); return D


def power_error(S):
    Q = S[S.test_id.isin(P1P2) & (S.op == "cc") & (S.mm == "") & S.VARIANT_NAME.isin(["MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_B"])].copy()
    Q["err_pp"] = Q.power_retention_pct - 100.0; Q["abs_err_kW"] = (Q.P_charge_dur_kW - Q.P_charge_pre_kW).abs(); Q["uncompensated"] = Q.test_id.isin(["E-BAT-01b", "E-BAT-01n"])
    piv = Q.pivot_table(index="test_id", columns="VARIANT_NAME", values="err_pp", aggfunc="first").reindex(P1P2)
    piv.columns = [f"{c}_err_pp" for c in piv.columns]; piv["target_kW"] = Q.groupby("test_id").P_charge_pre_kW.first().reindex(P1P2); piv["uncompensated_chain"] = piv.index.isin(["E-BAT-01b", "E-BAT-01n"])
    piv.reset_index().to_csv(OUT / "power_error.csv", index=False)
    rows = []
    for v in ["MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_B"]:
        for sub, lab in [(Q[Q.VARIANT_NAME == v], "all 13"), (Q[(Q.VARIANT_NAME == v) & ~Q.uncompensated], "11 compensable")]:
            if sub.empty:
                continue
            w = sub.loc[sub.err_pp.abs().idxmax()]
            rows.append(dict(controller=v, cases=lab, n=len(sub), mean_abs_err_pp=sub.err_pp.abs().mean(), median_abs_err_pp=sub.err_pp.abs().median(), within_1pp_pct=100 * (sub.err_pp.abs() <= 1).mean(), within_5pp_pct=100 * (sub.err_pp.abs() <= 5).mean(),
                             worst_case=w.test_id, worst_err_pp=w.err_pp, trips=int((sub.trip > 0).sum())))
    D = pd.DataFrame(rows); D.to_csv(OUT / "power_error_summary.csv", index=False); return D


def trips(S):
    Q = S[S.test_id.isin(P1P2) & (S.op == "cc") & (S.mm == "") & S.VARIANT_NAME.isin(["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_H1", "MPCC_R", "MPCC_R_OR", "MPCC_R_B"]) & (S.trip > 0)].copy()
    Q["trip_code"] = Q.trip.map(lambda v: TRIP.get(int(v), str(v)))
    D = Q[["test_id", "VARIANT_NAME", "trip_code", "t_trip_ms", "Vdc_over_on_V", "Vdc_under_on_V", "dVdc_V", "power_retention_pct", "t_rec_ms"]].sort_values(["test_id", "VARIANT_NAME"])
    D.to_csv(OUT / "trip_events.csv", index=False); return D


def delayed_oracle(S):
    vs = ["MPCC_R", "MPCC_R_OR", "MPCC_R_OR1", "MPCC_R_OR2", "MPCC_R_OR3"]
    Q = S[S.test_id.isin(P1P2) & (S.op == "cc") & (S.mm == "") & S.VARIANT_NAME.isin(vs)]
    if Q.VARIANT_NAME.nunique() < 3:
        return None
    piv = Q.pivot_table(index="test_id", columns="VARIANT_NAME", values=["power_retention_pct", "dVdc_V", "THD_rise_pp", "trip", "t_rec_ms"], aggfunc="first").reindex(P1P2)
    piv.columns = [f"{v}_{m}" for m, v in piv.columns]; piv.reset_index().to_csv(OUT / "delayed_oracle.csv", index=False)
    rows = []
    for v in vs:
        q = Q[Q.VARIANT_NAME == v]
        rows.append(dict(variant=v, delay_cycles={"MPCC_R": "detector", "MPCC_R_OR": 0, "MPCC_R_OR1": 1, "MPCC_R_OR2": 2, "MPCC_R_OR3": 3}[v], n=len(q), power_mean=q.power_retention_pct.mean(), abs_err_mean_pp=(q.power_retention_pct - 100).abs().mean(),
                         bus_abs_mean=q.dVdc_V.abs().mean(), bus_abs_max=q.dVdc_V.abs().max(), THD_rise_mean=q.THD_rise_pp.mean(), trips=int((q.trip > 0).sum()), t_rec_mean_ms=q.t_rec_ms.mean()))
    D = pd.DataFrame(rows); D.to_csv(OUT / "delayed_oracle_summary.csv", index=False)
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8)); x = np.arange(len(P1P2)); w = 0.16
    for j, v in enumerate(vs):
        q = Q[Q.VARIANT_NAME == v].set_index("test_id").reindex(P1P2)
        ax[0].bar(x + (j - 2) * w, q.dVdc_V.abs(), w, label=v.replace("MPCC_R", "R")); ax[1].bar(x + (j - 2) * w, q.power_retention_pct, w)
    ax[0].set_yscale("symlog", linthresh=1); ax[0].set_ylabel("|real bus deviation| [V]"); ax[1].set_ylabel("charging power retention [%]")
    for a in ax:
        a.set_xticks(x); a.set_xticklabels(P1P2, rotation=60, fontsize=7)
    ax[0].legend(fontsize=7, ncol=5); fig.suptitle("detector flags vs oracle flags delayed by 0-3 cycles"); fig.tight_layout(); fig.savefig(OUT / "fig31_delayed_oracle.png", dpi=150)
    return D


def mismatch(S):
    cases = ["E-DC-01b", "E-DC-01c", "E-BAT-02b", "E-BAT-02c"]
    Q = S[S.VARIANT_NAME.isin(["MPCC_R", "MPCC_R_BR"]) & (S.op == "cc") & S.test_id.isin(cases)].copy()
    if (Q.mm != "").sum() == 0:
        return None
    lab = {"": "nominal", "eff95": "charger efficiency 0.95", "eff90": "charger efficiency 0.90", "rint150": "battery Rint x1.5", "lchg50": "charger inductance x0.5"}
    Q["plant"] = Q.mm.map(lambda m: lab.get(m, m)); Q["trip_code"] = Q.trip.map(lambda v: TRIP.get(int(v), str(v))); Q["mm_order"] = Q.mm.map({"": 0, "eff95": 1, "eff90": 2, "rint150": 3, "lchg50": 4})
    Q["test_id"] = pd.Categorical(Q.test_id, cases)
    def det_flags(run):
        f = EMI / "ts" / f"{run}_det.csv"
        if not f.exists():
            return "", np.nan
        Dd = pd.read_csv(f); F = Dd[[f"chan_{k}" for k in range(1, 6)]].to_numpy() > 0.5; win = (Dd.t > 0.7) & (Dd.t <= 1.0); pre = Dd.t <= 0.7
        return "+".join(CH[c] for c in np.flatnonzero(F[win].any(0))) or "none", int(F[pre].any(1).sum())
    fl = [det_flags(f"{t}_{v}" + (f"_{m}" if m else "")) for t, v, m in zip(Q.test_id.astype(str), Q.VARIANT_NAME, Q.mm)]
    Q["flagged"] = [a for a, _ in fl]; Q["fa_pre"] = [b for _, b in fl]
    D = Q[["test_id", "VARIANT_NAME", "mm", "plant", "power_retention_pct", "dVdc_V", "Vdc_over_on_V", "Vdc_under_on_V", "THD_rise_pp", "trip_code", "t_rec_ms", "flagged", "fa_pre", "mm_order"]].sort_values(["test_id", "mm_order", "VARIANT_NAME"]).drop(columns="mm_order")
    D.to_csv(OUT / "mismatch.csv", index=False)
    rows = []
    for (v, m), g in Q.groupby(["VARIANT_NAME", "mm"]):
        rows.append(dict(variant=v, mm=m or "nominal", n=len(g), power_mean=g.power_retention_pct.mean(), abs_err_max_pp=(g.power_retention_pct - 100).abs().max(), bus_abs_mean=g.dVdc_V.abs().mean(), bus_abs_max=g.dVdc_V.abs().max(), trips=int((g.trip > 0).sum())))
    pd.DataFrame(rows).to_csv(OUT / "mismatch_summary.csv", index=False)
    # nominal 13-case comparison MPCC_R vs MPCC_R_BR (when the BR runs exist)
    N = S[S.test_id.isin(P1P2) & (S.op == "cc") & (S.mm == "") & S.VARIANT_NAME.isin(["MPCC_R", "MPCC_R_BR"])]
    if (N.VARIANT_NAME == "MPCC_R_BR").any():
        piv = N.pivot_table(index="test_id", columns="VARIANT_NAME", values=["power_retention_pct", "dVdc_V", "THD_rise_pp", "trip", "t_rec_ms"], aggfunc="first").reindex(P1P2)
        piv.columns = [f"{v}_{m}" for m, v in piv.columns]; piv.reset_index().to_csv(OUT / "br_cases.csv", index=False)
    return D


def benign_paired():
    B = v6map(pd.read_csv(EMI / "benign/scorecard.csv")); B = B[B.status == "OK"]
    if "mm" in B: B = B[B.mm.fillna("").astype(str).isin(["", "nan"])]   # mismatch-plant no-attack runs are a separate study (mk_mmbenign.py)
    vs = ["MPCC_D_H1", "MPCC_R", "MPCC_R_P1"] + (["MPCC_R_BR"] if (B.VARIANT_NAME == "MPCC_R_BR").any() else [])
    rows = []
    for t, g in B.groupby("test_id"):
        row = dict(test_id=t, disturbance=g.benign_desc.iloc[0] if "benign_desc" in g else "")
        for v in vs:
            q = g[g.VARIANT_NAME == v]
            if q.empty:
                continue
            q = q.iloc[0]; row[f"{v}_fa"] = q.fa_cycles; row[f"{v}_t_first"] = q.t_first_fa; row[f"{v}_trip"] = TRIP.get(int(q.trip), ""); row[f"{v}_P_kW"] = q.P_charge_dur_kW; row[f"{v}_dVdc"] = q.dVdc_V; row[f"{v}_THD"] = q.THD50_dur_pct
        rows.append(row)
    D = pd.DataFrame(rows); D.to_csv(OUT / "benign_paired.csv", index=False)
    rows = []
    for v in vs:
        q = B[B.VARIANT_NAME == v]
        rows.append(dict(variant=v, runs=len(q), runs_with_alarm=int((q.fa_cycles > 0).sum()), alarm_cycles=int(q.fa_cycles.sum()), of_cycles=35 * len(q), trips=int((q.trip > 0).sum()), P_min_kW=q.P_charge_dur_kW.min(), bus_abs_max=q.dVdc_V.abs().max()))
    pd.DataFrame(rows).to_csv(OUT / "benign_summary.csv", index=False)
    # paired false-alarm figure: three configurations on the same disturbances, stacked per channel
    ids = list(D.test_id); x = np.arange(len(ids)); w = 0.26
    fig, ax = plt.subplots(figsize=(11, 4.0))
    for j, (v, hatch) in enumerate(zip(vs[:3], ["", "//", ".."])):
        bottom = np.zeros(len(ids))
        for c, col in zip(CH, ["#4a7fb5", "#c97b3a", "#6aa84f", "#8e5ea2", "#e0a800"]):
            h = np.array([B[(B.test_id == t) & (B.VARIANT_NAME == v)][f"fa_{c}"].sum() for t in ids], float)
            ax.bar(x + (j - 1) * w, h, w, bottom=bottom, color=col, hatch=hatch, edgecolor="white", linewidth=0.3, label=c if j == 0 else None)
            bottom += h
    ax.set_xticks(x); ax.set_xticklabels(ids, rotation=45, ha="right", fontsize=8); ax.set_ylabel("flagged cycles (of 35)")
    ax.set_title("false alarms on the no-attack disturbances: MPCC-H (left, plain), MPCC-R (centre, hatched), MPCC-R-P1 (right, dotted)")
    ax.legend(fontsize=8, ncol=5); fig.tight_layout(); fig.savefig(OUT / "fig23b_benign_paired.png", dpi=150)
    return D


def main():
    OUT.mkdir(parents=True, exist_ok=True); pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    S = scorecard()
    print("== unified"); print(unified().round(1).to_string(index=False))
    print("== rt_sched"); print(rt_sched().round(2).to_string(index=False))
    print("== power"); print(power().round(3).to_string(index=False))
    import traceback
    for name, fn in [("power error", lambda: power_error(S)), ("trips", lambda: trips(S)), ("delayed oracle", lambda: delayed_oracle(S)), ("mismatch", lambda: mismatch(S)), ("benign paired", benign_paired)]:
        print(f"== {name}")
        try:
            D = fn(); print(D.round(2).to_string(index=False) if D is not None else "(not yet)")
        except Exception as e:   # partial run sets (v6 tiers still running): report and continue with the remaining sections
            print(f"(skipped: {type(e).__name__}: {e})"); traceback.print_exc(limit=1)


if __name__ == "__main__":
    main()
