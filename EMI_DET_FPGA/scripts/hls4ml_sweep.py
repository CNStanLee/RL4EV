"""Resource / latency sweep of the two HGQ2 models with hls4ml (Vitis backend, bit_exact).

    python scripts/hls4ml_sweep.py detector  --rf 1 4 8 16      --out /path/sweep
    python scripts/hls4ml_sweep.py estimator --rf 4 8 16 32 64  --out /path/sweep
    python scripts/hls4ml_sweep.py detector  --rf 8 --out ... --firmware HLS_PRJ/emi_detector/firmware   # export chosen point

For every ReuseFactor the bare network is converted (RF 1 -> Latency strategy, RF > 1 -> Resource),
its C model is checked against Keras on the component's test vectors (must be bit-exact: max |d| = 0),
and Vitis HLS csynth is run (vitis_hls on PATH; 2022.2 works).  One row per point goes to
<out>/<model>_sweep.csv: LUT, FF, DSP, BRAM, latency (cycles / us at 100 MHz), II, and the
interval-limited throughput.  --firmware copies the generated firmware/ of the (single) chosen point
over the board component (the AXI wrapper in HLS_PRJ is unchanged: same top name, same I/O types).

Models:
  detector : EMI_DET_FPGA/runs/det_v4/chain_std.keras (43 standardized features -> 5 channel logits)
  estimator: FFT_HGQ_BLS_FPGA/artifacts/hgq_residual_bls.keras (80 normalized samples -> 8 phasor components)
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("KERAS_BACKEND", "torch")
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]          # EMI_DET_FPGA
REPO = ROOT.parent

MODELS = {
    "detector": dict(
        keras=ROOT / "runs/det_v5/chain_std.keras",
        project="emi_detector",
        # standardized inputs of the tb vectors of the board component (raw -> (x-mu)*inv_sd)
        tb=lambda: _detector_inputs(),
    ),
    "estimator": dict(
        keras=REPO / "FFT_HGQ_BLS_FPGA/artifacts/hgq_residual_bls.keras",
        project="harmonic_estimator",
        tb=lambda: _estimator_inputs(),
    ),
}


def _detector_inputs() -> np.ndarray:
    import json

    j = json.load(open(ROOT / "artifacts/detector.json"))
    mu = np.asarray(j["mu"], np.float32); sd = np.asarray(j["sd"], np.float32)
    if int(j.get("version", 4)) >= 5:      # 48 features: every 8th cycle of the v3 supplement set, by feature name
        d = np.load(ROOT / "data/cycles_v3_supp.npz", allow_pickle=True)
        names = [str(n) for n in d["feature_names"]]
        X = np.stack([d["X"][::8, names.index(n)] if n in names else np.full(d["X"][::8].shape[0], np.nan) for n in j["features"]], 1)
        raw = np.where(np.isfinite(X), X, mu).astype(np.float32)
    else:
        raw = np.loadtxt(REPO / "HLS_PRJ/emi_detector/tb_data/feat_raw.dat", dtype=np.float32)
    return ((raw - mu) / sd).astype(np.float32)


def _estimator_inputs() -> np.ndarray:
    raw = np.loadtxt(REPO / "HLS_PRJ/harmonic_estimator/tb_data/wave_raw.dat", dtype=np.float32)
    peak = np.maximum(np.max(np.abs(raw), axis=1, keepdims=True), 1e-6)
    return (raw / peak).astype(np.float32)[..., None]


def convert(name: str, rf: int, out: Path, part: str, clock_ns: float, io_type: str = "io_parallel", pipeline: bool = False):
    import hgq  # noqa: F401  (registers the HGQ2 layers for keras.models.load_model)
    import hls4ml
    import keras

    spec = MODELS[name]
    model = keras.models.load_model(spec["keras"], compile=False)
    cfg = hls4ml.utils.config_from_keras_model(model, granularity="name", backend="Vitis", default_reuse_factor=rf)
    strategy = "Latency" if rf == 1 else "Resource"
    cfg["Model"]["Strategy"] = strategy
    cfg["Model"]["ReuseFactor"] = rf
    # hls4ml only accepts reuse factors that tile n_in x n_out (e.g. a 43-input layer allows 1, 43, 86, ...);
    # per layer take the smallest valid value >= the requested one and report the choice.
    backend = hls4ml.backends.get_backend("Vitis")
    per_layer = {}
    for lname, lcfg in cfg.get("LayerName", {}).items():
        lcfg["Strategy"] = strategy
        lyr = model.get_layer(lname) if lname in [l.name for l in model.layers] else None
        w = lyr.get_weights()[0] if lyr is not None and lyr.get_weights() else None
        if w is not None and w.ndim == 2:
            valid = backend.get_valid_reuse_factors(int(w.shape[0]), int(w.shape[1]))
            chosen = min([v for v in valid if v >= rf] or [valid[-1]])
            lcfg["ReuseFactor"] = int(chosen); per_layer[lname] = int(chosen)
        else:
            lcfg["ReuseFactor"] = rf
    if pipeline:
        # one pipelined top function instead of a dataflow chain: hls4ml's dataflow FIFOs between the
        # io_parallel layers cost more LUT/FF than the layers themselves (estimator RF 64: 111k LUT, 165k FF in FIFOs)
        cfg["Model"]["PipelineStyle"] = "pipeline"
        cfg["Model"]["PipelineInterval"] = max(per_layer.values()) if per_layer else rf
    print(f"[{name} rf={rf}{' pipeline' if pipeline else ''}] per-layer reuse factors: {per_layer}", flush=True)
    hm = hls4ml.converters.convert_from_keras_model(
        model, hls_config=cfg, output_dir=str(out), project_name=spec["project"], backend="Vitis",
        part=part, clock_period=clock_ns, io_type=io_type, bit_exact=True,
    )
    hm.compile()
    x = spec["tb"]()
    y_k = np.asarray(model.predict(x, verbose=0), np.float64).reshape(len(x), -1)
    y_h = np.asarray(hm.predict(x), np.float64).reshape(len(x), -1)
    d = np.abs(y_k - y_h)
    return hm, float(d.max()), float(np.sqrt((d ** 2).mean()))


def synth(hm, out: Path) -> dict:
    t0 = time.time()
    # hls4ml 1.3's Vitis backend insists on `vitis-run` (2023.2+); the generated build_prj.tcl runs fine
    # under vitis_hls 2022.2, so call that directly.
    import subprocess

    with open(out / "vitis_hls_synth.log", "w") as log:
        subprocess.run(["vitis_hls", "-f", "build_prj.tcl", "reset=1 csim=0 synth=1 cosim=0 validation=0 export=0 vsynth=0"],
                       cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True)
    import hls4ml

    rep = hls4ml.report.parse_vivado_report(str(out))
    cs = rep.get("CSynthesisReport", {})
    return dict(
        wall_s=round(time.time() - t0),
        lut=cs.get("LUT"), ff=cs.get("FF"), dsp=cs.get("DSP48E", cs.get("DSP")), bram=cs.get("BRAM_18K"),
        lat_min=cs.get("BestLatency"), lat_max=cs.get("WorstLatency"),
        ii_min=cs.get("IntervalMin"), ii_max=cs.get("IntervalMax"),
        est_clk_ns=cs.get("EstimatedClockPeriod"),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=list(MODELS))
    ap.add_argument("--rf", type=int, nargs="+", default=[1])
    ap.add_argument("--out", required=True)
    ap.add_argument("--part", default="xczu7ev-ffvc1156-2-e")
    ap.add_argument("--clock-ns", type=float, default=10.0)
    ap.add_argument("--no-synth", action="store_true")
    ap.add_argument("--firmware", help="copy the firmware of the single requested point onto this directory")
    ap.add_argument("--pipeline", action="store_true", help="PipelineStyle=pipeline (no dataflow FIFOs) with II = max reuse factor")
    ap.add_argument("--tag", default="", help="suffix for the project directory name")
    ap.add_argument("--io-stream", action="store_true", help="io_stream between layers (one packed FIFO per layer instead of one FIFO per element)")
    ap.add_argument("--no-dataflow", action="store_true",
                    help="drop the top-level DATAFLOW pragma after conversion: layers run sequentially without the per-element "
                         "FIFOs (latency = sum of the layer latencies, II = latency; enough for one inference per grid cycle)")
    a = ap.parse_args()
    if a.firmware and len(a.rf) != 1:
        sys.exit("--firmware needs exactly one --rf")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{a.model}_sweep.csv"
    rows = []
    for rf in a.rf:
        d = out / f"{a.model}_rf{rf}{'_pipe' if a.pipeline else ''}{'_stream' if a.io_stream else ''}{'_seq' if a.no_dataflow else ''}{a.tag}"
        if d.exists():
            shutil.rmtree(d)
        hm, dmax, drms = convert(a.model, rf, d, a.part, a.clock_ns, io_type="io_stream" if a.io_stream else "io_parallel", pipeline=a.pipeline)
        if a.no_dataflow:
            top = d / "firmware" / f"{MODELS[a.model]['project']}.cpp"
            src = top.read_text()
            assert "#pragma HLS DATAFLOW" in src, "no DATAFLOW pragma to remove"
            top.write_text(src.replace("#pragma HLS DATAFLOW", "// #pragma HLS DATAFLOW  (removed by hls4ml_sweep.py --no-dataflow: sequential layers, no element FIFOs)"))
        row = dict(model=a.model, rf=rf, strategy="Latency" if rf == 1 else "Resource",
                   style=("pipeline" if a.pipeline else ("sequential" if a.no_dataflow else "dataflow")) + ("+stream" if a.io_stream else ""),
                   cmodel_max_abs_diff=dmax, cmodel_rms_diff=drms)
        print(f"[{a.model} rf={rf}] C model vs Keras: max |d| = {dmax:.3g}, rms {drms:.3g}", flush=True)
        if not a.no_synth:
            row.update(synth(hm, d))
            print(f"[{a.model} rf={rf}] " + ", ".join(f"{k}={v}" for k, v in row.items() if k not in ("model", "rf")), flush=True)
        rows.append(row)
        if a.firmware:
            dst = Path(a.firmware)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(d / "firmware", dst)
            print(f"firmware -> {dst}")
        # append as we go so a killed sweep still leaves its rows
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if f.tell() == 0:
                w.writeheader()
            w.writerow(row)
    print(f"rows -> {csv_path}")


if __name__ == "__main__":
    main()
