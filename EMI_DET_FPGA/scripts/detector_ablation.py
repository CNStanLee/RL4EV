"""Offline detector analyses for the paper (2026-09-06): feature-group ablation, simple residual baselines,
per-channel confusion, detection-latency distribution, float vs quantised cost.

    python detector_ablation.py --data data/cycles_v3_all.npz --out runs/detector_ablation [--seed 0] [--test-frac 0.25]

Run-level protocol (same rule as the deployed detector): a channel is flagged when its per-cycle score exceeds the
threshold on `persist` consecutive cycles; a run detects a channel if it is flagged inside the injection window;
latency = flagged cycle - first attacked cycle; a false alarm is any flag outside the window (or in a benign run).
Thresholds per channel are set on the training split for a 1 % pre-injection false-alarm budget.
Models: random forest (multi-output, the teacher of the deployed MLP) trained on feature subsets; baselines are
single-residual detectors (power-balance ratio, bus/charger cross-check, current DC component, bus error) with the
same persistence rule.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
GROUPS = {
    "power_balance": ["p_ac_int", "p_chg_int", "p_ratio", "xchk_vdc", "vbat_mismatch", "d_p_ratio"],
    "spectral": ["iac_h1", "iac_h2", "iac_h3", "iac_dc_over_h1", "iac_phase_vs_theta", "vdc_h1", "vdc_h1_over_h2", "vdc_h1_phase", "vdc_ripple", "iac_ref_corr"],
}
BASELINES = {                     # residual, sign handled by |z|; channel the alarm is attributed to
    "power_ratio": ("p_ratio", None),
    "xchk_vdc": ("xchk_vdc", "Vdc"),
    "vbat_mismatch": ("vbat_mismatch", "Vbat"),
    "iac_dc": ("iac_mean", "Iac"),
    "vdc_err": ("vdc_err", "Vdc"),
    "vac_mean": ("vac_mean", "Vac"),
}


def run_level(score, thr, persist, runs, t, t_on, t_off, ych):
    """score: (N, 5) per-cycle scores; returns per-run records."""
    recs = []
    for r in np.unique(runs):
        m = runs == r; idx = np.flatnonzero(m); idx = idx[np.argsort(t[idx])]
        on = t_on[idx[0]]; off = t_off[idx[0]]; tt = t[idx]
        truth = set(np.flatnonzero(ych[idx].any(0)))
        win = (tt >= on) & (tt < off + 0.02) if np.isfinite(on) and on > 0 else np.zeros(len(idx), bool)
        rec = dict(run=r, truth="+".join(CH[c] for c in sorted(truth)) or "none", n_cycles=len(idx))
        det = set(); lat = {}; fa_pre = 0; fa_post = 0; fa_benign = 0
        for c in range(5):
            above = score[idx, c] >= thr[c]; cnt = 0; flag = np.zeros(len(idx), bool)
            for i, a in enumerate(above):
                cnt = cnt + 1 if a else 0; flag[i] = cnt >= persist
            if win.any():
                first_on = np.flatnonzero(win)[0]
                hit = np.flatnonzero(flag & win)
                if hit.size:
                    det.add(c); lat[c] = int(hit[0] - first_on)
                fa_pre += int(flag[:first_on].sum()); fa_post += int(flag[np.flatnonzero(win)[-1] + 1:].sum())
            else:
                fa_benign += int(flag.sum())
        rec.update(detected="+".join(CH[c] for c in sorted(det)) or "none", hit=int(len(truth) > 0 and truth <= det), any_hit=int(len(truth) > 0 and len(det & truth) > 0),
                   latency_cycles=min(lat.values()) if lat else np.nan, fa_pre=fa_pre, fa_post=fa_post, fa_benign=fa_benign, benign=int(len(truth) == 0))
        for c in range(5):
            rec[f"lat_{CH[c]}"] = lat.get(c, np.nan)
        recs.append(rec)
    return pd.DataFrame(recs)


def thresholds(score_tr, ych_tr, pre_mask_tr, budget):
    """per-channel threshold: quantile of the benign / pre-injection cycles giving `budget` false alarms per cycle."""
    thr = np.zeros(5)
    for c in range(5):
        neg = score_tr[pre_mask_tr & (ych_tr[:, c] == 0), c]
        if neg.size == 0 or np.ptp(score_tr[:, c]) == 0:      # unused / constant score column: never flags
            thr[c] = np.inf; continue
        thr[c] = np.quantile(neg, 1 - budget)
    return thr


def summarize(R, tag, **extra):
    att = R[R.benign == 0]; ben = R[R.benign == 1]
    out = dict(model=tag, runs_attacked=len(att), runs_benign=len(ben),
               detected_any=int(att.any_hit.sum()), detected_exact=int(att.hit.sum()),
               recall_any=att.any_hit.mean() if len(att) else np.nan, recall_exact=att.hit.mean() if len(att) else np.nan,
               latency_median=att.latency_cycles.median(), latency_p90=att.latency_cycles.quantile(0.9),
               fa_pre_cycles=int(att.fa_pre.sum()), fa_post_cycles=int(att.fa_post.sum()), fa_benign_cycles=int(ben.fa_benign.sum()),
               benign_runs_with_alarm=int((ben.fa_benign > 0).sum()))
    for c in CH:
        sub = att[att.truth.str.contains(c)]
        out[f"recall_{c}"] = sub.detected.str.contains(c).mean() if len(sub) else np.nan
        out[f"n_{c}"] = len(sub)
    out.update(extra); return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cycles_v3_all.npz"); ap.add_argument("--out", default="runs/detector_ablation")
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--test-frac", type=float, default=0.25)
    ap.add_argument("--persist", type=int, default=2); ap.add_argument("--fa-budget", type=float, default=0.01)
    ap.add_argument("--v5-report", default="runs/det_v5/report.json")
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Z = np.load(a.data, allow_pickle=True)
    X = Z["X"].astype(np.float64); X = np.where(np.isfinite(X), X, 0.0); ych = Z["ych"].astype(int); runs = Z["run_id"].astype(str)
    t = Z["t"]; t_on = Z["t_on"]; t_off = Z["t_off"]; names = list(Z["feature_names"].astype(str))
    rng = np.random.default_rng(a.seed); ur = np.unique(runs); rng.shuffle(ur)
    test_runs = set(ur[: int(round(a.test_frac * len(ur)))]); te = np.array([r in test_runs for r in runs]); tr = ~te
    pre = ~((t >= t_on) & (t < t_off + 0.02)) | ~(t_on > 0)          # cycles outside the injection window
    print(f"{len(ur)} runs ({len(test_runs)} test), {X.shape[0]} cycles, features {X.shape[1]}")
    rows = []; latencies = {}; confusion = []
    # ---------------- feature-group ablation (random forest, multi-output)
    all_idx = list(range(len(names)))
    grp_idx = {g: [names.index(n) for n in fs if n in names] for g, fs in GROUPS.items()}
    rest = [i for i in all_idx if i not in grp_idx["power_balance"] + grp_idx["spectral"]]
    subsets = {"all_48": all_idx, "power_balance_only": grp_idx["power_balance"], "spectral_only": grp_idx["spectral"],
               "time_domain_only": rest, "power_balance+spectral": grp_idx["power_balance"] + grp_idx["spectral"],
               "without_power_balance": [i for i in all_idx if i not in grp_idx["power_balance"]],
               "without_spectral": [i for i in all_idx if i not in grp_idx["spectral"]]}
    for tag, cols in subsets.items():
        rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, n_jobs=8, random_state=a.seed, class_weight="balanced_subsample")
        rf.fit(X[tr][:, cols], ych[tr])
        P = np.column_stack([p[:, 1] if p.shape[1] > 1 else np.zeros(len(p)) for p in rf.predict_proba(X[:, cols])])
        thr = thresholds(P[tr], ych[tr], pre[tr], a.fa_budget)
        R = run_level(P[te], thr, a.persist, runs[te], t[te], t_on[te], t_off[te], ych[te])
        rows.append(summarize(R, f"rf_{tag}", n_features=len(cols), thr=json.dumps([round(float(x), 3) for x in thr])))
        R.to_csv(out / f"runs_rf_{tag}.csv", index=False)
        if tag == "all_48":
            latencies["rf_all_48"] = R.latency_cycles.dropna().to_numpy()
            for _, rr in R[R.benign == 0].iterrows():
                confusion.append(dict(truth=rr.truth, detected=rr.detected))
        print(f"{tag:28s} recall_exact {rows[-1]['recall_exact']:.3f} any {rows[-1]['recall_any']:.3f} lat {rows[-1]['latency_median']:.1f} fa_pre {rows[-1]['fa_pre_cycles']} benign_alarm_runs {rows[-1]['benign_runs_with_alarm']}")
    # ---------------- single-residual baselines (|z| of one feature, same persistence, same budget)
    for tag, (feat, ch) in BASELINES.items():
        j = names.index(feat); x = X[:, j]
        neg = x[tr & pre]; mu = np.median(neg); sd = max(1.4826 * np.median(np.abs(neg - mu)), 1e-3 * (abs(mu) + np.std(neg)) + 1e-9)
        z = np.abs(x - mu) / sd
        S = np.zeros((len(x), 5))
        if ch is None:
            S[:] = z[:, None]                     # attributed to every channel: "something is wrong" detector
        else:
            S[:, CH.index(ch)] = z
        thr = thresholds(S[tr], ych[tr], pre[tr], a.fa_budget)
        R = run_level(S[te], thr, a.persist, runs[te], t[te], t_on[te], t_off[te], ych[te])
        rows.append(summarize(R, f"baseline_{tag}", n_features=1, thr=json.dumps([round(float(v), 2) for v in thr])))
        latencies[f"baseline_{tag}"] = R.latency_cycles.dropna().to_numpy()
        print(f"{'baseline_' + tag:28s} recall_exact {rows[-1]['recall_exact']:.3f} any {rows[-1]['recall_any']:.3f} lat {rows[-1]['latency_median']:.1f} fa_pre {rows[-1]['fa_pre_cycles']}")
    T = pd.DataFrame(rows); T.to_csv(out / "ablation.csv", index=False)
    # ---------------- confusion (truth channel set vs detected set) for the full model
    C = pd.DataFrame(confusion); C["pair"] = C.truth + " -> " + C.detected
    conf = C.groupby(["truth", "detected"]).size().reset_index(name="runs"); conf.to_csv(out / "confusion.csv", index=False)
    M = np.zeros((6, 6), int)
    for _, rr in C.iterrows():
        for i, c in enumerate(CH + ["none"]):
            if c in rr.truth.split("+"):
                for j, d in enumerate(CH + ["none"]):
                    if d in rr.detected.split("+"):
                        M[i, j] += 1
    pd.DataFrame(M, index=[f"truth_{c}" for c in CH + ["none"]], columns=[f"det_{c}" for c in CH + ["none"]]).to_csv(out / "confusion_matrix.csv")
    # ---------------- latency distribution
    L = pd.DataFrame([dict(model=k, n=len(v), **{f"p{q}": float(np.percentile(v, q)) if len(v) else np.nan for q in (10, 50, 90, 100)}, mean=float(v.mean()) if len(v) else np.nan) for k, v in latencies.items()])
    L.to_csv(out / "latency.csv", index=False)
    # ---------------- float vs quantised (from the v5 training report)
    try:
        rep = json.load(open(a.v5_report)); keys = ["float_test", "q_test", "float_test_rule", "q_test_rule", "float_phase1", "q_phase1", "float_phase1_rule", "q_phase1_rule", "float_amp_test", "q_amp_test"]
        Q = pd.DataFrame([dict(split=k, **{kk: vv for kk, vv in rep[k].items() if not isinstance(vv, (list, dict))}) for k in keys if k in rep])
        Q.to_csv(out / "float_vs_quantised.csv", index=False); print(Q.to_string(index=False))
    except Exception as e:  # noqa: BLE001
        print("v5 report not summarised:", e)
    # figure
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    A = T[T.model.str.startswith("rf_")]; B = T[T.model.str.startswith("baseline_")]
    ax[0].barh(A.model.str.replace("rf_", ""), A.recall_exact, color="#4a7fb5", label="exact channel set"); ax[0].barh(A.model.str.replace("rf_", ""), A.recall_any, color="none", edgecolor="k", label="any attacked channel")
    ax[0].set_xlabel("run-level recall (test runs)"); ax[0].set_title("feature-group ablation (random forest)"); ax[0].legend(fontsize=8); ax[0].set_xlim(0, 1)
    ax[1].barh(B.model.str.replace("baseline_", ""), B.recall_any, color="#c97b3a", label="any"); ax[1].barh(B.model.str.replace("baseline_", ""), B.recall_exact, color="none", edgecolor="k", label="exact")
    ax[1].axvline(A[A.model == "rf_all_48"].recall_any.iloc[0], color="#4a7fb5", ls="--", label="learned detector (any)"); ax[1].set_xlim(0, 1)
    ax[1].set_xlabel("run-level recall"); ax[1].set_title("single-residual baselines, same persistence and FA budget"); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "fig18_detector_ablation.png", dpi=130)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(T[["model", "n_features", "recall_exact", "recall_any", "latency_median", "latency_p90", "fa_pre_cycles", "fa_post_cycles", "benign_runs_with_alarm"] + [f"recall_{c}" for c in CH]].round(3).to_string(index=False))
        print(L.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
