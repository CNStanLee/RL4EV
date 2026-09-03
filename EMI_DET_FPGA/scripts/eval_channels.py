"""Per-channel (multi-label) detection evaluation with leave-run-out CV.

    python scripts/eval_channels.py data/cycles_dataset_interim.npz --labels <labels.csv> [--abs] [--folds 5]

Five one-vs-rest random forests (Vdc, Vac, Iac, Vbat, Ibat).  A run counts as
detected when the injected channel(s) are flagged on >= 50 % of the injected
steady cycles.  --abs uses only the absolute features (first 41 columns) to
quantify the benefit of the baseline-relative block.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("npz"); ap.add_argument("--labels", required=True); ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--abs", action="store_true"); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fa-budget", type=float, default=0.01, help="max false-alarm fraction on clean cycles per channel")
    args = ap.parse_args()
    d = np.load(args.npz, allow_pickle=True)
    X = np.nan_to_num(d["X"], nan=0.0, posinf=1e6, neginf=-1e6)
    n_base = len([n for n in d["feature_names"] if not str(n).startswith("d_") and not str(n).startswith("is_")]) if "feature_names" in d else 43
    if args.abs:
        X = X[:, :n_base]
    ych = d["ych"]; tr = d["tr"]; t = d["t"]; t_on = d["t_on"]; run_id = d["run_id"]
    L = pd.read_csv(args.labels).set_index("run_id")
    PR = np.zeros(ych.shape, float)
    for itr, ite in GroupKFold(n_splits=args.folds).split(X, ych[:, 0], run_id):
        m = np.zeros(len(t), bool); m[itr] = True; m &= tr == 0
        for c in range(5):
            if ych[m, c].sum() == 0:
                continue
            clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample", random_state=args.seed, n_jobs=-1)
            clf.fit(X[m], ych[m, c]); PR[ite, c] = clf.predict_proba(X[ite])[:, 1]
    steady = tr == 0
    # per-channel threshold: highest recall subject to <= fa_budget false alarms on clean steady cycles
    clean0 = steady & (ych.sum(1) == 0); thr = np.full(5, 0.5)
    for c in range(5):
        cand = np.linspace(0.05, 0.95, 19)
        ok = [q for q in cand if (PR[clean0, c] >= q).mean() <= args.fa_budget]
        thr[c] = min(ok) if ok else 0.95
    print("thresholds (FA budget %.3f):" % args.fa_budget, np.round(thr, 2))
    P = (PR >= thr).astype(int)
    print(f"{'channel':6s} {'prec':>6s} {'recall':>6s} {'support':>8s}   (steady cycles)")
    for c in range(5):
        tp = int(((P[:, c] == 1) & (ych[:, c] == 1) & steady).sum()); fp = int(((P[:, c] == 1) & (ych[:, c] == 0) & steady).sum())
        fn = int(((P[:, c] == 0) & (ych[:, c] == 1) & steady).sum())
        print(f"{CH[c]:6s} {tp / max(tp + fp, 1):6.3f} {tp / max(tp + fn, 1):6.3f} {tp + fn:8d}")
    clean = steady & (ych.sum(1) == 0)
    print(f"false alarms on clean cycles (any channel): {int((P[clean].sum(1) > 0).sum())} / {int(clean.sum())}")
    rows = []
    for r in np.unique(run_id):
        m = run_id == r; inj = m & steady & (ych.sum(1) > 0)
        if not inj.any():
            continue
        chans = [c for c in range(5) if ych[m, c].any()]
        hit = min(float(P[inj, c].mean()) for c in chans)
        after = m & (t > t_on[m][0]); ok = np.where(np.all(P[after][:, chans] == 1, axis=1))[0]
        lat = int(round((t[after][ok[0]] - t_on[m][0]) / 0.02)) if ok.size else np.inf
        lab = L.loc[r] if r in L.index else None
        amp = float(lab["amp1"]) if lab is not None else np.nan; sh = str(lab["shape1"]) if lab is not None else ""
        rows.append(dict(run=r, ch="+".join(CH[c] for c in chans), shape=sh, amp=amp, hit=hit, lat=lat))
    T = pd.DataFrame(rows).sort_values(["ch", "amp"])
    pd.set_option("display.width", 200)
    print(T.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    det = (T.hit >= 0.5).sum()
    print(f"\nruns detected (>=50 % of injected cycles): {det} / {len(T)};  median latency {np.median(T.lat[np.isfinite(T.lat)]) if np.isfinite(T.lat).any() else 'n/a'} cycles")
    for c in CH:
        s = T[T.ch.str.contains(c)]
        if len(s):
            print(f"  {c:5s} runs {len(s):3d} detected {(s.hit >= 0.5).sum():3d}  |amp| detected median {np.median(np.abs(s.amp[s.hit >= 0.5])) if (s.hit >= 0.5).any() else float('nan'):.1f}  missed median {np.median(np.abs(s.amp[s.hit < 0.5])) if (s.hit < 0.5).any() else float('nan'):.1f}")


if __name__ == "__main__":
    main()
