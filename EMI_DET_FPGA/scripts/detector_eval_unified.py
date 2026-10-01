"""Unified detector evaluation (review point 5/6): one protocol, several models, several test sets.

    KERAS_BACKEND=torch python detector_eval_unified.py --out runs/detector_unified

Models
  rf_teacher      random forest (multi-output) trained on the training split of the 288 dataset runs
  mlp_float       keras MLP 48-64-64-10 (standardised inputs), plain labels
  mlp_float_kd    same, distilled from the RF teacher (soft-label weight 0.5, as the deployed model)
  mlp_q_deployed  the deployed bit-exact HGQ ONNX (artifacts/detector_bitexact.onnx)
  joint_residual  logistic regression on six residual z-scores (power ratio, bus/charger cross-check, battery mismatch,
                  current DC, bus error, grid-voltage mean), one-vs-rest per channel
Decision rule (deployed): sigmoid > per-channel threshold for 2 consecutive cycles, clear below 0.6 * thr, Vdc priority.
Test sets
  holdout   run-grouped 25 % of the 288 dataset runs (models trained on the other 75 %; the deployed ONNX was trained on its
            own split of the same runs and is therefore NOT reported on this set)
  phase1    the 104 closed-loop benchmark runs (13 cases x 8 controller variants), never used in training
  random20  the 20 random unseen scenarios (seeds 301-320), never used in training of the deployed model
Metrics: run-level any-channel / exact-set success; per-cycle channel precision / recall inside the attack window;
latency in cycles (grid cycles overlapping the attack up to and including the one at whose end the flag is raised) and in ms from the attack onset to the flag; false-alarm cycles before / after.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
RESID = ["p_ratio", "xchk_vdc", "vbat_mismatch", "iac_mean", "vdc_err", "vac_mean"]


def decide(P, thr, persist, hyst, priority=True):
    """per-cycle scores P (n,5) of ONE run in time order -> flags (n,5) with the deployed rule."""
    n = len(P); flags = np.zeros((n, 5), bool); cnt = np.zeros(5, int); on = np.zeros(5, bool)
    for i in range(n):
        above = P[i] >= thr; below = P[i] < hyst * thr
        cnt = np.where(above, cnt + 1, 0); on = np.where(on, ~below, cnt >= persist)
        f = on.copy()
        if priority and f[0]:
            f[3] = False; f[4] = False
        flags[i] = f
    return flags


def evaluate(score, thr, Z, idx_all, persist=2, hyst=0.6, priority=True):
    """score: (N,5) probabilities aligned with Z rows; idx_all: rows of the test set."""
    runs = Z["run_id"].astype(str); t = Z["t"]; t_on = Z["t_on"]; t_off = Z["t_off"]; ych = Z["ych"].astype(int)
    recs = []; tp = np.zeros(5); fp = np.zeros(5); fn = np.zeros(5)
    for r in np.unique(runs[idx_all]):
        idx = idx_all[runs[idx_all] == r]; idx = idx[np.argsort(t[idx])]
        F = decide(score[idx], thr, persist, hyst, priority); Y = ych[idx] > 0
        on = t_on[idx[0]]; off = t_off[idx[0]]; tt = t[idx]
        attacked = np.isfinite(on) and on > 0
        win = (tt > on + 1e-9) & (tt < off + 0.02) if attacked else np.zeros(len(idx), bool)   # t = end of the cycle; attacked cycles end after t_on
        truth = set(np.flatnonzero(Y.any(0))); attacked = bool(attacked and len(truth) > 0)      # runs without an attacked channel are benign
        win = win if attacked else np.zeros(len(idx), bool); det = set(np.flatnonzero(F[win].any(0))) if attacked else set()
        lat_c = np.nan; lat_ms = np.nan
        if attacked and (F[win] & Y[win]).any(1).any():
            first = np.flatnonzero(win)[0]; hit = np.flatnonzero((F & Y).any(1) & win)[0]
            lat_c = hit - first + 1; lat_ms = 1e3 * (tt[hit] - on)   # cycles overlapping the attack up to the deciding one; ms from onset to the flag (end of that cycle)
        pre = (tt <= on + 1e-9) if attacked else np.ones(len(idx), bool)
        recs.append(dict(run=r, attacked=int(attacked), truth="+".join(CH[c] for c in sorted(truth)) or "none", detected="+".join(CH[c] for c in sorted(det)) or "none",
                         any_hit=int(attacked and len(det & truth) > 0), exact=int(attacked and det == truth), lat_cycles=lat_c, lat_ms=lat_ms,
                         fa_pre=int(F[pre].any(1).sum()), fa_post=int(F[~pre & ~win].any(1).sum()) if attacked else 0))
        if attacked:
            tp += (F[win] & Y[win]).sum(0); fp += (F[win] & ~Y[win]).sum(0); fn += (~F[win] & Y[win]).sum(0)
    R = pd.DataFrame(recs); A = R[R.attacked == 1]
    out = dict(runs=len(R), attacked=len(A), any_pct=100 * A.any_hit.mean(), exact_pct=100 * A.exact.mean(), lat_cycles_median=A.lat_cycles.median(), lat_cycles_p90=A.lat_cycles.quantile(0.9),
               lat_ms_median=A.lat_ms.median(), lat_ms_max=A.lat_ms.max(), fa_pre_cycles=int(R.fa_pre.sum()), fa_post_cycles=int(A.fa_post.sum()), benign_runs_alarm=int((R[R.attacked == 0].fa_pre > 0).sum()))
    for c in range(5):
        out[f"prec_{CH[c]}"] = 100 * tp[c] / max(tp[c] + fp[c], 1); out[f"rec_{CH[c]}"] = 100 * tp[c] / max(tp[c] + fn[c], 1)
    out["cycle_precision"] = 100 * tp.sum() / max(tp.sum() + fp.sum(), 1); out["cycle_recall"] = 100 * tp.sum() / max(tp.sum() + fn.sum(), 1)
    return out, R


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="runs/detector_unified"); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--epochs", type=int, default=150)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Zall = np.load("data/cycles_v3_all.npz", allow_pickle=True); Zp = np.load("data/cycles_v3_phase1.npz", allow_pickle=True)
    names = list(Zall["feature_names"].astype(str)); cfg = json.load(open("artifacts/detector.json"))
    thr = np.array(cfg["thr"]); persist = int(cfg["persist"]); hyst = float(cfg["hyst"]); mu = np.array(cfg["mu"]); sd = np.array(cfg.get("sd", cfg.get("std", np.ones(48))))
    ra = Zall["run_id"].astype(str); is_rand = np.array([r >= "D0301" for r in ra]); ds_idx = np.flatnonzero(~is_rand); rand_idx = np.flatnonzero(is_rand)
    # run-grouped split of the 288 dataset runs
    rng = np.random.default_rng(a.seed); ur = np.unique(ra[ds_idx]); rng.shuffle(ur); test_runs = set(ur[: int(round(0.25 * len(ur)))])
    te = np.array([r in test_runs for r in ra]) & ~is_rand; tr = ~te & ~is_rand
    Xa = np.where(np.isfinite(Zall["X"]), Zall["X"], mu); Xp = np.where(np.isfinite(Zp["X"]), Zp["X"], mu)
    ya = Zall["ych"].astype(int); yp = Zp["ych"].astype(int)
    stand = lambda X: (X - mu) / np.where(sd > 0, sd, 1.0)
    models = {}
    # ---- RF teacher
    from sklearn.ensemble import RandomForestClassifier
    rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=2, n_jobs=8, random_state=a.seed, class_weight="balanced_subsample").fit(Xa[tr], ya[tr])
    rf_prob = lambda X: np.column_stack([p[:, 1] if p.shape[1] > 1 else np.zeros(len(p)) for p in rf.predict_proba(X)])
    models["rf_teacher"] = rf_prob
    # ---- float MLPs (keras, torch backend)
    os.environ.setdefault("KERAS_BACKEND", "torch")
    import keras
    def train_mlp(soft=None, tag="float"):
        keras.utils.set_random_seed(a.seed)
        inp = keras.Input((48,)); x = inp
        for i, w in enumerate((64, 64)):
            x = keras.layers.Dense(w, activation="relu", name=f"dense{i}")(x)
        h = keras.layers.Dense(10, name="head")(x); m = keras.Model(inp, h)
        Ztr = stand(Xa[tr]).astype(np.float32); ytr = ya[tr].astype(np.float32)
        target = ytr if soft is None else (0.5 * ytr + 0.5 * soft)
        amp_t = np.abs(Zall["amp_ch"][tr]).astype(np.float32)
        def loss(y_true, y_pred):
            ce = keras.ops.mean(keras.ops.binary_crossentropy(y_true[:, :5], y_pred[:, :5], from_logits=True))
            return ce
        m.compile(optimizer=keras.optimizers.Adam(1e-3), loss=loss)
        Y = np.concatenate([target, amp_t], 1).astype(np.float32)
        m.fit(Ztr, Y, epochs=a.epochs, batch_size=256, verbose=0)
        return lambda X: 1 / (1 + np.exp(-np.asarray(m.predict(stand(X).astype(np.float32), verbose=0))[:, :5]))
    models["mlp_float"] = train_mlp(None)
    models["mlp_float_kd"] = train_mlp(rf_prob(Xa[tr]).astype(np.float32))
    # ---- deployed quantised ONNX
    import onnxruntime as ort
    sess = ort.InferenceSession("artifacts/detector_bitexact.onnx", providers=["CPUExecutionProvider"])
    def q_prob(X):
        lg = sess.run(["chan_logits"], {"features": X.astype(np.float32)})[0]; return 1 / (1 + np.exp(-lg))
    models["mlp_q_deployed"] = q_prob
    # ---- joint residual baseline (logistic regression on six z-scored residuals)
    from sklearn.linear_model import LogisticRegression
    ridx = [names.index(f) for f in RESID]; med = np.median(Xa[tr][:, ridx], 0); mad = 1.4826 * np.median(np.abs(Xa[tr][:, ridx] - med), 0) + 1e-6
    zres = lambda X: np.abs(X[:, ridx] - med) / mad
    lrs = [LogisticRegression(max_iter=2000, class_weight="balanced").fit(zres(Xa[tr]), ya[tr][:, c]) for c in range(5)]
    models["joint_residual"] = lambda X: np.column_stack([l.predict_proba(zres(X))[:, 1] for l in lrs])
    # thresholds: deployed thresholds for the deployed model; for the others the same 1 % pre-attack FA budget on training runs
    pre_tr = tr & ~((Zall["t"] >= Zall["t_on"]) & (Zall["t"] < Zall["t_off"] + 0.02) & (Zall["t_on"] > 0))
    rows = []
    for name, fn in models.items():
        if name == "mlp_q_deployed":
            th = thr
        else:
            P = fn(Xa); th = np.array([np.quantile(P[pre_tr & (ya[:, c] == 0), c], 0.99) for c in range(5)])
        sets = {"phase1": (Zp, Xp, np.arange(len(Xp))), "random20": (Zall, Xa, rand_idx)}
        if name != "mlp_q_deployed":
            sets["holdout"] = (Zall, Xa, np.flatnonzero(te))
        for sname, (Z, X, idx) in sets.items():
            P = fn(X)
            for pr in (True, False):
                res, R = evaluate(P, th, Z, idx, persist, hyst, pr)
                res.update(model=name, test_set=sname, priority_rule=pr, thr=json.dumps([round(float(v), 3) for v in th])); rows.append(res)
                if pr:
                    R.to_csv(out / f"runs_{name}_{sname}.csv", index=False)
            print(f"{name:16s} {sname:9s} any {res['any_pct']:5.1f} exact {res['exact_pct']:5.1f} lat {res['lat_cycles_median']:.0f} cyc / {res['lat_ms_median']:.0f} ms  cyc-P {res['cycle_precision']:.1f} R {res['cycle_recall']:.1f}  FA pre {res['fa_pre_cycles']}", flush=True)
    T = pd.DataFrame(rows); T.to_csv(out / "unified.csv", index=False)
    print("holdout test runs:", sorted(test_runs)[:5], "...", len(test_runs)); json.dump(sorted(test_runs), open(out / "holdout_runs.json", "w"))


if __name__ == "__main__":
    main()
