#!/usr/bin/env python3
"""Train one HGQ2 architecture from a JSON experiment configuration."""

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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backend", default=os.environ.get("HGQ_BACKEND", "torch"))
    args = parser.parse_args()

    os.environ["KERAS_BACKEND"] = args.backend
    os.environ["HGQ_BACKEND"] = args.backend

    from hgq_model.config import load_json, resolve_path
    from hgq_model.training import train_model

    config = load_json(args.config)
    project_dir = args.config.resolve().parent.parent
    dataset_path = args.dataset or resolve_path(config["paths"]["dataset"], relative_to=project_dir)
    output_path = args.output or resolve_path(
        Path(config["paths"]["run_dir"]) / args.model,
        relative_to=project_dir,
    )
    train_model(
        args.model,
        dataset_path,
        output_path,
        model_config=config.get("model"),
        training_config=config.get("training"),
    )


if __name__ == "__main__":
    main()
