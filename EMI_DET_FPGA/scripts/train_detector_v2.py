"""Route-B detector, v2: regularized HGQ2 MLP with the standardization folded in,
per-channel head as primary output, run-wise validation for early stopping,
optional feature subset, ONNX export with onnxruntime parity.

    python scripts/train_detector_v2.py data/cycles_dataset.npz --out runs/det_v2 \
        --test data/cycles_phase1.npz [--float] [--features top32.txt] [--dropout 0.2] [--wd 1e-4]

Model: features (n) -> fixed affine (x - mu)/sd -> [Dense(w) ReLU, Dropout] x 2
       -> chan (5 logits), logits (10), amp (1).
Export: model.onnx with inputs 'features' (batch, n) and three outputs
        chan_logits, class_logits, amp; norm folded in, so Simulink needs no
        side file.  Parity vs onnxruntime is checked on 256 samples.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emi_det.features import CLASSES  # noqa: E402

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]


class Affine(keras.layers.Layer):
    """Fixed (x - mu) / sd, exported as constants."""

    def __init__(self, mu, sd, clip=0.0, **kw):
        super().__init__(**kw)
        self.mu = np.asarray(mu, np.float32); self.sd = np.asarray(sd, np.float32); self.clip = float(clip)

    def build(self, input_shape):
        self.mu_w = self.add_weight(shape=self.mu.shape, initializer=keras.initializers.Constant(self.mu), trainable=False, name="mu")
        self.inv_w = self.add_weight(shape=self.sd.shape, initializer=keras.initializers.Constant(1.0 / self.sd), trainable=False, name="inv_sd")

    def call(self, x):
        z = (x - self.mu_w) * self.inv_w
        if self.clip > 0:
            z = keras.ops.clip(z, -self.clip, self.clip)
        return z

    def get_config(self):
        c = super().get_config(); c.update(mu=self.mu.tolist(), sd=self.sd.tolist(), clip=self.clip); return c


def build(n_in, mu, sd, width=(48, 32), quantized=True, w_bits=(2, 7), a_bits=(4, 7), dropout=0.2, clip=0.0):
    inp = keras.Input((n_in,), name="features")
    x = Affine(mu, sd, clip, name="standardize")(inp)
    if quantized:
        from hgq.config import LayerConfigScope, QuantizerConfigScope
        from hgq.layers import QDense
        with QuantizerConfigScope(default_q_type="kif", place="weight", k0=1, i0=w_bits[0], f0=w_bits[1], trainable=False), \
             QuantizerConfigScope(default_q_type="kif", place="datalane", k0=1, i0=a_bits[0], f0=a_bits[1], trainable=False, overflow_mode="SAT"), \
             LayerConfigScope(enable_ebops=False, beta0=0.0):
            for i, w in enumerate(width):
                x = QDense(w, activation="relu", name=f"dense{i}")(x)
                if dropout > 0:
                    x = keras.layers.Dropout(dropout, name=f"drop{i}")(x)
            chan = QDense(5, name="chan")(x); logits = QDense(len(CLASSES), name="logits")(x); amp = QDense(1, name="amp")(x)
    else:
        for i, w in enumerate(width):
            x = keras.layers.Dense(w, activation="relu", name=f"dense{i}")(x)
            if dropout > 0:
                x = keras.layers.Dropout(dropout, name=f"drop{i}")(x)
        chan = keras.layers.Dense(5, name="chan")(x); logits = keras.layers.Dense(len(CLASSES), name="logits")(x); amp = keras.layers.Dense(1, name="amp")(x)
    return keras.Model(inp, [chan, logits, amp], name="emi_det_v2")


def load(npz, feat_idx=None):
    d = np.load(npz, allow_pickle=True)
    X = np.nan_to_num(d["X"].astype(np.float32), nan=0.0, posinf=1e6, neginf=-1e6)
    if feat_idx is not None:
        X = X[:, feat_idx]
    return dict(X=X, y=d["y"].astype(np.int64), a=d["a"].astype(np.float32), tr=d["tr"], t=d["t"], t_on=d["t_on"],
                run_id=d["run_id"], variant=d["variant"], ych=d["ych"].astype(np.float32), names=list(d["feature_names"]))


def evaluate(model, D, mask, tag, thr=None, fa_budget=0.01):
    chan, logits, amp = model.predict(D["X"][mask], batch_size=2048, verbose=0)
    pc = 1 / (1 + np.exp(-chan)); ych = D["ych"][mask]; tr = D["tr"][mask]; steady = tr == 0
    clean = steady & (ych.sum(1) == 0)
    if thr is None:
        thr = np.array([min([q for q in np.linspace(0.05, 0.95, 19) if (pc[clean, c] >= q).mean() <= fa_budget] or [0.95]) for c in range(5)])
    P = pc >= thr
    rep = {}
    for c, nm in enumerate(CH):
        tp = int((P[:, c] & (ych[:, c] == 1) & steady).sum()); fn = int((~P[:, c] & (ych[:, c] == 1) & steady).sum()); fp = int((P[:, c] & (ych[:, c] == 0) & steady).sum())
        rep[nm] = dict(recall=tp / max(tp + fn, 1), precision=tp / max(tp + fp, 1), support=tp + fn)
    rid = D["run_id"][mask]; t = D["t"][mask]; ton = D["t_on"][mask]; det = 0; tot = 0; lat = []
    for r in np.unique(rid):
        m = (rid == r) & steady & (ych.sum(1) > 0)
        if not m.any():
            continue
        tot += 1; chans = [c for c in range(5) if ych[m, c].any()]
        if min(P[m][:, c].mean() for c in chans) >= 0.5:
            det += 1
        after = (rid == r) & (t > ton[m][0]); ok = np.where(np.all(P[after][:, chans], axis=1))[0]
        lat.append(int(round((t[after][ok[0]] - ton[m][0]) / 0.02)) if ok.size else 99)
    fa = int((P[clean].sum(1) > 0).sum())
    pred = logits.argmax(1); y = D["y"][mask]; acc = float((pred[steady] == y[steady]).mean())
    out = dict(tag=tag, runs_detected=det, runs_injected=tot, false_alarm_cycles=fa, clean_cycles=int(clean.sum()),
               latency_median=float(np.median(lat)) if lat else None, class_accuracy=acc, thr=thr.tolist(), per_channel=rep)
    print(f"[{tag}] runs {det}/{tot}  FA {fa}/{int(clean.sum())} ({100*fa/max(clean.sum(),1):.1f}%)  lat med {out['latency_median']}  10-class acc {acc:.3f}  "
          + " ".join(f"{k}:R{v['recall']:.2f}/P{v['precision']:.2f}" for k, v in rep.items()))
    return out, thr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train_npz"); ap.add_argument("--out", required=True); ap.add_argument("--test")
    ap.add_argument("--features", help="text file with feature names to keep (one per line)")
    ap.add_argument("--width", default="48,32"); ap.add_argument("--dropout", type=float, default=0.2); ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--epochs", type=int, default=400); ap.add_argument("--batch", type=int, default=256); ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--float", action="store_true"); ap.add_argument("--wbits", default="2,7"); ap.add_argument("--abits", default="4,7")
    ap.add_argument("--test-frac", type=float, default=0.25); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--clip", type=float, default=0.0, help="clip standardized features to +-clip (0 = off)")
    ap.add_argument("--chan-only", action="store_true", help="train only the per-channel head with plain BCE (sklearn-like recipe)")
    ap.add_argument("--base43", action="store_true", help="use only the 43 base features (drop baseline-relative block and one-hot)")
    args = ap.parse_args()
    keras.utils.set_random_seed(args.seed)
    D0 = load(args.train_npz)
    feat_idx = None
    if args.base43:
        feat_idx = [i for i, n in enumerate(D0["names"]) if not str(n).startswith("d_") and not str(n).startswith("is_")]
    if args.features:
        keep = [l.strip() for l in open(args.features) if l.strip()]
        feat_idx = [D0["names"].index(k) for k in keep]
    D = load(args.train_npz, feat_idx)
    from sklearn.model_selection import GroupShuffleSplit
    n = D["y"].size
    itr, ite = next(GroupShuffleSplit(n_splits=1, test_size=args.test_frac, random_state=args.seed).split(D["X"], D["y"], D["run_id"]))
    te = np.zeros(n, bool); te[ite] = True; trn = ~te
    # validation runs (for early stopping) carved out of the training runs
    itr2, iva = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=args.seed + 1).split(D["X"][trn], D["y"][trn], D["run_id"][trn]))
    idx_trn = np.where(trn)[0]; va = np.zeros(n, bool); va[idx_trn[iva]] = True; fit = trn & ~va & (D["tr"] == 0); vfit = va & (D["tr"] == 0)
    mu = D["X"][fit].mean(0); sd = D["X"][fit].std(0) + 1e-6
    model = build(D["X"].shape[1], mu, sd, tuple(int(w) for w in args.width.split(",")), quantized=not args.float,
                  w_bits=tuple(int(b) for b in args.wbits.split(",")), a_bits=tuple(int(b) for b in args.abits.split(",")), dropout=args.dropout, clip=args.clip)
    pos = D["ych"][fit].mean(0); pw = np.clip((1 - pos) / np.maximum(pos, 1e-3), 1, 20)
    cnt = np.bincount(D["y"][fit], minlength=len(CLASSES)).astype(float); cw = np.where(cnt > 0, cnt.sum() / (len(CLASSES) * np.maximum(cnt, 1)), 0.0)
    # channel loss with positive-class weighting via sample weights on a per-sample basis is not possible per output column,
    # so use a weighted BCE
    def wbce(y_true, y_pred):
        w = 1.0 + y_true * (keras.ops.convert_to_tensor(pw, dtype="float32") - 1.0)
        bce = keras.ops.softplus(-y_pred) * y_true + keras.ops.softplus(y_pred) * (1.0 - y_true)   # elementwise BCE from logits
        return keras.ops.mean(w * bce, axis=-1)
    if args.chan_only:
        model.compile(optimizer=keras.optimizers.AdamW(args.lr, weight_decay=args.wd),
                      loss=[keras.losses.BinaryCrossentropy(from_logits=True), keras.losses.SparseCategoricalCrossentropy(from_logits=True), "mse"],
                      loss_weights=[1.0, 0.0, 0.0])
    else:
        model.compile(optimizer=keras.optimizers.AdamW(args.lr, weight_decay=args.wd),
                      loss=[wbce, keras.losses.SparseCategoricalCrossentropy(from_logits=True), "mse"], loss_weights=[3.0, 1.0, 1.0])
    cb = [keras.callbacks.EarlyStopping(monitor="val_loss", patience=40, restore_best_weights=True),
          keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=15, min_lr=1e-5)]
    sw_cls = np.ones(fit.sum()) if args.chan_only else cw[D["y"][fit]]
    model.fit(D["X"][fit], [D["ych"][fit], D["y"][fit], D["a"][fit]], sample_weight=[np.ones(fit.sum()), sw_cls, np.ones(fit.sum())],
              validation_data=(D["X"][vfit], [D["ych"][vfit], D["y"][vfit], D["a"][vfit]]),
              epochs=args.epochs, batch_size=args.batch, verbose=0, callbacks=cb)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rep = {}
    rep["train"], thr = evaluate(model, D, fit, "train")
    rep["val"], _ = evaluate(model, D, va, "val", thr)
    rep["test"], _ = evaluate(model, D, te, "test-runs", thr)
    if args.test:
        T = load(args.test, feat_idx); rep["independent"], _ = evaluate(model, T, np.ones(T["y"].size, bool), "phase1", thr)
    model.save(out / "model.keras")
    json.dump(dict(features=[D["names"][i] for i in (feat_idx or range(len(D["names"])))], mu=mu.tolist(), sd=sd.tolist(),
                   thr=thr.tolist(), quantized=not args.float, width=args.width, params=int(model.count_params())), open(out / "detector.json", "w"), indent=1)
    json.dump(rep, open(out / "report.json", "w"), indent=1)
    # ONNX export + parity
    try:
        onnx_path = out / "model.onnx"; model.export(str(onnx_path), format="onnx", verbose=False)
        import onnxruntime as ort
        s = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        xs = D["X"][:256]; ref = model.predict(xs, verbose=0)
        got = s.run(None, {s.get_inputs()[0].name: xs})
        err = max(float(np.abs(a - b).max()) for a, b in zip(ref, got))
        print(f"onnx: inputs {[(i.name, i.shape) for i in s.get_inputs()]} outputs {[(o.name, o.shape) for o in s.get_outputs()]} parity max abs {err:.3g}")
    except Exception as e:
        print("onnx export failed:", e)
    print(f"params {model.count_params()} saved {out}")


if __name__ == "__main__":
    main()
