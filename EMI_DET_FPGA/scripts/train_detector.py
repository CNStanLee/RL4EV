"""Train the route-B EMI-injection detector: quantized (HGQ2) MLP on per-cycle features.

    python scripts/train_detector.py data/cycles_dataset.npz --out runs/det_mlp \
        [--test data/cycles_phase1.npz] [--holdout-variant MPCC_D_R] [--float]

Inputs : 41 per-cycle features (features.FEATURE_NAMES), standardized with the
         training-set mean / std (stored in the run directory, to be applied in
         fixed point on the FPGA).
Outputs: 10-class softmax (features.CLASSES) + 1 regression (normalized amplitude
         of the first injection, 0 for 'none').
Split  : run-wise (GroupShuffleSplit on run_id) unless --holdout-variant.
Metrics: per-class precision / recall on steady cycles, false-alarm rate on
         'none' cycles, detection latency per run, amplitude MAE, plus the same
         on an optional independent test set (e.g. the phase-1 runs).
Artifacts: model.keras, model.onnx (if onnx export available), norm.json,
           report.json, confusion.csv.
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


def build_model(n_in: int, n_cls: int, width=(48, 32), quantized=True, w_bits=(1, 6), a_bits=(3, 5)):
    if quantized:
        from hgq.config import LayerConfigScope, QuantizerConfig, QuantizerConfigScope
        from hgq.layers import QDense
        wq = QuantizerConfig("kif", "weight", k0=1, i0=w_bits[0], f0=w_bits[1], trainable=False)
        aq = QuantizerConfig("kif", "datalane", k0=1, i0=a_bits[0], f0=a_bits[1], trainable=False)
        with QuantizerConfigScope(default_q_type="kif", place="weight", k0=1, i0=w_bits[0], f0=w_bits[1], trainable=False), \
             QuantizerConfigScope(default_q_type="kif", place="datalane", k0=1, i0=a_bits[0], f0=a_bits[1], trainable=False), \
             LayerConfigScope(enable_ebops=False, beta0=0.0):
            inp = keras.Input((n_in,), name="features")
            x = inp
            for i, w in enumerate(width):
                x = QDense(w, activation="relu", name=f"dense{i}")(x)
            logits = QDense(n_cls, name="logits")(x)
            amp = QDense(1, name="amp")(x)
        del wq, aq
    else:
        inp = keras.Input((n_in,), name="features")
        x = inp
        for i, w in enumerate(width):
            x = keras.layers.Dense(w, activation="relu", name=f"dense{i}")(x)
        logits = keras.layers.Dense(n_cls, name="logits")(x)
        amp = keras.layers.Dense(1, name="amp")(x)
    return keras.Model(inp, [logits, amp], name="emi_det_mlp")


def load(npz: str):
    d = np.load(npz, allow_pickle=True)
    X = np.nan_to_num(d["X"].astype(np.float32), nan=0.0, posinf=1e6, neginf=-1e6)
    return dict(X=X, y=d["y"].astype(np.int64), a=d["a"].astype(np.float32), tr=d["tr"], t=d["t"],
                t_on=d["t_on"], run_id=d["run_id"], variant=d["variant"])


def evaluate(model, D, mask, mu, sd, tag: str) -> dict:
    Xn = (D["X"][mask] - mu) / sd
    logits, amp = model.predict(Xn, batch_size=1024, verbose=0)
    pred = logits.argmax(1); y = D["y"][mask]; tr = D["tr"][mask]
    steady = tr == 0
    rep = {}
    for i, c in enumerate(CLASSES):
        tp = int(((pred == i) & (y == i) & steady).sum()); fp = int(((pred == i) & (y != i) & steady).sum())
        fn = int(((pred != i) & (y == i) & steady).sum()); sup = int(((y == i) & steady).sum())
        if sup or fp:
            rep[c] = dict(precision=tp / max(tp + fp, 1), recall=tp / max(tp + fn, 1), support=sup)
    none = steady & (y == 0)
    fa = int((pred[none] != 0).sum())
    acc = float((pred[steady] == y[steady]).mean())
    mae = float(np.abs(amp[:, 0][steady & (y != 0)] - D["a"][mask][steady & (y != 0)]).mean()) if (steady & (y != 0)).any() else float("nan")
    # latency per run
    lat = []; missed = 0; runs = 0
    rid = D["run_id"][mask]; t = D["t"][mask]; ton = D["t_on"][mask]
    for r in np.unique(rid):
        m = rid == r; ys = y[m]; ys = ys[ys != 0]
        if ys.size == 0:
            continue
        runs += 1; c = ys[0]; after = m & (t > ton[m][0])
        hit = np.where(pred[after] == c)[0]
        if hit.size == 0:
            missed += 1
        else:
            lat.append(int(round((t[after][hit[0]] - ton[m][0]) / 0.02)))
    cm = np.zeros((len(CLASSES), len(CLASSES)), int)
    for yt, yp in zip(y[steady], pred[steady]):
        cm[yt, yp] += 1
    out = dict(tag=tag, steady_cycles=int(steady.sum()), accuracy=acc, false_alarms=fa, none_cycles=int(none.sum()),
               amp_mae=mae, latency_median=float(np.median(lat)) if lat else None, latency_max=int(max(lat)) if lat else None,
               missed_runs=missed, injected_runs=runs, per_class=rep, confusion=cm.tolist())
    print(f"[{tag}] steady {out['steady_cycles']} acc {acc:.4f}  false alarms {fa}/{out['none_cycles']}  amp MAE {mae:.3f}  "
          f"latency med {out['latency_median']} max {out['latency_max']} missed {missed}/{runs}")
    for c, v in rep.items():
        print(f"    {c:9s} P {v['precision']:.3f} R {v['recall']:.3f} n={v['support']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("train_npz"); ap.add_argument("--out", required=True)
    ap.add_argument("--test", default=None); ap.add_argument("--holdout-variant", default=None)
    ap.add_argument("--test-frac", type=float, default=0.25); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=200); ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=2e-3); ap.add_argument("--width", default="48,32")
    ap.add_argument("--float", action="store_true", help="unquantized reference model")
    ap.add_argument("--wbits", default="2,7", help="weight kif integer,fraction bits"); ap.add_argument("--abits", default="4,7", help="activation kif integer,fraction bits")
    args = ap.parse_args()
    keras.utils.set_random_seed(args.seed)
    D = load(args.train_npz)
    n = D["y"].size
    if args.holdout_variant:
        te = D["variant"] == args.holdout_variant; trn = ~te
    else:
        from sklearn.model_selection import GroupShuffleSplit
        gss = GroupShuffleSplit(n_splits=1, test_size=args.test_frac, random_state=args.seed)
        itr, ite = next(gss.split(D["X"], D["y"], D["run_id"]))
        trn = np.zeros(n, bool); trn[itr] = True; te = ~trn
    fit = trn & (D["tr"] == 0)
    mu = D["X"][fit].mean(0); sd = D["X"][fit].std(0) + 1e-6
    Xn = (D["X"][fit] - mu) / sd
    # class weights: balance 'none' against the injected classes
    cnt = np.bincount(D["y"][fit], minlength=len(CLASSES)).astype(float); cw = np.where(cnt > 0, cnt.sum() / (len(CLASSES) * np.maximum(cnt, 1)), 0.0)
    sw = cw[D["y"][fit]]
    model = build_model(D["X"].shape[1], len(CLASSES), tuple(int(w) for w in args.width.split(",")), quantized=not args.float, w_bits=tuple(int(b) for b in args.wbits.split(",")), a_bits=tuple(int(b) for b in args.abits.split(",")))
    model.compile(optimizer=keras.optimizers.Adam(args.lr),
                  loss=[keras.losses.SparseCategoricalCrossentropy(from_logits=True), "mse"],
                  loss_weights=[1.0, 2.0])
    cb = [keras.callbacks.EarlyStopping(monitor="loss", patience=25, restore_best_weights=True),
          keras.callbacks.ReduceLROnPlateau(monitor="loss", factor=0.5, patience=10, min_lr=1e-5)]
    model.fit(Xn, [D["y"][fit], D["a"][fit]], sample_weight=[sw, np.ones_like(sw)],
              epochs=args.epochs, batch_size=args.batch, verbose=0, callbacks=cb)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    json.dump(dict(mu=mu.tolist(), sd=sd.tolist(), classes=CLASSES, quantized=not args.float, width=args.width),
              open(out / "norm.json", "w"), indent=1)
    report = dict(train=evaluate(model, D, trn, mu, sd, "train"), test=evaluate(model, D, te, mu, sd, "test-split"))
    if args.test:
        T = load(args.test); report["independent"] = evaluate(model, T, np.ones(T["y"].size, bool), mu, sd, "independent")
    json.dump(report, open(out / "report.json", "w"), indent=1)
    print(f"params: {model.count_params()}  saved to {out}")
    try:
        import torch  # noqa: F401
        from keras.export import ExportArchive  # noqa: F401
    except Exception:
        pass


if __name__ == "__main__":
    main()
