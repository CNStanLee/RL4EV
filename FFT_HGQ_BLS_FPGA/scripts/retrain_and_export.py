#!/usr/bin/env python3
"""Retrain HGQ2 Residual-BLS and refresh Simulink/FPGA artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str], *, project_dir: Path) -> None:
    environment = dict(os.environ)
    environment["KERAS_BACKEND"] = "torch"
    environment["HGQ_BACKEND"] = "torch"
    subprocess.run(command, cwd=project_dir, env=environment, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def refresh_manifest(project_dir: Path) -> None:
    path = project_dir / "MANIFEST.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    for relative in document["sha256"]:
        target = project_dir / relative
        if target.is_file():
            document["sha256"][relative] = sha256(target)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    scripts = project_dir / "scripts"
    config = project_dir / "config" / "training.json"
    python = sys.executable

    run(
        [python, str(scripts / "train_model.py"), "--config", str(config), "--model", "residual_bls"],
        project_dir=project_dir,
    )
    run(
        [python, str(scripts / "export_simulink.py"), "--config", str(config), "--model", "residual_bls"],
        project_dir=project_dir,
    )
    generated = project_dir / "artifacts" / "pv_mev_hgq_residual_bls" / "residual_bls"
    run(
        [
            python,
            str(scripts / "wrap_onnx_for_pv_mev.py"),
            "--input",
            str(generated / "harmonic_residual_bls.onnx"),
            "--output",
            str(project_dir / "artifacts" / "harmonic_residual_bls_simulink.onnx"),
            "--opset",
            "18",
        ],
        project_dir=project_dir,
    )
    run(
        [python, str(scripts / "check_alkaid.py"), "--config", str(config), "--model", "residual_bls"],
        project_dir=project_dir,
    )

    trained = project_dir / "runs" / "pv_mev_hgq_residual_bls" / "residual_bls" / "model.keras"
    shutil.copy2(trained, project_dir / "artifacts" / "hgq_residual_bls.keras")
    for name in ("contract.json", "contract.mat", "deployment_manifest.json"):
        shutil.copy2(generated / name, project_dir / "artifacts" / name)
    for name in ("harmonic_residual_bls.alir.json.gz", "alkaid_manifest.json"):
        shutil.copy2(generated / name, project_dir / "artifacts" / name)
    refresh_manifest(project_dir)
    print("training and export complete; run MATLAB setup_project before simulation")


if __name__ == "__main__":
    main()
