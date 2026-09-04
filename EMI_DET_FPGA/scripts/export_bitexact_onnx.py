"""Bit-exact ONNX of the HGQ2 detector chain (the board arithmetic), replacing the
Keras/torch export.

    CUDA_VISIBLE_DEVICES=-1 KERAS_BACKEND=torch python scripts/export_bitexact_onnx.py runs/det_v4 [--out artifacts/detector_bitexact.onnx]

Keras' ONNX exporter maps the HGQ2 fixed-point quantizers to `Round` (round half
to even).  HGQ2 itself, and the hls4ml firmware (ap_fixed AP_RND), round half
UP; because activations and weights sit on a 2^-7 grid the accumulators are
exact multiples of 2^-14 and ties are frequent, so the exported ONNX differed
from the trained network on almost every cycle (max |dlogit| 4.3, 68/8709 flag
decisions).  This script builds the graph explicitly: standardization
(Sub mu, Mul inv_sd) -> per layer: Q_in(x) = clip(floor(x*2^f + 0.5)/2^f)
(SAT), Gemm with the quantized kernel/bias, Relu -> the same three outputs as
the Keras export ([5] channel logits, [10] zeros, [1] zero) so it is a drop-in
for OnnxRunner / onnx_bridge.  Verified against the Keras chain on the whole
dataset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("KERAS_BACKEND", "torch"); os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
import keras  # noqa: E402
import hgq  # noqa: E402,F401
import onnx  # noqa: E402
from onnx import TensorProto, helper, numpy_helper  # noqa: E402

keras.config.enable_unsafe_deserialization()
ROOT = Path(__file__).resolve().parents[1]


def npy(t):
    try:
        return t.detach().cpu().numpy()
    except AttributeError:
        return np.asarray(t)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir"); ap.add_argument("--out", default=str(ROOT / "artifacts/detector_bitexact.onnx"))
    ap.add_argument("--data", default=str(ROOT / "data/cycles_dataset.npz")); a = ap.parse_args()
    run = Path(a.run_dir); cfg = json.load(open(run / "detector.json"))
    mu = np.array(cfg["mu"], np.float32); inv = (1.0 / np.array(cfg["sd"], np.float32)).astype(np.float32)
    ab = tuple(int(b) for b in cfg["abits"].split(",")); i_bits, f_bits = ab
    chain = keras.models.load_model(run / "chain_std.keras", compile=False)
    names = [f"dense{i}" for i in range(len(cfg["width"]))] + ["chan"]
    n_in = len(cfg["features"])
    inits = [numpy_helper.from_array(mu, "mu"), numpy_helper.from_array(inv, "inv_sd"),
             numpy_helper.from_array(np.array(2.0 ** f_bits, np.float32), "scale"), numpy_helper.from_array(np.array(2.0 ** -f_bits, np.float32), "inv_scale"),
             numpy_helper.from_array(np.array(0.5, np.float32), "half"), numpy_helper.from_array(np.array(-(2.0 ** i_bits), np.float32), "q_lo"),
             numpy_helper.from_array(np.array(2.0 ** i_bits - 2.0 ** -f_bits, np.float32), "q_hi"),
             numpy_helper.from_array(np.zeros((1, 10), np.float32), "zeros10"), numpy_helper.from_array(np.zeros((1, 1), np.float32), "zeros1")]
    nodes = [helper.make_node("Sub", ["features", "mu"], ["x_c"]), helper.make_node("Mul", ["x_c", "inv_sd"], ["x_std"])]
    h = "x_std"
    for k, name in enumerate(names):
        l = chain.get_layer(name); W = npy(l.qkernel).astype(np.float32); b = npy(l.qbias).astype(np.float32)
        assert np.abs(W * 2.0 ** f_bits - np.round(W * 2.0 ** f_bits)).max() == 0, "kernel not on the 2^-f grid"
        inits += [numpy_helper.from_array(W, f"W{k}"), numpy_helper.from_array(b, f"b{k}")]
        # input quantizer: round half up, saturate
        nodes += [helper.make_node("Mul", [h, "scale"], [f"s{k}"]), helper.make_node("Add", [f"s{k}", "half"], [f"sh{k}"]),
                  helper.make_node("Floor", [f"sh{k}"], [f"fl{k}"]), helper.make_node("Mul", [f"fl{k}", "inv_scale"], [f"qu{k}"]),
                  helper.make_node("Clip", [f"qu{k}", "q_lo", "q_hi"], [f"q{k}"]),
                  helper.make_node("Gemm", [f"q{k}", f"W{k}", f"b{k}"], [f"z{k}"])]
        h = f"z{k}"
        if name != "chan":
            nodes += [helper.make_node("Relu", [h], [f"a{k}"])]; h = f"a{k}"
    nodes += [helper.make_node("Identity", [h], ["chan_logits"]),
              helper.make_node("Shape", ["features"], ["shp"]), helper.make_node("Slice", ["shp", "sl0", "sl1"], ["nb"]),
              helper.make_node("Concat", ["nb", "c10"], ["shape10"], axis=0), helper.make_node("Concat", ["nb", "c1"], ["shape1"], axis=0),
              helper.make_node("Expand", ["zeros10", "shape10"], ["logits"]), helper.make_node("Expand", ["zeros1", "shape1"], ["amp"])]
    inits += [numpy_helper.from_array(np.array([0], np.int64), "sl0"), numpy_helper.from_array(np.array([1], np.int64), "sl1"),
              numpy_helper.from_array(np.array([10], np.int64), "c10"), numpy_helper.from_array(np.array([1], np.int64), "c1")]
    g = helper.make_graph(nodes, "emi_det_v4_bitexact", [helper.make_tensor_value_info("features", TensorProto.FLOAT, ["batch", n_in])],
                          [helper.make_tensor_value_info("chan_logits", TensorProto.FLOAT, ["batch", 5]),
                           helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", 10]),
                           helper.make_tensor_value_info("amp", TensorProto.FLOAT, ["batch", 1])], initializer=inits)
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 17)], producer_name="export_bitexact_onnx"); m.ir_version = 8
    onnx.checker.check_model(m); onnx.save(m, a.out)
    import onnxruntime as ort
    s = ort.InferenceSession(a.out, providers=["CPUExecutionProvider"])
    D = np.load(a.data); X = np.nan_to_num(D["X"][:, :n_in].astype(np.float32))
    ref = chain.predict((X - mu) * inv, batch_size=4096, verbose=0); got = s.run(None, {"features": X})
    d = np.abs(np.asarray(got[0]) - ref); thr = np.array(cfg["thr"]); lt = np.log(thr / (1 - thr))
    print(f"bit-exact ONNX vs Keras chain over {len(X)} cycles: max |dlogit| {d.max():.3g}  rows > 1e-3: {int((d.max(1) > 1e-3).sum())}  "
          f"flag disagreements {int(((np.asarray(got[0]) >= lt) != (ref >= lt)).sum())}  outputs {[np.asarray(o).shape[1] for o in got]}")
    print("written", a.out)


if __name__ == "__main__":
    main()
