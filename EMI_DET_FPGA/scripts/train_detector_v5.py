"""Route-B detector, v5 (plan step D3-D6): random-forest soft-label distillation, per-channel
amplitude head, 48-wide input (FEATURE_NAMES_V3), 2-cycle persistence + hysteresis evaluation,
then HGQ2 QAT and a board chain on standardized inputs.

    python scripts/train_detector_v5.py data/cycles_dataset.npz [data/cycles_v3_supplement.npz ...] \
        --out runs/det_v5 --test data/cycles_phase1.npz [--width 64,64] [--wbits 2,7] [--abits 4,7]

Training files may have different feature layouts: columns are matched by name against
features.FEATURE_NAMES_V3 (48); features missing in a file are set to the training mean
(0 after standardization) so the 92-column v2 sets (43 base features + baseline deltas + one-hots
that are not used) mix with the 48-column v3 sets.

Recipe
  1. random forest (per channel, 400 trees) with out-of-fold probabilities on the training runs
     (GroupKFold by run) -> soft targets  p_soft = 0.5 * y + 0.5 * p_rf  (the RF is the 160 / 185
     upper-bound reference; distillation regularizes the small MLP)
  2. float Keras MLP (Affine standardization -> Dense widths -> head 10 = 5 channel logits + 5
     signed normalized amplitudes), BCE on p_soft + masked MSE on the amplitudes, early stopping on
     the held-out runs
  3. HGQ2 QDense copy of the float MLP, short quantization-aware fine-tune (same losses)
  4. thresholds per channel at a false-alarm budget on the clean steady cycles; reported raw and
     after the run-time decision rule (2 consecutive cycles to set, hysteresis 0.6 * thr to clear)
Outputs (in --out): model.keras (full), chain_std.keras (pure QDense chain on standardized
inputs, head 10), detector.json (features, mu, sd, thr, bits), report.json.
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
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.model_selection import GroupKFold, GroupShuffleSplit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emi_det.features import CHANNELS, FEATURE_NAMES_V3  # noqa: E402

NB = len(FEATURE_NAMES_V3)
MULTI = 9   # CLASSES index of 'multi'


# ------------------------------------------------------------------ data
def load(npz_paths):
    parts = []
    for p in npz_paths:
        d = np.load(p, allow_pickle=True)
        names = [str(n) for n in d["feature_names"]]
        X = np.full((d["X"].shape[0], NB), np.nan)
        for j, nm in enumerate(FEATURE_NAMES_V3):
            if nm in names:
                X[:, j] = d["X"][:, names.index(nm)]
        X = np.where(np.isfinite(X), X, np.nan)
        n = X.shape[0]
        ych = d["ych"].astype(np.float32)
        if "amp_ch" in d:
            amp = d["amp_ch"].astype(np.float32); amp_ok = np.ones(n, bool)
        else:   # old layout: one signed amplitude of channel 1; usable only for single-channel cycles
            amp = d["a"][:, None].astype(np.float32) * ych; amp_ok = d["y"] != MULTI
        parts.append(dict(X=X, ych=ych, amp=amp, amp_ok=amp_ok, tr=d["tr"], t=d["t"], t_on=d["t_on"], t_off=d["t_off"],
                          run_id=np.array([f"{Path(p).stem}:{r}" for r in d["run_id"]]), y=d["y"]))
    out = {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
    print(f"loaded {out['X'].shape[0]} cycles from {len(parts)} file(s); features present per file: "
          + ", ".join(str(int(np.isfinite(q['X'][0]).sum())) for q in parts))
    return out


def standardize(X, mu, sd):
    Z = (X - mu) / sd
    return np.where(np.isfinite(Z), Z, 0.0).astype(np.float32)


# ------------------------------------------------------------------ decisions / metrics
def decide(p, thr, run_id, t, persist=2, hyst=0.6):
    """Run-time rule: set a channel flag after `persist` consecutive cycles >= thr, clear when < hyst*thr."""
    F = np.zeros_like(p, bool)
    for r in np.unique(run_id):
        idx = np.where(run_id == r)[0]; idx = idx[np.argsort(t[idx])]
        cnt = np.zeros(p.shape[1], int); on = np.zeros(p.shape[1], bool)
        for i in idx:
            above = p[i] >= thr; below = p[i] < hyst * thr
            cnt = np.where(above, cnt + 1, 0)
            on = np.where(on, ~below, cnt >= persist)
            F[i] = on
    return F


def metrics(pc, D, mask, tag, thr=None, fa_budget=0.01, rule=False):
    ych = D["ych"][mask]; tr = D["tr"][mask]; steady = tr == 0; clean = steady & (ych.sum(1) == 0)
    rid = D["run_id"][mask]; t = D["t"][mask]; ton = D["t_on"][mask]; toff = D["t_off"][mask]
    # clean cycles before the injection (or in runs without one) vs. after its removal (recovery transients:
    # physically disturbed cycles, reported separately as in sil_report.py)
    clean_pre = clean & ~(t > toff); clean_post = clean & (t > toff)
    if thr is None:
        thr = np.array([min([q for q in np.linspace(0.05, 0.95, 19) if (pc[clean_pre, c] >= q).mean() <= fa_budget] or [0.95]) for c in range(5)])
    P = decide(pc, thr, rid, t) if rule else (pc >= thr)
    rep = {}
    for c, nm in enumerate(CHANNELS):
        tp = int((P[:, c] & (ych[:, c] == 1) & steady).sum()); fn = int((~P[:, c] & (ych[:, c] == 1) & steady).sum()); fp = int((P[:, c] & (ych[:, c] == 0) & steady).sum())
        rep[nm] = dict(recall=tp / max(tp + fn, 1), precision=tp / max(tp + fp, 1), support=tp + fn)
    det = tot = 0; lat = []
    for r in np.unique(rid):
        m = (rid == r) & steady & (ych.sum(1) > 0)
        if not m.any():
            continue
        tot += 1; chans = [c for c in range(5) if ych[m, c].any()]
        det += int(min(P[m][:, c].mean() for c in chans) >= 0.5)
        after = (rid == r) & (t > ton[m][0]); ok = np.where(np.all(P[after][:, chans], axis=1))[0]
        lat.append(int(round((t[after][ok[0]] - ton[m][0]) / 0.02)) if ok.size else 99)
    fa_pre = int((P[clean_pre].sum(1) > 0).sum()); fa_post = int((P[clean_post].sum(1) > 0).sum())
    out = dict(tag=tag, rule=rule, runs_detected=det, runs_injected=tot, fa_pre=fa_pre, clean_pre=int(clean_pre.sum()),
               fa_post=fa_post, clean_post=int(clean_post.sum()),
               latency_median=float(np.median(lat)) if lat else None, latency_p90=float(np.percentile(lat, 90)) if lat else None,
               thr=thr.tolist(), per_channel=rep)
    print(f"[{tag}{' +rule' if rule else ''}] runs {det}/{tot}  FA pre {fa_pre}/{int(clean_pre.sum())} ({100 * fa_pre / max(clean_pre.sum(), 1):.2f}%)  "
          f"post {fa_post}/{int(clean_post.sum())} ({100 * fa_post / max(clean_post.sum(), 1):.1f}%)  "
          f"lat med {out['latency_median']} p90 {out['latency_p90']}  " + " ".join(f"{k}:R{v['recall']:.2f}" for k, v in rep.items()), flush=True)
    return out, thr


def amp_metrics(pa, D, mask, tag):
    ych = D["ych"][mask]; amp = D["amp"][mask]; ok = D["amp_ok"][mask] & (D["tr"][mask] == 0)
    rel = []
    for c in range(5):
        m = ok & (ych[:, c] == 1) & (np.abs(amp[:, c]) > 0.05)
        if m.any():
            rel.append(np.median(np.abs(pa[m, c] - amp[m, c]) / np.abs(amp[m, c])))
        else:
            rel.append(np.nan)
    print(f"[{tag}] amplitude median relative error per channel: " + " ".join(f"{CHANNELS[c]}:{100 * rel[c]:.0f}%" for c in range(5)), flush=True)
    return dict(tag=tag, median_rel_err=[None if np.isnan(r) else float(r) for r in rel])


# ------------------------------------------------------------------ models
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


def heads(h):
    chan = keras.layers.Lambda(lambda z: z[:, :5], name="chan_logits")(h)
    amp = keras.layers.Lambda(lambda z: z[:, 5:], name="amp")(h)
    zeros10 = keras.layers.Lambda(lambda z: keras.ops.zeros_like(z[:, :1]) * keras.ops.zeros((1, 10)), name="logits")(h)
    return [chan, zeros10, amp]


def build_float(widths):
    inp = keras.Input((NB,), name="features_std"); x = inp
    for i, w in enumerate(widths):
        x = keras.layers.Dense(w, activation="relu", name=f"dense{i}")(x)
    h = keras.layers.Dense(10, name="head")(x)
    return keras.Model(inp, heads(h), name="emi_det_v5_float")


def build_q(widths, w_bits, a_bits, standardized_input=False, mu=None, sd=None):
    from hgq.config import LayerConfigScope, QuantizerConfigScope
    from hgq.layers import QDense
    inp = keras.Input((NB,), name="features"); x = inp if standardized_input else Affine(mu, sd, name="standardize")(inp)
    with QuantizerConfigScope(default_q_type="kif", place="weight", k0=1, i0=w_bits[0], f0=w_bits[1], trainable=False), \
         QuantizerConfigScope(default_q_type="kif", place="datalane", k0=1, i0=a_bits[0], f0=a_bits[1], trainable=False, overflow_mode="SAT"), \
         LayerConfigScope(enable_ebops=False, beta0=0.0):
        for i, w in enumerate(widths):
            x = QDense(w, activation="relu", name=f"dense{i}")(x)
        h = QDense(10, name="head")(x)
    if standardized_input:
        return keras.Model(inp, h, name="emi_det_v5_chain")
    return keras.Model(inp, heads(h), name="emi_det_v5")


def masked_mse(y_true, y_pred):
    # y_true: [amp(5), mask(5)]
    a = y_true[:, :5]; m = y_true[:, 5:]
    return keras.ops.sum(m * keras.ops.square(y_pred - a)) / (keras.ops.sum(m) + 1.0)


def compile_(model, lr, amp_w):
    model.compile(optimizer=keras.optimizers.Adam(lr),
                  loss=[keras.losses.BinaryCrossentropy(from_logits=True), None, masked_mse],
                  loss_weights=[1.0, 0.0, amp_w])


def targets(D, idx, p_soft):
    amp_mask = (D["ych"][idx] * D["amp_ok"][idx][:, None]).astype(np.float32)
    return [p_soft[idx].astype(np.float32), np.zeros((len(idx), 10), np.float32),
            np.concatenate([D["amp"][idx], amp_mask], axis=1).astype(np.float32)]


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("train_npz", nargs="+"); ap.add_argument("--out", required=True); ap.add_argument("--test")
    ap.add_argument("--width", default="64,64"); ap.add_argument("--wbits", default="2,7"); ap.add_argument("--abits", default="4,7")
    ap.add_argument("--test-frac", type=float, default=0.25); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--distill", type=float, default=0.5, help="weight of the RF soft label (0 = plain labels)")
    ap.add_argument("--amp-w", type=float, default=0.3); ap.add_argument("--epochs", type=int, default=300); ap.add_argument("--ft-epochs", type=int, default=80)
    ap.add_argument("--fa-budget", type=float, default=0.01)
    args = ap.parse_args()
    keras.utils.set_random_seed(args.seed)
    D = load(args.train_npz); n = D["ych"].shape[0]
    itr, ite = next(GroupShuffleSplit(n_splits=1, test_size=args.test_frac, random_state=args.seed).split(D["X"], D["ych"][:, 0], D["run_id"]))
    te = np.zeros(n, bool); te[ite] = True; trn = ~te; fit = trn & (D["tr"] == 0)
    mu = np.nanmean(D["X"][fit], 0); sd = np.nanstd(D["X"][fit], 0) + 1e-6
    mu = np.where(np.isfinite(mu), mu, 0.0); sd = np.where(np.isfinite(sd), sd, 1.0)
    Z = standardize(D["X"], mu, sd)
    widths = tuple(int(w) for w in args.width.split(","))
    wbits = tuple(int(b) for b in args.wbits.split(",")); abits = tuple(int(b) for b in args.abits.split(","))
    T = load([args.test]) if args.test else None
    ZT = standardize(T["X"], mu, sd) if T is not None else None
    allT = np.ones(T["ych"].shape[0], bool) if T is not None else None
    rep = {}

    # --- 1. random forest: out-of-fold soft labels on the training runs, reference numbers on the held-out runs
    fit_idx = np.where(fit)[0]
    p_rf = np.zeros((n, 5), np.float32)
    rf_kw = dict(n_estimators=400, min_samples_leaf=2, n_jobs=8, random_state=args.seed, class_weight="balanced_subsample")
    for k, (a, b) in enumerate(GroupKFold(5).split(fit_idx, groups=D["run_id"][fit_idx])):
        for c in range(5):
            rf = RandomForestClassifier(**rf_kw).fit(Z[fit_idx[a]], D["ych"][fit_idx[a], c])
            p_rf[fit_idx[b], c] = rf.predict_proba(Z[fit_idx[b]])[:, 1]
    rf_full = [RandomForestClassifier(**rf_kw).fit(Z[fit], D["ych"][fit, c]) for c in range(5)]
    p_rf_te = np.stack([rf_full[c].predict_proba(Z[te])[:, 1] for c in range(5)], 1)
    rep["rf_test"], thr_rf = metrics(p_rf_te, D, te, "RF test-runs", fa_budget=args.fa_budget)
    rep["rf_test_rule"], _ = metrics(p_rf_te, D, te, "RF test-runs", thr_rf, rule=True)
    if T is not None:
        rep["rf_phase1"], _ = metrics(np.stack([rf_full[c].predict_proba(ZT)[:, 1] for c in range(5)], 1), T, allT, "RF phase1", thr_rf)
    p_soft = (1 - args.distill) * D["ych"] + args.distill * p_rf
    p_soft[~fit] = D["ych"][~fit]

    # --- 2. float MLP on the soft labels
    fl = build_float(widths); compile_(fl, 1e-3, args.amp_w)
    val = np.where(te & (D["tr"] == 0))[0]
    fl.fit(Z[fit], targets(D, np.where(fit)[0], p_soft), validation_data=(Z[val], targets(D, val, p_soft)),
           epochs=args.epochs, batch_size=128, verbose=0,
           callbacks=[keras.callbacks.EarlyStopping(monitor="val_loss", patience=40, restore_best_weights=True)])
    pf = fl.predict(Z, verbose=0)
    pc = 1 / (1 + np.exp(-pf[0]))
    rep["float_train"], thr_f = metrics(pc[fit], D, fit, "float train", fa_budget=args.fa_budget)
    rep["float_test"], _ = metrics(pc[te], D, te, "float test-runs", thr_f)
    rep["float_test_rule"], _ = metrics(pc[te], D, te, "float test-runs", thr_f, rule=True)
    rep["float_amp_test"] = amp_metrics(pf[2][te], D, te, "float test-runs")
    if T is not None:
        pt = fl.predict(ZT, verbose=0)
        rep["float_phase1"], _ = metrics(1 / (1 + np.exp(-pt[0])), T, allT, "float phase1", thr_f)
        rep["float_phase1_rule"], _ = metrics(1 / (1 + np.exp(-pt[0])), T, allT, "float phase1", thr_f, rule=True)

    # --- 3. HGQ2 copy + QAT fine-tune (on raw features: the Affine layer standardizes inside the model)
    q = build_q(widths, wbits, abits, mu=mu, sd=sd)
    for name in [f"dense{i}" for i in range(len(widths))] + ["head"]:
        lyr = q.get_layer(name); W, b = fl.get_layer(name).get_weights()
        lyr.set_weights([W.astype(np.float32), b.astype(np.float32)] + lyr.get_weights()[2:])
    Xraw = np.where(np.isfinite(D["X"]), D["X"], mu).astype(np.float32)
    pq0 = q.predict(Xraw[te], verbose=0)
    rep["q_init_test"], _ = metrics(1 / (1 + np.exp(-pq0[0])), D, te, "HGQ2 init test-runs", thr_f)
    compile_(q, 3e-4, args.amp_w)
    q.fit(Xraw[fit], targets(D, np.where(fit)[0], p_soft), validation_data=(Xraw[val], targets(D, val, p_soft)),
          epochs=args.ft_epochs, batch_size=128, verbose=0,
          callbacks=[keras.callbacks.EarlyStopping(monitor="val_loss", patience=20, restore_best_weights=True)])
    pq = q.predict(Xraw, verbose=0); pcq = 1 / (1 + np.exp(-pq[0]))
    rep["q_train"], thr_q = metrics(pcq[fit], D, fit, "HGQ2 QAT train", fa_budget=args.fa_budget)
    rep["q_test"], _ = metrics(pcq[te], D, te, "HGQ2 QAT test-runs", thr_q)
    rep["q_test_rule"], _ = metrics(pcq[te], D, te, "HGQ2 QAT test-runs", thr_q, rule=True)
    rep["q_amp_test"] = amp_metrics(pq[2][te], D, te, "HGQ2 QAT test-runs")
    if T is not None:
        XT = np.where(np.isfinite(T["X"]), T["X"], mu).astype(np.float32)
        pt = q.predict(XT, verbose=0)
        rep["q_phase1"], _ = metrics(1 / (1 + np.exp(-pt[0])), T, allT, "HGQ2 QAT phase1", thr_q)
        rep["q_phase1_rule"], _ = metrics(1 / (1 + np.exp(-pt[0])), T, allT, "HGQ2 QAT phase1", thr_q, rule=True)
        rep["q_amp_phase1"] = amp_metrics(pt[2], T, allT, "HGQ2 QAT phase1")

    # --- 4. save: full model, board chain on standardized input, config
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    q.save(out / "model.keras")
    chain = build_q(widths, wbits, abits, standardized_input=True)
    for name in [f"dense{i}" for i in range(len(widths))] + ["head"]:
        chain.get_layer(name).set_weights(q.get_layer(name).get_weights())
    chk = chain.predict(standardize(D["X"][:512], mu, sd), verbose=0); ref = q.predict(Xraw[:512], verbose=0)
    print(f"standardized-input chain vs full model max |d| (512 samples): logits {np.abs(chk[:, :5] - ref[0]).max():.4g}  amp {np.abs(chk[:, 5:] - ref[2]).max():.4g}")
    chain.save(out / "chain_std.keras")
    json.dump(dict(version=5, features=FEATURE_NAMES_V3, mu=mu.tolist(), sd=sd.tolist(), thr=thr_q.tolist(), persist=2, hyst=0.6,
                   width=list(widths), wbits=args.wbits, abits=args.abits, head=10, params=int(chain.count_params()),
                   amp_scale=dict(Vdc=100.0, Vac=40.0, Iac=20.0, Vbat=25.0, Ibat=8.0)), open(out / "detector.json", "w"), indent=1)
    json.dump(rep, open(out / "report.json", "w"), indent=1)
    print(f"params {chain.count_params()} saved {out}")


if __name__ == "__main__":
    main()
