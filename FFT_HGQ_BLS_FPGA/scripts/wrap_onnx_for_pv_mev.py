#!/usr/bin/env python3
"""Wrap HGQ2 ONNX as the existing PV_MEV 2-D input/output-name contract."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper, version_converter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--opset",
        type=int,
        default=18,
        help="Target ONNX opset supported by MATLAB's co-execution runtime.",
    )
    args = parser.parse_args()
    model = onnx.load(args.input)
    current_opset = next(item.version for item in model.opset_import if item.domain in ("", "ai.onnx"))
    if current_opset != args.opset:
        try:
            model = version_converter.convert_version(model, args.opset)
        except RuntimeError:
            # ONNX's converter has no 20->19 adapter for ConstantOfShape even
            # though the operator schema used by these exports is unchanged.
            # Restamping is accepted only after the target-opset checker validates
            # the complete graph below.
            if current_opset != 20 or args.opset not in (18, 19):
                raise
            for item in model.opset_import:
                if item.domain in ("", "ai.onnx"):
                    item.version = args.opset
            onnx.checker.check_model(model)
    graph = model.graph
    original_input = graph.input[0]
    original_output = graph.output[0]
    internal_input_name = original_input.name + "_3d"
    internal_output_name = original_output.name + "_internal"

    for node in graph.node:
        node.input[:] = [internal_input_name if name == original_input.name else name for name in node.input]
        node.output[:] = [internal_output_name if name == original_output.name else name for name in node.output]
    graph.ClearField("input")
    graph.input.append(helper.make_tensor_value_info("input", TensorProto.FLOAT, ["batch", 80]))
    graph.ClearField("output")
    graph.output.append(helper.make_tensor_value_info("output", TensorProto.FLOAT, ["batch", 8]))
    axes_name = "pv_mev_unsqueeze_axes"
    graph.initializer.append(numpy_helper.from_array(np.asarray([2], dtype=np.int64), name=axes_name))
    unsqueeze = helper.make_node("Unsqueeze", ["input", axes_name], [internal_input_name], name="PVMEVUnsqueeze")
    identity = helper.make_node("Identity", [internal_output_name], ["output"], name="PVMEVOutput")
    existing = list(graph.node)
    graph.ClearField("node")
    graph.node.extend([unsqueeze, *existing, identity])
    onnx.checker.check_model(model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, args.output)
    print(f"saved {args.output.resolve()}")


if __name__ == "__main__":
    main()
