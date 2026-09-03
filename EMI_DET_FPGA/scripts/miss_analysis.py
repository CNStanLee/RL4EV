"""Which injected runs does a run-wise random forest miss, and why?

    python scripts/miss_analysis.py data/cycles_dataset_interim.npz --labels <labels.csv> [--seed 0]

Per test run: true class, first-injection channel/shape/amplitude, cycles of
injection, fraction of injected steady cycles predicted as the true class, the
majority predicted class, and detection latency.  Also a per-class recall vs
|amplitude| table (binned) using leave-run-out cross-validation.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("npz"); ap.add_argument("--labels", required=True); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()
    d = np.load(args.npz, allow_pickle=True)
    X = np.nan_to_num(d["X"], nan=0.0, posinf=1e6, neginf=-1e6); y = d["y"]; tr = d["tr"]; t = d["t"]; t_on = d["t_on"]
    run_id = d["run_id"]; classes = list(d["classes"])
    L = pd.read_csv(args.labels).set_index("run_id")
    pred = np.zeros_like(y)
    gkf = GroupKFold(n_splits=args.folds)
    for itr, ite in gkf.split(X, y, run_id):
        m = np.zeros(len(y), bool); m[itr] = True; m &= tr == 0
        clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample", random_state=args.seed, n_jobs=-1)
        clf.fit(X[m], y[m]); pred[ite] = clf.predict(X[ite])
    rows = []
    for r in np.unique(run_id):
        m = run_id == r; c = y[m][y[m] != 0]
        if c.size == 0:
            fa = int((pred[m & (tr == 0)] != 0).sum()); rows.append(dict(run=r, cls="none", ch="", sh="", amp=0.0, n_inj_cyc=0, hit_frac=np.nan, maj="", lat=np.nan, fa=fa)); continue
        c = c[0]; inj = m & (y == c) & (tr == 0)
        hit = float((pred[inj] == c).mean()) if inj.any() else np.nan
        maj = classes[np.bincount(pred[inj], minlength=len(classes)).argmax()] if inj.any() else ""
        after = m & (t > t_on[m][0]); h = np.where(pred[after] == c)[0]
        lat = int(round((t[after][h[0]] - t_on[m][0]) / 0.02)) if h.size else np.inf
        lab = L.loc[r] if r in L.index else None
        ch = str(lab["channel1"]) if lab is not None else ""; sh = str(lab["shape1"]) if lab is not None else ""
        amp = float(lab["amp1"]) if lab is not None else np.nan
        fa = int((pred[m & (y == 0) & (tr == 0)] != 0).sum())
        rows.append(dict(run=r, cls=classes[c], ch=ch, sh=sh, amp=amp, n_inj_cyc=int(inj.sum()), hit_frac=hit, maj=maj, lat=lat, fa=fa))
    T = pd.DataFrame(rows)
    pd.set_option("display.width", 200); pd.set_option("display.max_rows", 500)
    inj = T[T.cls != "none"].sort_values(["cls", "amp"])
    print(inj.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("\nnone-only runs: false alarm cycles per run:", T[T.cls == "none"].fa.tolist())
    print("\nmissed (hit_frac < 0.5):", int((inj.hit_frac < 0.5).sum()), "of", len(inj))
    print("median latency (detected):", np.median(inj.lat[np.isfinite(inj.lat)]) if np.isfinite(inj.lat).any() else "n/a")


if __name__ == "__main__":
    main()
