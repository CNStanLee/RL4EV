"""ONNX/Simulink export with numerical parity and contract artifacts."""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("KERAS_BACKEND", os.environ.get("HGQ_BACKEND", "torch"))

from pathlib import Path
from typing import Any

import keras
import numpy as np
from scipy.io import savemat

from .config import save_json
from .contract import FS_HZ, HARMONICS, ORDER_SCALES, WINDOW_SIZE, decode_targets
from .data import load_dataset
from .models import load_model


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _onnx_parity(onnx_path: Path, x: np.ndarray, expected: np.ndarray) -> dict[str, Any]:
    try:
        import onnx
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("ONNX parity needs the `onnx` export extra") from exc
    onnx.checker.check_model(onnx.load(onnx_path))
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_info = session.get_inputs()[0]
    output_info = session.get_outputs()[0]
    actual = np.asarray(session.run([output_info.name], {input_info.name: x})[0])
    difference = actual.astype(np.float64) - expected.astype(np.float64)
    return {
        "input_name": input_info.name,
        "input_shape": [str(value) for value in input_info.shape],
        "output_name": output_info.name,
        "output_shape": [str(value) for value in output_info.shape],
        "max_abs_error": float(np.max(np.abs(difference))),
        "mean_abs_error": float(np.mean(np.abs(difference))),
        "allclose_atol_1e_6": bool(np.allclose(actual, expected, rtol=1.0e-6, atol=1.0e-6)),
    }


def export_for_simulink(
    model_name: str,
    model_path: str | Path,
    dataset_path: str | Path,
    output_dir: str | Path,
    *,
    parity_examples: int = 16,
) -> dict[str, Any]:
    """Export a fixed-window ONNX graph plus MATLAB-readable contract data."""

    model_path = Path(model_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = load_dataset(dataset_path)
    split = dataset["test_id"]
    count = min(max(int(parity_examples), 1), len(split))
    x = np.asarray(split.waveform_norm[:count], dtype=np.float32)
    model = load_model(str(model_path), compile=False)
    expected = np.asarray(model.predict(x, verbose=0), dtype=np.float32)

    onnx_path = output_dir / f"harmonic_{model_name}.onnx"
    model.export(onnx_path, format="onnx", verbose=False)
    parity = _onnx_parity(onnx_path, x, expected)
    if not parity["allclose_atol_1e_6"]:
        raise RuntimeError(f"ONNX parity failed for {model_name}: max_abs_error={parity['max_abs_error']:.3g}")

    first_decoded = decode_targets(expected[:1], split.scale[:1])
    contract = {
        "model": model_name,
        "input": {
            "name": parity["input_name"],
            "dtype": "float32",
            "shape": ["batch", WINDOW_SIZE, 1],
            "normalization": "x / max(abs(x))",
            "window_peak_is_external_side_channel": True,
        },
        "output": {
            "name": parity["output_name"],
            "dtype": "float32",
            "shape": ["batch", 8],
            "order": ["c1", "s1", "c3", "s3", "c5", "s5", "c7", "s7"],
            "encoding": "A_h/(window_peak*order_scale_h) * [cos(psi_end_h), sin(psi_end_h)]",
        },
        "sampling_rate_hz": FS_HZ,
        "window_size": WINDOW_SIZE,
        "window_duration_ms": 1000.0 * WINDOW_SIZE / FS_HZ,
        "harmonics": HARMONICS.tolist(),
        "order_scales": ORDER_SCALES.tolist(),
        "waveform_convention": "A_h * sin(2*pi*h*f0*(t-t_end) + psi_end_h)",
        "relative_phase": "wrap(psi_end_h - h*theta_pll_end), or use predicted psi1 as fallback reference",
        "physical_extended_output": ["A1", "A3", "A5", "A7", "psi1", "psi3", "psi5", "psi7"],
        "legacy_control_output": ["A1", "A3", "A5", "A7", "delta3", "delta5", "delta7"],
    }
    save_json(output_dir / "contract.json", contract)
    savemat(
        output_dir / "contract.mat",
        {
            "fs_hz": np.asarray([[FS_HZ]], dtype=np.float32),
            "window_size": np.asarray([[WINDOW_SIZE]], dtype=np.int32),
            "harmonics": HARMONICS.astype(np.int32)[None, :],
            "order_scales": ORDER_SCALES.astype(np.float32)[None, :],
            "waveform_raw_80x1": split.raw_waveform[0, :, None],
            "waveform_normalized_80x1": split.waveform_norm[0],
            "window_peak": split.scale[0:1],
            "network_output_1x8": expected[0:1],
            "amplitude_1x4": first_decoded.amplitude,
            "phase_end_1x4": first_decoded.phase_end,
            "phase_relative_1x4": first_decoded.phase_relative,
        },
        do_compression=True,
    )
    manifest = {
        "model": model_name,
        "source_keras_model": model_path.name,
        "source_keras_sha256": _sha256(model_path),
        "onnx_file": onnx_path.name,
        "onnx_bytes": int(onnx_path.stat().st_size),
        "onnx_sha256": _sha256(onnx_path),
        "parity_examples": count,
        "parity": parity,
        "keras_backend": keras.backend.backend(),
        "warning": (
            "ONNX host parity is not an HLS timing or bit-accurate RTL result; "
            "complete SIL/PIL/HIL and closed-loop stability validation before control use."
        ),
    }
    save_json(output_dir / "deployment_manifest.json", manifest)
    return manifest


__all__ = ["export_for_simulink"]
