"""SIL parity: compare the Simulink detector record (<run>_det.csv, per cycle) with
the Python feature pipeline on the same run's 10 kHz time series, and the ONNX
outputs recomputed in onnxruntime from the Simulink features.

    python scripts/sil_parity.py <ts_dir> <run_id>_<variant> [--onnx artifacts/detector.onnx]

Reports per-feature max abs / relative error (Simulink vs Python, aligned by
cycle end time), and max |raw| error between Simulink's ONNX outputs and
onnxruntime(features_simulink).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emi_det.features import FEATURE_NAMES, cycle_features, vref_series  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ts_dir"); ap.add_argument("run"); ap.add_argument("--onnx", default=str(Path(__file__).resolve().parents[1] / "artifacts" / "detector.onnx"))
    ap.add_argument("--vref-t", type=float, default=0.0); ap.add_argument("--vref-dv", type=float, default=0.0)
    args = ap.parse_args()
    ts = pd.read_csv(Path(args.ts_dir) / f"{args.run}.csv"); det = pd.read_csv(Path(args.ts_dir) / f"{args.run}_det.csv")
    cf = cycle_features(ts, vref_series(ts["t"].to_numpy(), args.vref_t, args.vref_dv))
    fcols = [c for c in det.columns if c.startswith("f")][:len(FEATURE_NAMES)]
    Fs = det[fcols].to_numpy(); ts_end = det["t"].to_numpy()
    # Simulink emits the feature vector at the buffer output time (= cycle end); align on cycle end time
    idx = {round(t, 4): i for i, t in enumerate(np.round(cf.t, 4))}
    pairs = [(i, idx[round(t, 4)]) for i, t in enumerate(np.round(ts_end, 4)) if round(t, 4) in idx]
    if not pairs:
        # try a one-sample offset (Simulink timestamps the buffer at the first sample of the next cycle)
        idx2 = {round(t - 0.02, 4): i for i, t in enumerate(np.round(cf.t, 4))}
        pairs = [(i, idx2[round(t, 4)]) for i, t in enumerate(np.round(ts_end, 4)) if round(t, 4) in idx2]
    print(f"cycles: simulink {len(det)}, python {cf.t.size}, aligned {len(pairs)}")
    A = Fs[[p[0] for p in pairs]]; B = cf.X[[p[1] for p in pairs]]
    worst = []
    for k, name in enumerate(FEATURE_NAMES):
        a = A[:, k]; b = B[:, k]; err = np.abs(a - b); scale = np.maximum(np.abs(b).max(), 1e-6)
        worst.append((err.max() / scale, name, err.max(), scale))
    worst.sort(reverse=True)
    print("worst relative feature errors (rel, name, abs, scale):")
    for w in worst[:10]:
        print(f"  {w[0]:9.2e}  {w[1]:18s}  abs {w[2]:.3g}  scale {w[3]:.3g}")
    ok = sum(1 for w in worst if w[0] < 1e-3)
    print(f"features within 1e-3 relative: {ok}/{len(FEATURE_NAMES)}")
    try:
        import onnxruntime as ort
        s = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"])
        rcols = [c for c in det.columns if c.startswith("raw")]
        raw_sim = det[rcols].to_numpy()
        outs = s.run(None, {s.get_inputs()[0].name: Fs.astype(np.float32)})
        raw_py = np.concatenate([np.asarray(o).reshape(len(det), -1) for o in outs], axis=1)
        print(f"ONNX raw outputs: simulink vs onnxruntime(simulink features) max abs {np.abs(raw_sim - raw_py).max():.3g}")
    except Exception as e:
        print("onnx check skipped:", e)


if __name__ == "__main__":
    main()
