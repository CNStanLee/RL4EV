"""Quick separability check of the per-cycle features with scikit-learn.

    python scripts/quick_eval.py data/cycles_phase1.npz [--holdout-variant MPCC_D_R]

Run-wise split (no cycle of a test run is seen in training).  Reports per-class
precision / recall on steady cycles, false alarms on 'none' cycles, and the
detection latency in cycles from injection onset per run.
"""

from __future__ import annotations

import argparse

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit


def latency(pred: np.ndarray, y: np.ndarray, t: np.ndarray, t_on: np.ndarray, run_id: np.ndarray) -> dict:
    out = {}
    for r in np.unique(run_id):
        m = run_id == r
        cls = y[m][y[m] != 0]
        if cls.size == 0:
            continue
        c = cls[0]; ton = t_on[m][0]
        after = m & (t > ton)
        hits = np.where(pred[after] == c)[0]
        if hits.size == 0:
            out[r] = np.inf
        else:
            out[r] = int(np.round((t[after][hits[0]] - ton) / 0.02))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("npz"); ap.add_argument("--holdout-variant", default=None)
    ap.add_argument("--test-frac", type=float, default=0.3); ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    d = np.load(args.npz, allow_pickle=True)
    X, y, tr, t, t_on = d["X"], d["y"], d["tr"], d["t"], d["t_on"]
    run_id, variant, classes = d["run_id"], d["variant"], list(d["classes"])
    X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)
    groups = np.array([f"{r}" for r in run_id])
    if args.holdout_variant:
        te = variant == args.holdout_variant; trn = ~te
    else:
        gss = GroupShuffleSplit(n_splits=1, test_size=args.test_frac, random_state=args.seed)
        trn, te = next(gss.split(X, y, groups)); m = np.zeros(len(y), bool); m[te] = True; te = m; trn = ~te
    clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample",
                                 random_state=args.seed, n_jobs=-1)
    clf.fit(X[trn & (tr == 0)], y[trn & (tr == 0)])
    pred = clf.predict(X)
    steady = te & (tr == 0)
    print(f"train cycles {int((trn & (tr == 0)).sum())}, test steady cycles {int(steady.sum())}, "
          f"test runs {len(np.unique(run_id[te]))}")
    present = sorted(set(y[steady]) | set(pred[steady]))
    print(classification_report(y[steady], pred[steady], labels=present, target_names=[classes[i] for i in present], zero_division=0))
    cm = confusion_matrix(y[steady], pred[steady], labels=present)
    print("confusion (rows = true):"); print("          " + " ".join(f"{classes[i][:7]:>7s}" for i in present))
    for i, row in zip(present, cm):
        print(f"{classes[i]:9s} " + " ".join(f"{v:7d}" for v in row))
    none_te = te & (y == 0) & (tr == 0)
    print(f"false alarms on 'none' test cycles: {int((pred[none_te] != 0).sum())} / {int(none_te.sum())}")
    lat = latency(pred[te], y[te], t[te], t_on[te], run_id[te])
    if lat:
        v = np.array(list(lat.values()))
        print(f"detection latency (cycles) over {len(v)} test runs: median {np.median(v[np.isfinite(v)]) if np.isfinite(v).any() else 'n/a'}, "
              f"max {v[np.isfinite(v)].max() if np.isfinite(v).any() else 'n/a'}, missed {int(np.isinf(v).sum())}")
    imp = clf.feature_importances_; names = d["feature_names"]
    top = np.argsort(imp)[::-1][:12]
    print("top features: " + ", ".join(f"{names[i]}({imp[i]:.2f})" for i in top))


if __name__ == "__main__":
    main()
