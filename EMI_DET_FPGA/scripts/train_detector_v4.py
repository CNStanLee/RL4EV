"""Route-B detector, v4: sklearn multi-label MLP (proven recipe) -> HGQ2 QDense
network initialised from its weights -> short quantization-aware fine-tune ->
ONNX (standardization folded in).

    python scripts/train_detector_v4.py data/cycles_dataset.npz --out runs/det_v4 --test data/cycles_phase1.npz

Inputs: the 43 base features (features.FEATURE_NAMES).  Outputs of the ONNX:
chan (5 logits), and for compatibility two dummy heads: class logits (10, all
zero) and amp (1, zero) -> 16 values, same layout the Simulink block expects.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("KERAS_BACKEND", "torch")
import keras  # noqa: E402
from sklearn.model_selection import GroupShuffleSplit  # noqa: E402
from sklearn.neural_network import MLPClassifier  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emi_det.features import FEATURE_NAMES  # noqa: E402

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
NB = len(FEATURE_NAMES)


def load(npz):
    d = np.load(npz, allow_pickle=True)
    X = np.nan_to_num(d["X"][:, :NB].astype(np.float32), nan=0.0, posinf=1e6, neginf=-1e6)
    return dict(X=X, ych=d["ych"].astype(np.float32), tr=d["tr"], t=d["t"], t_on=d["t_on"], run_id=d["run_id"], y=d["y"])


def metrics(pc, D, mask, tag, thr=None, fa_budget=0.01):
    ych = D["ych"][mask]; tr = D["tr"][mask]; steady = tr == 0; clean = steady & (ych.sum(1) == 0)
    if thr is None:
        thr = np.array([min([q for q in np.linspace(0.05, 0.95, 19) if (pc[clean, c] >= q).mean() <= fa_budget] or [0.95]) for c in range(5)])
    P = pc >= thr; rep = {}
    for c, nm in enumerate(CH):
        tp = int((P[:, c] & (ych[:, c] == 1) & steady).sum()); fn = int((~P[:, c] & (ych[:, c] == 1) & steady).sum()); fp = int((P[:, c] & (ych[:, c] == 0) & steady).sum())
        rep[nm] = dict(recall=tp / max(tp + fn, 1), precision=tp / max(tp + fp, 1), support=tp + fn)
    rid = D["run_id"][mask]; t = D["t"][mask]; ton = D["t_on"][mask]; det = tot = 0; lat = []
    for r in np.unique(rid):
        m = (rid == r) & steady & (ych.sum(1) > 0)
        if not m.any():
            continue
        tot += 1; chans = [c for c in range(5) if ych[m, c].any()]
        det += int(min(P[m][:, c].mean() for c in chans) >= 0.5)
        after = (rid == r) & (t > ton[m][0]); ok = np.where(np.all(P[after][:, chans], axis=1))[0]
        lat.append(int(round((t[after][ok[0]] - ton[m][0]) / 0.02)) if ok.size else 99)
    fa = int((P[clean].sum(1) > 0).sum())
    out = dict(tag=tag, runs_detected=det, runs_injected=tot, false_alarm_cycles=fa, clean_cycles=int(clean.sum()),
               latency_median=float(np.median(lat)) if lat else None, thr=thr.tolist(), per_channel=rep)
    print(f"[{tag}] runs {det}/{tot}  FA {fa}/{int(clean.sum())} ({100 * fa / max(clean.sum(), 1):.1f}%)  lat med {out['latency_median']}  "
          + " ".join(f"{k}:R{v['recall']:.2f}/P{v['precision']:.2f}" for k, v in rep.items()))
    return out, thr


class Affine(keras.layers.Layer):
    def __init__(self, mu, sd, **kw):
        super().__init__(**kw); self.mu = np.asarray(mu, np.float32); self.sd = np.asarray(sd, np.float32)

    def build(self, input_shape):
        self.mu_w = self.add_weight(shape=self.mu.shape, initializer=keras.initializers.Constant(self.mu), trainable=False, name="mu")
        self.inv_w = self.add_weight(shape=self.sd.shape, initializer=keras.initializers.Constant(1.0 / self.sd), trainable=False, name="inv_sd")

    def call(self, x):
        return (x - self.mu_w) * self.inv_w

    def get_config(self):
        c = super().get_config(); c.update(mu=self.mu.tolist(), sd=self.sd.tolist()); return c


def build_q(n_in, mu, sd, widths, w_bits, a_bits):
    from hgq.config import LayerConfigScope, QuantizerConfigScope
    from hgq.layers import QDense
    inp = keras.Input((n_in,), name="features"); x = Affine(mu, sd, name="standardize")(inp)
    with QuantizerConfigScope(default_q_type="kif", place="weight", k0=1, i0=w_bits[0], f0=w_bits[1], trainable=False), \
         QuantizerConfigScope(default_q_type="kif", place="datalane", k0=1, i0=a_bits[0], f0=a_bits[1], trainable=False, overflow_mode="SAT"), \
         LayerConfigScope(enable_ebops=False, beta0=0.0):
        for i, w in enumerate(widths):
            x = QDense(w, activation="relu", name=f"dense{i}")(x)
        chan = QDense(5, name="chan")(x)
    zeros10 = keras.layers.Lambda(lambda z: keras.ops.zeros_like(z[:, :1]) * keras.ops.zeros((1, 10)), name="logits")(chan)
    zero1 = keras.layers.Lambda(lambda z: keras.ops.zeros_like(z[:, :1]), name="amp")(chan)
    return keras.Model(inp, [chan, zeros10, zero1], name="emi_det_v4")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train_npz"); ap.add_argument("--out", required=True); ap.add_argument("--test")
    ap.add_argument("--width", default="64,64"); ap.add_argument("--alpha", type=float, default=1e-3); ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--wbits", default="2,7"); ap.add_argument("--abits", default="4,7"); ap.add_argument("--ft-epochs", type=int, default=60)
    ap.add_argument("--test-frac", type=float, default=0.25); ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    D = load(args.train_npz); n = D["ych"].shape[0]
    itr, ite = next(GroupShuffleSplit(n_splits=1, test_size=args.test_frac, random_state=args.seed).split(D["X"], D["ych"][:, 0], D["run_id"]))
    te = np.zeros(n, bool); te[ite] = True; trn = ~te; fit = trn & (D["tr"] == 0)
    mu = D["X"][fit].mean(0); sd = D["X"][fit].std(0) + 1e-6
    Xn = (D["X"] - mu) / sd
    widths = tuple(int(w) for w in args.width.split(","))
    # --- 1. sklearn multi-label MLP (the recipe that reached 144/185 in CV)
    clf = MLPClassifier(widths, alpha=args.alpha, max_iter=args.iters, random_state=args.seed)
    clf.fit(Xn[fit], D["ych"][fit].astype(int))
    pc = clf.predict_proba(Xn)
    rep = {}
    rep["sk_train"], thr = metrics(pc[fit], D, fit, "sklearn train")
    rep["sk_test"], _ = metrics(pc[te], D, te, "sklearn test-runs", thr)
    T = load(args.test) if args.test else None
    if T is not None:
        rep["sk_phase1"], _ = metrics(clf.predict_proba((T["X"] - mu) / sd), T, np.ones(T["ych"].shape[0], bool), "sklearn phase1", thr)
    # --- 2. HGQ2 network initialised from the sklearn weights, short QAT fine-tune
    model = build_q(NB, mu, sd, widths, tuple(int(b) for b in args.wbits.split(",")), tuple(int(b) for b in args.abits.split(",")))
    dense_layers = [model.get_layer(f"dense{i}") for i in range(len(widths))] + [model.get_layer("chan")]
    for lyr, W, b in zip(dense_layers, clf.coefs_, clf.intercepts_):
        lyr.set_weights([W.astype(np.float32), b.astype(np.float32)] + lyr.get_weights()[2:])
    chan0, _, _ = model.predict(D["X"][:512], verbose=0)
    print("quantized-init vs sklearn max |dlogit| on 512 samples:", float(np.abs(chan0 - (clf._forward_pass_fast(Xn[:512]) if hasattr(clf, "_forward_pass_fast") else chan0)).max()) if False else "n/a")
    rep["q_init_test"], _ = metrics(1 / (1 + np.exp(-model.predict(D["X"][te], verbose=0)[0])), D, te, "HGQ2 init test-runs", thr)
    model.compile(optimizer=keras.optimizers.Adam(3e-4), loss=[keras.losses.BinaryCrossentropy(from_logits=True), None, None])
    model.fit(D["X"][fit], [D["ych"][fit], np.zeros((fit.sum(), 10), np.float32), np.zeros((fit.sum(), 1), np.float32)],
              epochs=args.ft_epochs, batch_size=128, verbose=0)
    pcq = 1 / (1 + np.exp(-model.predict(D["X"], verbose=0)[0]))
    rep["q_train"], thr_q = metrics(pcq[fit], D, fit, "HGQ2 QAT train")
    rep["q_test"], _ = metrics(pcq[te], D, te, "HGQ2 QAT test-runs", thr_q)
    if T is not None:
        rep["q_phase1"], _ = metrics(1 / (1 + np.exp(-model.predict(T["X"], verbose=0)[0])), T, np.ones(T["ych"].shape[0], bool), "HGQ2 QAT phase1", thr_q)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    json.dump(dict(features=FEATURE_NAMES, mu=mu.tolist(), sd=sd.tolist(), thr=thr_q.tolist(), width=list(widths),
                   wbits=args.wbits, abits=args.abits, params=int(model.count_params())), open(out / "detector.json", "w"), indent=1)
    json.dump(rep, open(out / "report.json", "w"), indent=1)
    onnx_path = out / "model.onnx"; model.export(str(onnx_path), format="onnx", verbose=False)
    import onnxruntime as ort
    s = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    xs = D["X"][:256]; ref = model.predict(xs, verbose=0); got = s.run(None, {s.get_inputs()[0].name: xs})
    print(f"onnx inputs {[(i.name, i.shape) for i in s.get_inputs()]} outputs {[(o.name, o.shape) for o in s.get_outputs()]} parity {max(float(np.abs(a - b).max()) for a, b in zip(ref, got)):.3g}")
    print(f"params {model.count_params()} saved {out}")


if __name__ == "__main__":
    main()
