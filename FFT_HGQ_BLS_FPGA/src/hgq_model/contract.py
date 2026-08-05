"""Signal and target contract shared by training and deployment.

The waveform convention is

``x_h(t) = A_h sin(2 pi h f0 (t - t_end) + psi_h)``.

Consequently, ``psi_h`` is the phase at the final sample in the 80-sample
window.  The network does not regress wrapped angles directly.  It predicts
the real/imaginary components of four normalized phasors in the order
``[c1, s1, c3, s3, c5, s5, c7, s7]``.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike, NDArray

FS_HZ: float = 4_000.0
WINDOW_SIZE: int = 80
HARMONICS: NDArray[np.int64] = np.asarray((1, 3, 5, 7), dtype=np.int64)
ORDER_SCALES: NDArray[np.float64] = np.asarray((1.0, 0.25, 0.20, 0.15), dtype=np.float64)


class DecodedTargets(NamedTuple):
    """Physical values reconstructed from the eight network outputs."""

    amplitude: NDArray[np.floating]
    phase_end: NDArray[np.floating]
    phase_relative: NDArray[np.floating]


def wrap_phase(phase: ArrayLike) -> NDArray[np.floating]:
    """Wrap angles to the half-open interval ``[-pi, pi)``.

    The function is deliberately NumPy-only so the exact same definition can
    be used in dataset checks, evaluation, and exported-model validation.
    """

    value = np.asarray(phase)
    if not np.issubdtype(value.dtype, np.floating):
        value = value.astype(np.float64)
    return (value + np.pi) % (2.0 * np.pi) - np.pi


def _last_axis_is_harmonics(value: NDArray[np.generic], name: str) -> None:
    if value.ndim == 0 or value.shape[-1] != HARMONICS.size:
        raise ValueError(f"{name} must have a final dimension of {HARMONICS.size}; received shape {value.shape}")


def _broadcast_window_peak(
    window_peak: ArrayLike,
    leading_shape: tuple[int, ...],
    dtype: np.dtype,
) -> NDArray[np.floating]:
    """Broadcast a scalar/``(...)``/``(..., 1)`` scale to ``(..., 1)``."""

    peak = np.asarray(window_peak, dtype=dtype)
    try:
        peak = np.broadcast_to(peak, leading_shape)
    except ValueError:
        # A stored scale is commonly ``(batch, 1)`` while targets are
        # ``(batch, 8)``.  Remove that component axis only when direct
        # broadcasting did not already handle it (e.g. ``(batch, 1)`` can
        # legitimately broadcast across a second batch dimension).
        if peak.ndim > 0 and peak.shape[-1] == 1:
            peak = np.squeeze(peak, axis=-1)
        if not leading_shape and peak.size == 1:
            peak = peak.reshape(())
        try:
            peak = np.broadcast_to(peak, leading_shape)
        except ValueError as exc:
            raise ValueError(
                "window_peak must be scalar or broadcastable to the target "
                f"leading shape {leading_shape}; received shape {peak.shape}"
            ) from exc
    if not np.all(np.isfinite(peak)) or np.any(peak <= 0.0):
        raise ValueError("window_peak must contain finite, strictly positive values")
    return peak[..., np.newaxis]


def encode_targets(
    amplitude: ArrayLike,
    phase_end: ArrayLike,
    window_peak: ArrayLike,
) -> NDArray[np.floating]:
    """Encode physical amplitudes/phases as eight normalized phasor values.

    For each ``h`` in ``[1, 3, 5, 7]`` this implements

    ``z_h = A_h / (window_peak * order_scale_h) * exp(1j * phi_h)``.

    Parameters may be a single sample with shape ``(4,)`` or batches with
    arbitrary leading dimensions and final shape ``(..., 4)``.
    """

    amp_input = np.asarray(amplitude)
    phase_input = np.asarray(phase_end)
    _last_axis_is_harmonics(amp_input, "amplitude")
    _last_axis_is_harmonics(phase_input, "phase_end")
    if amp_input.shape != phase_input.shape:
        raise ValueError(
            f"amplitude and phase_end must have identical shapes; received {amp_input.shape} and {phase_input.shape}"
        )
    dtype = np.result_type(amp_input.dtype, phase_input.dtype, np.float32)
    amplitude_array = amp_input.astype(dtype, copy=False)
    phase_array = phase_input.astype(dtype, copy=False)
    if not np.all(np.isfinite(amplitude_array)) or np.any(amplitude_array < 0.0):
        raise ValueError("amplitude must contain finite, non-negative values")
    if not np.all(np.isfinite(phase_array)):
        raise ValueError("phase_end must contain finite values")

    peak = _broadcast_window_peak(window_peak, amplitude_array.shape[:-1], dtype)
    scales = ORDER_SCALES.astype(dtype, copy=False)
    normalized_amplitude = amplitude_array / (peak * scales)
    components = np.stack(
        (
            normalized_amplitude * np.cos(phase_array),
            normalized_amplitude * np.sin(phase_array),
        ),
        axis=-1,
    )
    return components.reshape(amplitude_array.shape[:-1] + (2 * HARMONICS.size,))


def decode_targets(
    target: ArrayLike,
    window_peak: ArrayLike,
) -> DecodedTargets:
    """Decode eight phasor components to amplitude and phase.

    ``phase_relative[..., i]`` is ``wrap(psi_h - h * psi_1)``.  This is
    invariant to a common time-reference shift; its fundamental entry is
    therefore always zero (up to floating-point precision).
    """

    target_input = np.asarray(target)
    if target_input.ndim == 0 or target_input.shape[-1] != 2 * HARMONICS.size:
        raise ValueError(
            f"target must have a final dimension of {2 * HARMONICS.size}; received shape {target_input.shape}"
        )
    dtype = np.result_type(target_input.dtype, np.float32)
    target_array = target_input.astype(dtype, copy=False)
    if not np.all(np.isfinite(target_array)):
        raise ValueError("target must contain finite values")
    peak = _broadcast_window_peak(window_peak, target_array.shape[:-1], dtype)

    phasors = target_array.reshape(target_array.shape[:-1] + (HARMONICS.size, 2))
    normalized_amplitude = np.hypot(phasors[..., 0], phasors[..., 1])
    phase_end = np.arctan2(phasors[..., 1], phasors[..., 0])
    amplitude = normalized_amplitude * peak * ORDER_SCALES.astype(dtype, copy=False)
    phase_relative = wrap_phase(phase_end - phase_end[..., :1] * HARMONICS.astype(dtype, copy=False))
    return DecodedTargets(amplitude, phase_end, phase_relative)


__all__ = [
    "DecodedTargets",
    "FS_HZ",
    "HARMONICS",
    "ORDER_SCALES",
    "WINDOW_SIZE",
    "decode_targets",
    "encode_targets",
    "wrap_phase",
]
