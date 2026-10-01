"""Same-split float vs quantised comparison (review point 4): on the unified split (seed 0, run-grouped 75 % of the 288 dataset runs)
train the RF-distilled float MLP exactly as detector_eval_unified.py does, copy it into an HGQ2 QDense chain with the deployed bit
budget (weights 2-7 bit, activations 4-7 bit), fine-tune it quantisation-aware, calibrate BOTH models' thresholds at the same 1 %
false-alarm budget on the same training runs, and evaluate both under the unified protocol on hold-out / benchmark / random-20.

    KERAS_BACKEND=torch python scripts/quantise_unified.py   -> runs/detector_unified/unified_samesplit.csv (+ runs_* csv)
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np, pandas as pd
os.environ.setdefault("KERAS_BACKEND", "torch")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keras
from sklearn.ensemble import RandomForestClassifier
from detector_eval_unified import evaluate, CH

SEED = 0; OUT = Path("runs/detector_unified"); OUT.mkdir(parents=True, exist_ok=True)
Zall = np.load("data/cycles_v3_all.npz", allow_pickle=True); Zp = np.load("data/cycles_v3_phase1.npz", allow_pickle=True)
cfg = json.load(open("artifacts/detector.json")); mu = np.array(cfg["mu"]); sd = np.array(cfg.get("sd", cfg.get("std", np.ones(48)))); persist = int(cfg["persist"]); hyst = float(cfg["hyst"])
ra = Zall["run_id"].astype(str); is_rand = np.array([r >= "D0301" for r in ra]); ds_idx = np.flatnonzero(~is_rand); rand_idx = np.flatnonzero(is_rand)
rng = np.random.default_rng(SEED); ur = np.unique(ra[ds_idx]); rng.shuffle(ur); test_runs = set(ur[: int(round(0.25 * len(ur)))])
te = np.array([r in test_runs for r in ra]) & ~is_rand; tr = ~te & ~is_rand
Xa = np.where(np.isfinite(Zall["X"]), Zall["X"], mu); Xp = np.where(np.isfinite(Zp["X"]), Zp["X"], mu); ya = Zall["ych"].astype(int); yp = Zp["ych"].astype(int)
stand = lambda X: ((X - mu) / np.where(sd > 0, sd, 1.0)).astype(np.float32)
# --- teacher soft labels (as in the unified script)
rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=2, n_jobs=8, random_state=SEED, class_weight="balanced_subsample").fit(Xa[tr], ya[tr])
soft = np.column_stack([p[:, 1] if p.shape[1] > 1 else np.zeros(len(p)) for p in rf.predict_proba(Xa[tr])])
target = (0.5 * ya[tr] + 0.5 * soft).astype(np.float32)
def bce(y_true, y_pred): return keras.ops.mean(keras.ops.binary_crossentropy(y_true[:, :5], y_pred[:, :5], from_logits=True))
keras.utils.set_random_seed(SEED)
inp = keras.Input((48,)); x = inp
for i in (0, 1): x = keras.layers.Dense(64, activation="relu", name=f"dense{i}")(x)
fl = keras.Model(inp, keras.layers.Dense(10, name="head")(x)); fl.compile(optimizer=keras.optimizers.Adam(1e-3), loss=bce)
Y = np.concatenate([target, np.zeros((tr.sum(), 5), np.float32)], 1); fl.fit(stand(Xa[tr]), Y, epochs=150, batch_size=256, verbose=0)
# --- HGQ2 copy with the deployed bit budget, quantisation-aware fine-tune on the same runs
from hgq.config import LayerConfigScope, QuantizerConfigScope
from hgq.layers import QDense
with QuantizerConfigScope(default_q_type="kif", place="weight", k0=1, i0=2, f0=7, trainable=False), \
     QuantizerConfigScope(default_q_type="kif", place="datalane", k0=1, i0=4, f0=7, trainable=False, overflow_mode="SAT"), \
     LayerConfigScope(enable_ebops=False, beta0=0.0):
    qi = keras.Input((48,)); qx = qi
    for i in (0, 1): qx = QDense(64, activation="relu", name=f"dense{i}")(qx)
    q = keras.Model(qi, QDense(10, name="head")(qx))
for name in ("dense0", "dense1", "head"):
    q.get_layer(name).set_weights(fl.get_layer(name).get_weights()[:2] + q.get_layer(name).get_weights()[2:]) if len(q.get_layer(name).get_weights()) > 2 else q.get_layer(name).set_weights(fl.get_layer(name).get_weights())
q.compile(optimizer=keras.optimizers.Adam(3e-4), loss=bce); q.fit(stand(Xa[tr]), Y, epochs=80, batch_size=256, verbose=0)
sig = lambda z: 1 / (1 + np.exp(-z[:, :5]))
models = {"mlp_float_kd_s0": lambda X: sig(fl.predict(stand(X), verbose=0)), "mlp_q_hgq_s0": lambda X: sig(q.predict(stand(X), verbose=0))}
# --- thresholds: 1 % FA on the clean (pre-attack) training cycles, identical rule for both
t_on = Zall["t_on"]; t = Zall["t"]; clean = tr & (~np.isfinite(t_on) | (t <= t_on))
rows = []; brk = []
for m, fn in models.items():
    P = fn(Xa[clean]); thr = np.quantile(P, 0.99, axis=0); thr = np.maximum(thr, 0.05)
    for s, Z, idx, X in [("holdout", Zall, np.flatnonzero(te), Xa), ("phase1", Zp, np.arange(len(yp)), Xp), ("random20", Zall, rand_idx, Xa)]:
        score = np.zeros((len(X), 5)); score[idx] = fn(X[idx])
        o, R = evaluate(score, thr, Z, idx, persist, hyst, True); o.update(model=m, test_set=s, thr=json.dumps([round(float(v), 3) for v in thr])); rows.append(o); R.to_csv(OUT / f"runs_{m}_{s}.csv", index=False)
        A = R[R.attacked == 1]; trs = A.truth.map(lambda v: set(v.split("+"))); des = A.detected.map(lambda v: set() if v == "none" else set(v.split("+")))
        ex = np.array([a == b for a, b in zip(trs, des)]); sup = ~ex & np.array([a <= b for a, b in zip(trs, des)]); miss = np.array([len(a & b) == 0 for a, b in zip(trs, des)])
        brk.append(dict(model=m, test_set=s, attacked=len(A), exact=int(ex.sum()), superset=int(sup.sum()), partial=int((~ex & ~sup & ~miss).sum()), miss=int(miss.sum())))
        print(f"{m:16s} {s:9s} any {o['any_pct']:5.1f} exact {o['exact_pct']:5.1f} cycP {o['cycle_precision']:5.1f} cycR {o['cycle_recall']:5.1f} FApre {o['fa_pre_cycles']}")
pd.DataFrame(rows).to_csv(OUT / "unified_samesplit.csv", index=False); pd.DataFrame(brk).to_csv(OUT / "unified_samesplit_breakdown.csv", index=False)
print("bits: weights 2+7, activations 4+7 (kif), same split, same thresholds rule")
