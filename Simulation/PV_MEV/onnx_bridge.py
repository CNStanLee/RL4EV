"""Thin onnxruntime bridge for MATLAB (OnnxRunner.m).

MATLAB's in-process Python cannot wrap pybind11 objects such as
onnxruntime.SessionOptions, so sessions are kept here in a module-level
table and MATLAB only exchanges ints, floats and lists.
"""

from __future__ import annotations

import numpy as np
import onnxruntime as ort

_SESSIONS: dict[int, tuple[ort.InferenceSession, str, list[str]]] = {}
_NEXT = 1


def load(path: str, threads: int = 1) -> int:
    global _NEXT
    so = ort.SessionOptions()
    so.intra_op_num_threads = int(threads)
    so.inter_op_num_threads = 1
    s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    names = [o.name for o in s.get_outputs()]
    h = _NEXT; _NEXT += 1
    _SESSIONS[h] = (s, s.get_inputs()[0].name, names)
    return h


def num_outputs(h: int) -> int:
    return len(_SESSIONS[h][2])


def run(h: int, values, n_in: int) -> list:
    """values: flat list of floats (one sample).  Returns all outputs concatenated as a flat list."""
    s, in_name, _ = _SESSIONS[h]
    x = np.asarray(values, dtype=np.float32).reshape(1, int(n_in))
    outs = s.run(None, {in_name: x})
    return np.concatenate([np.asarray(o, dtype=np.float32).ravel() for o in outs]).tolist()


def close(h: int) -> None:
    _SESSIONS.pop(h, None)
