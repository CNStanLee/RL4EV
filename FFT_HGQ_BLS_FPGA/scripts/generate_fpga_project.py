#!/usr/bin/env python3
"""Generate a target-specific Alkaid RTL/HLS project from the packaged ALIR."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", help="FPGA part name, for example xczu7ev-ffvc1156-2-e")
    parser.add_argument("--flavor", choices=("verilog", "vhdl", "vitis", "hlslib", "oneapi"), default="verilog")
    parser.add_argument("--clock-ns", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=Path("build/fpga"))
    parser.add_argument("--validate-rtl", action="store_true")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parents[1]
    alir = project_dir / "artifacts" / "harmonic_residual_bls.alir.json.gz"
    if not alir.is_file():
        raise FileNotFoundError(alir)
    executable = shutil.which("alkaid")
    if executable is None:
        raise RuntimeError("alkaid is not installed; install requirements-fpga.txt first")
    output = args.output if args.output.is_absolute() else project_dir / args.output
    command = [
        executable,
        "convert",
        str(alir),
        str(output),
        "--flavor",
        args.flavor,
        "--clock-period",
        str(args.clock_ns),
        "--inputs-kif",
        "1",
        "1",
        "8",
    ]
    if args.part:
        command.extend(("--part-name", args.part))
    if args.validate_rtl:
        command.append("--validate-rtl")
    subprocess.run(command, check=True)
    print(f"generated {output}")


if __name__ == "__main__":
    main()
