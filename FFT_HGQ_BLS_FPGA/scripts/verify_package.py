#!/usr/bin/env python3
"""Verify packaged file hashes and, when available, the ONNX graph."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    manifest = json.loads((project_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    mutable = set(manifest.get("mutable_after_setup", ()))
    for name, expected in manifest["sha256"].items():
        path = project_dir / name
        actual = sha256(path)
        if actual != expected:
            if name in mutable:
                print(f"relocated artifact differs as expected: {name}")
            else:
                raise RuntimeError(f"hash mismatch: {name}: {actual} != {expected}")
    model_path = project_dir / manifest["simulink_model"]
    with zipfile.ZipFile(model_path) as archive:
        bad_member = archive.testzip()
    if bad_member is not None:
        raise RuntimeError(f"damaged Simulink archive member: {bad_member}")
    try:
        import onnx
    except ImportError:
        print("hashes and Simulink archive OK; install onnx to enable graph validation")
    else:
        onnx.checker.check_model(
            onnx.load(project_dir / "artifacts" / "harmonic_residual_bls_simulink.onnx")
        )
        print("hashes and ONNX graph OK")


if __name__ == "__main__":
    main()
