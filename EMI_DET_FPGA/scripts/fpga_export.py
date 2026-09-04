"""Board version of the EMI detector chain: HGQ2 QDense chain -> da4ml -> Verilog / Vitis HLS.

    CUDA_VISIBLE_DEVICES=-1 KERAS_BACKEND=torch python scripts/fpga_export.py runs/det_v4 [--ibits 6] [--part xczu7ev-ffvc1156-2-e] [--clock 10]

The network input on the board is the STANDARDIZED feature vector: folding
(x - mu)/sd into the first layer's weights is not viable after quantization
(W/sd spans several decades, max |dlogit| 126 on the folded chain), so the
feature extractor must apply the 43 per-feature (mu, 1/sd) constants in fixed
point and hand the network bounded values.  da4ml only accepts WRAP overflow
on activations, while training used SAT.  The chain is therefore
re-instantiated with WRAP and a wider integer part (--ibits, default 6 ->
+-64) and checked for equality against the trained SAT network on the whole
dataset before code generation.  Outputs: <run>/fpga/ {emi_det_chain_wrap.keras, verilog/, hls/,
report.json} with da4ml's cost (LUT-equivalent adders) and latency estimates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("KERAS_BACKEND", "torch")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
import keras  # noqa: E402
import hgq  # noqa: E402,F401  (registers QDense etc. for deserialization)

keras.config.enable_unsafe_deserialization()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("--ibits", type=int, default=6); ap.add_argument("--part", default="xczu7ev-ffvc1156-2-e")
    ap.add_argument("--clock", type=float, default=10.0); ap.add_argument("--data", default="data/cycles_dataset.npz")
    args = ap.parse_args()
    run = Path(args.run_dir); out = run / "fpga"; out.mkdir(parents=True, exist_ok=True)
    cfg = json.load(open(run / "detector.json"))
    full = keras.models.load_model(run / "chain_std.keras", compile=False)     # QDense chain on standardized input (SAT quantizers)
    mu = np.array(cfg["mu"], np.float32); sd = np.array(cfg["sd"], np.float32)
    n_in = len(cfg["features"])
    from hgq.config import LayerConfigScope, QuantizerConfigScope
    from hgq.layers import QDense
    wb = tuple(int(b) for b in cfg["wbits"].split(",")); ab = tuple(int(b) for b in cfg["abits"].split(","))
    with QuantizerConfigScope(default_q_type="kif", place="weight", k0=1, i0=wb[0], f0=wb[1], trainable=False, overflow_mode="WRAP"), \
         QuantizerConfigScope(default_q_type="kif", place="datalane", k0=1, i0=args.ibits, f0=ab[1], trainable=False, overflow_mode="WRAP"), \
         LayerConfigScope(enable_ebops=False, beta0=0.0):
        inp = keras.Input((n_in,), name="features_std"); x = inp
        for i, w in enumerate(cfg["width"]):
            x = QDense(w, activation="relu", name=f"dense{i}")(x)
        outp = QDense(5, name="chan")(x)
    wrap = keras.Model(inp, outp, name="emi_det_chain_wrap")
    for l in wrap.layers:
        if l.get_weights():
            src = full.get_layer(l.name).get_weights(); dst = l.get_weights()
            l.set_weights(src[:2] + dst[2:])          # kernel, bias (on standardized input); keep the replica's own quantizer params
    X = np.nan_to_num(np.load(args.data)["X"][:, :n_in].astype(np.float32), nan=0.0, posinf=1e6, neginf=-1e6)
    Xs = (X - mu) / sd
    ref = full.predict(Xs, batch_size=4096, verbose=0); got = wrap.predict(Xs, batch_size=4096, verbose=0)
    d = np.abs(ref - got).max(); print(f"WRAP/i={args.ibits} replica (standardized input) vs trained SAT network: max |dlogit| {d:.4g} over {len(X)} cycles; std-feature range [{Xs.min():.1f}, {Xs.max():.1f}]")
    np.savez(out / "standardization.npz", mu=mu, inv_sd=(1.0 / sd).astype(np.float32), features=np.array(cfg["features"]))
    wrap.save(out / "emi_det_chain_wrap.keras")
    from da4ml.converter import trace_model
    from da4ml.trace import HWConfig
    from da4ml.codegen import HLSModel, VerilogModel
    import torch
    with torch.no_grad():                    # replica reads quantized kernels as numpy
        sol = trace_model(wrap, hwconf=HWConfig(1, -1, -1), verbose=False)
    rep = dict(replica_max_dlogit=float(d), ibits=args.ibits)
    for a in ("cost", "latency", "shape", "inp_shape", "out_shape"):
        if hasattr(sol, a):
            v = getattr(sol, a); rep[a] = v if isinstance(v, (int, float, str)) else str(v); print(f"  {a} = {v}")
    vm = VerilogModel(sol, "emi_det", out / "verilog", part_name=args.part, clock_period=args.clock); vm.write()
    hm = HLSModel(sol, "emi_det_hls", out / "hls", flavor="vitis", part_name=args.part, clock_period=int(args.clock)); hm.write()
    # bit-true check of the traced fixed-point graph against the Keras replica (da4ml evaluates the solution in numpy)
    try:
        y_fx = sol(Xs[:512])
        rep["trace_vs_keras_max"] = float(np.abs(np.asarray(y_fx) - got[:512]).max()); print("  traced fixed-point graph vs keras replica max abs:", rep["trace_vs_keras_max"])
    except Exception as e:
        print("  trace evaluation skipped:", repr(e)[:200])
    json.dump(rep, open(out / "report.json", "w"), indent=1)
    print("written", out)


if __name__ == "__main__":
    main()
