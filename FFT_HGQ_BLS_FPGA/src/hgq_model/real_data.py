"""Convert labeled Simulink/HIL waveform arrays to the shared NPZ contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

from .contract import FS_HZ, HARMONICS, WINDOW_SIZE, encode_targets, wrap_phase
from .data import SPLIT_NAMES, SplitData


def _string_array(values: ArrayLike, name: str) -> np.ndarray:
    value = np.asarray(values)
    if value.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if value.dtype == object:
        raise ValueError(f"{name} must use a fixed-width string/integer dtype, not object")
    return value.astype(str)


def build_labeled_dataset(
    waveform: ArrayLike,
    amplitude: ArrayLike,
    phase_end: ArrayLike,
    f0: ArrayLike,
    split: ArrayLike,
    scenario_id: ArrayLike,
    *,
    clean_waveform: ArrayLike | None = None,
    normalization_floor: float = 1.0e-7,
) -> dict[str, SplitData]:
    """Build leakage-checked splits from labeled raw 80-sample windows.

    ``scenario_id`` must identify the complete simulation run or measured
    capture from which overlapping windows came.  A scenario appearing in
    more than one split is rejected rather than silently leaking adjacent
    windows into train and test.
    """

    raw = np.asarray(waveform, dtype=np.float32)
    amp = np.asarray(amplitude, dtype=np.float32)
    phase = np.asarray(phase_end, dtype=np.float32)
    frequency = np.asarray(f0, dtype=np.float32).reshape(-1)
    split_name = _string_array(split, "split")
    scenario = _string_array(scenario_id, "scenario_id")
    n_samples = raw.shape[0] if raw.ndim else 0
    if raw.shape != (n_samples, WINDOW_SIZE):
        raise ValueError(f"waveform must have shape (N, {WINDOW_SIZE})")
    if amp.shape != (n_samples, 4) or phase.shape != (n_samples, 4):
        raise ValueError("amplitude and phase_end must both have shape (N, 4)")
    if any(value.shape != (n_samples,) for value in (frequency, split_name, scenario)):
        raise ValueError("f0, split, and scenario_id must contain N values")
    if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(amp)) or not np.all(np.isfinite(phase)):
        raise ValueError("waveform, amplitude, and phase_end must be finite")
    if np.any(amp < 0.0) or np.any(frequency <= 0.0) or not np.all(np.isfinite(frequency)):
        raise ValueError("amplitudes must be non-negative and f0 must be finite/positive")
    unknown_splits = sorted(set(split_name) - set(SPLIT_NAMES))
    if unknown_splits:
        raise ValueError(f"unknown split labels: {', '.join(unknown_splits)}")
    for required in SPLIT_NAMES:
        if not np.any(split_name == required):
            raise ValueError(f"source has no examples for required split {required!r}")

    ownership: dict[str, str] = {}
    for scenario_value, split_value in zip(scenario, split_name, strict=True):
        previous = ownership.setdefault(scenario_value, split_value)
        if previous != split_value:
            raise ValueError(
                f"scenario {scenario_value!r} occurs in both {previous!r} and {split_value!r}; "
                "split complete runs before making overlapping windows"
            )

    scale = np.maximum(np.max(np.abs(raw), axis=1), float(normalization_floor)).astype(np.float32)
    normalized = (raw / scale[:, None])[..., None]
    relative = wrap_phase(phase - phase[:, :1] * HARMONICS[None, :]).astype(np.float32)
    target = encode_targets(amp, phase, scale).astype(np.float32)
    if clean_waveform is None:
        time_from_end = (np.arange(WINDOW_SIZE, dtype=np.float64) - (WINDOW_SIZE - 1)) / FS_HZ
        angle = (
            2.0 * np.pi * frequency[:, None, None] * HARMONICS[None, :, None] * time_from_end[None, None, :]
            + phase[:, :, None]
        )
        clean = np.sum(amp[:, :, None] * np.sin(angle), axis=1).astype(np.float32)
    else:
        clean = np.asarray(clean_waveform, dtype=np.float32)
        if clean.shape != raw.shape or not np.all(np.isfinite(clean)):
            raise ValueError("clean_waveform must be finite and have shape (N, 80)")

    result: dict[str, SplitData] = {}
    for name in SPLIT_NAMES:
        selection = split_name == name
        item = SplitData(
            waveform_norm=normalized[selection].astype(np.float32),
            target=target[selection],
            scale=scale[selection],
            amplitude=amp[selection],
            phase_end=wrap_phase(phase[selection]).astype(np.float32),
            phase_relative=relative[selection],
            f0=frequency[selection],
            clean_waveform=clean[selection],
            raw_waveform=raw[selection],
            scenario_id=scenario[selection],
        )
        item.validate()
        result[name] = item
    return result


def load_labeled_npz(path: str | Path) -> dict[str, SplitData]:
    """Load the documented six-key raw-data exchange format without pickle."""

    with np.load(path, allow_pickle=False) as archive:
        required = ("waveform", "amplitude", "phase_end", "f0", "split", "scenario_id")
        missing = [name for name in required if name not in archive]
        if missing:
            raise ValueError(f"labeled source is missing: {', '.join(missing)}")
        values: dict[str, Any] = {name: np.asarray(archive[name]) for name in required}
        if "clean_waveform" in archive:
            values["clean_waveform"] = np.asarray(archive["clean_waveform"])
    return build_labeled_dataset(**values)


__all__ = ["build_labeled_dataset", "load_labeled_npz"]
