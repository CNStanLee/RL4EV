"""Alkaid conversion gate and bit-exact ALIR parity checks."""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("KERAS_BACKEND", os.environ.get("HGQ_BACKEND", "torch"))

from pathlib import Path
from typing import Any

import hgq
import keras
import numpy as np

from .config import save_json
from .data import load_dataset
from .models import load_model


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_alkaid_conversion(
    model_name: str,
    model_path: str | Path,
    dataset_path: str | Path,
    output_dir: str | Path,
    *,
    parity_examples: int = 16,
    input_kif: tuple[int, int, int] = (1, 1, 8),
) -> dict[str, Any]:
    """Trace a Keras model to ALIR and require exact simulator parity.

    This is a conversion/functional gate, not FPGA synthesis or timing signoff.
    ``input_kif`` represents the normalized signed input at the hardware port.
    """

    try:
        import alkaid
        from alkaid.converter import trace_model
        from alkaid.trace import HWConfig, trace
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Alkaid validation needs the `hardware` export extra") from exc

    model_path = Path(model_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model = load_model(str(model_path), compile=False)

    symbolic_input, symbolic_output = trace_model(
        model,
        HWConfig(1, 1, -1),
        {"hard_dc": 5},
        verbose=False,
        inputs_kif=input_kif,
    )
    logic = trace(symbolic_input, symbolic_output, optimize=True)

    split = load_dataset(dataset_path)["test_id"]
    count = min(max(int(parity_examples), 1), len(split))
    x = np.asarray(split.waveform_norm[:count], dtype=np.float32)
    expected = np.asarray(model.predict(x, verbose=0), dtype=np.float64).reshape(count, -1)
    actual = np.asarray(logic.predict(x, n_threads=1), dtype=np.float64).reshape(count, -1)
    difference = actual - expected
    exact = bool(np.array_equal(actual, expected))
    if not exact:
        raise RuntimeError(f"Alkaid parity failed for {model_name}: max_abs_error={np.max(np.abs(difference)):.3g}")

    alir_path = output_dir / f"harmonic_{model_name}.alir.json.gz"
    logic.save(alir_path)
    manifest = {
        "model": model_name,
        "source_keras_model": model_path.name,
        "source_keras_sha256": _sha256(model_path),
        "alkaid_version": alkaid.__version__,
        "hgq2_version": getattr(hgq, "__version__", "unknown"),
        "keras_backend": keras.backend.backend(),
        "input_kif": list(input_kif),
        "input_shape": [80, 1],
        "output_shape": [8],
        "alir_file": alir_path.name,
        "alir_bytes": int(alir_path.stat().st_size),
        "alir_sha256": _sha256(alir_path),
        "parity_examples": count,
        "parity": {
            "exact": exact,
            "max_abs_error": float(np.max(np.abs(difference))),
            "mean_abs_error": float(np.mean(np.abs(difference))),
        },
        "warning": "ALIR parity does not replace RTL synthesis, timing closure, or SIL/PIL/HIL validation.",
    }
    save_json(output_dir / "alkaid_manifest.json", manifest)
    return manifest


__all__ = ["check_alkaid_conversion"]
