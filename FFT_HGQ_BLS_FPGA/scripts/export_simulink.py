#!/usr/bin/env python3
"""Export trained models to ONNX with a Simulink contract and parity test."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", choices=("mlp", "rnn", "transformer", "residual_bls"), required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--parity-examples", type=int, default=16)
    parser.add_argument("--backend", default=os.environ.get("HGQ_BACKEND", "torch"))
    args = parser.parse_args()
    os.environ["KERAS_BACKEND"] = args.backend
    os.environ["HGQ_BACKEND"] = args.backend

    from hgq_model.config import load_json, resolve_path
    from hgq_model.deployment import export_for_simulink

    config = load_json(args.config)
    project_dir = args.config.resolve().parent.parent
    dataset_path = args.dataset or resolve_path(config["paths"]["dataset"], relative_to=project_dir)
    run_dir = resolve_path(config["paths"]["run_dir"], relative_to=project_dir)
    export_root = resolve_path(config["paths"]["export_dir"], relative_to=project_dir)
    model_path = args.model_path or run_dir / args.model / "model.keras"
    output_dir = args.output or export_root / args.model
    manifest = export_for_simulink(
        args.model,
        model_path,
        dataset_path,
        output_dir,
        parity_examples=args.parity_examples,
    )
    print(f"exported {args.model}: {output_dir} (ONNX max_abs_error={manifest['parity']['max_abs_error']:.3g})")


if __name__ == "__main__":
    main()
