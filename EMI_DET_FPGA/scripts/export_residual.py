"""export_residual.py: the joint-residual baseline of detector_eval_unified.py (six z-scored residual features, one logistic
regression per channel, thresholds at the 1 % pre-attack budget on the unified training runs) exported as artifacts/residual.json
so that the same detector can run online inside the Simulink model (det_src = 1) with the same correction back end."""
import json, numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
R = Path(__file__).resolve().parents[1]; RESID = ["p_ratio", "xchk_vdc", "vbat_mismatch", "iac_mean", "vdc_err", "vac_mean"]
Z = np.load(R / "data/cycles_v3_all.npz", allow_pickle=True); names = [str(n) for n in Z["feature_names"]]; run = Z["run_id"].astype(str)
cfg = json.load(open(R / "artifacts/detector.json")); mu = np.array(cfg["mu"], dtype=np.float64)
Xa = np.where(np.isfinite(Z["X"]), Z["X"], mu).astype(np.float64); ya = Z["ych"] > 0   # non-finite features replaced by mu, as in the unified evaluation
hold = set(json.load(open(R / "runs/detector_unified/holdout_runs.json"))); ds = run < "D0301"; tr = ds & ~np.isin(run, list(hold))
ridx = [names.index(f) for f in RESID]; med = np.median(Xa[tr][:, ridx], 0); mad = 1.4826 * np.median(np.abs(Xa[tr][:, ridx] - med), 0) + 1e-6
zres = lambda X: np.abs(X[:, ridx] - med) / mad
lrs = [LogisticRegression(max_iter=2000, class_weight="balanced").fit(zres(Xa[tr]), ya[tr][:, c]) for c in range(5)]
P = np.column_stack([l.predict_proba(zres(Xa))[:, 1] for l in lrs])
pre_tr = tr & ~((Z["t"] >= Z["t_on"]) & (Z["t"] < Z["t_off"] + 0.02) & (Z["t_on"] > 0))
thr = [float(np.quantile(P[pre_tr & (~ya[:, c]), c], 0.99)) for c in range(5)]
par = [float(i + 1) for i in ridx] + med.tolist() + mad.tolist() + np.concatenate([l.coef_[0] for l in lrs]).tolist() + [float(l.intercept_[0]) for l in lrs]
out = dict(features=RESID, ridx1=[i + 1 for i in ridx], med=med.tolist(), mad=mad.tolist(), coef=[l.coef_[0].tolist() for l in lrs], intercept=[float(l.intercept_[0]) for l in lrs], thr=thr, par=par, train_runs=int(tr.sum() and len(set(run[tr]))))
json.dump(out, open(R / "artifacts/residual.json", "w"), indent=1); print("thr", np.round(thr, 3), "par length", len(par), "train runs", out["train_runs"])
