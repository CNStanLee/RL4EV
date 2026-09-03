"""Per-cycle features for the EMI-injection detector (plan phase 2, route B).

The detector sits on the controller side, so it only sees the *internal*
quantities (after the injection): Vdc_int, Vac_int, Iac_int, Iref, theta_pll,
D, and the charger's Vbat_int, Ibat_int, D_dcdc, state, Iref_bat.  Real
quantities are never used here.

One feature vector is produced per 20 ms grid cycle from the 10 kHz time-series
csv written by run_injection.m (results/emi/ts, results/emi/dataset/ts).  The
cycle grid is aligned to t = 0.6 s (the grid voltage has zero phase at t = 0 in
the model, so 0.6 + 0.02 k are zero crossings).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FS = 10_000            # csv sample rate (Hz)
F0 = 50.0              # grid frequency
NCYC = FS // 50        # samples per cycle (200)
T0 = 0.6               # first cycle boundary

CLASSES = ["none", "Vdc+", "Vdc-", "Vac_dc", "Iac_dc", "Iac_sine", "Iac_hall", "Vbat", "Ibat", "multi"]
CLASS_ID = {c: i for i, c in enumerate(CLASSES)}
AMP_SCALE = {"Vdc": 100.0, "Vac": 40.0, "Iac": 20.0, "Vbat": 25.0, "Ibat": 8.0}

FEATURE_NAMES = [
    # grid voltage (internal)
    "vac_mean", "vac_amp", "vac_mean_over_amp",
    # grid current (internal)
    "iac_mean", "iac_rms", "iac_pos_peak", "iac_neg_peak", "iac_asym", "iac_h2", "iac_h3", "iac_h1",
    "iac_ref_corr", "iac_ref_rms_err", "iac_dc_over_h1", "iac_phase_vs_theta",
    # bus voltage (internal)
    "vdc_mean", "vdc_ripple", "vdc_err",
    # outer loop / duty
    "iref_mean", "iref_min", "iref_max", "iref_neg_frac", "d_mean", "d_ff_mismatch",
    # charger (internal)
    "vbat_mean", "ibat_mean", "ddcdc_mean", "state", "irefbat_mean", "vbat_step", "ibat_step",
    # power balance (all internal)
    "p_ac_int", "p_chg_int", "p_ratio",
    # cycle-to-cycle deltas
    "d_vdc_mean", "d_iref_mean", "d_iac_rms", "d_iac_mean", "d_vbat_mean", "d_ibat_mean", "d_p_ratio",
]


def goertzel_amp(x: np.ndarray, k: int) -> float:
    """Amplitude of harmonic k (k cycles per window) of a real window x."""
    n = x.size
    w = 2 * np.pi * k / n
    c = np.cos(w * np.arange(n)); s = np.sin(w * np.arange(n))
    return 2.0 / n * np.hypot(np.dot(x, c), np.dot(x, s))


def goertzel_phase(x: np.ndarray, k: int) -> float:
    n = x.size
    w = 2 * np.pi * k / n
    c = np.cos(w * np.arange(n)); s = np.sin(w * np.arange(n))
    return float(np.arctan2(-np.dot(x, s), np.dot(x, c)))


@dataclass
class CycleFeatures:
    t: np.ndarray            # cycle end time (s)
    X: np.ndarray            # (n_cycles, n_features)


def cycle_features(df: pd.DataFrame, vref: np.ndarray | None = None) -> CycleFeatures:
    """Compute per-cycle features from a run_injection time-series table.

    vref: optional per-sample Vdc reference (400 V + benign step); default 400 V.
    """
    t = df["t"].to_numpy()
    if vref is None:
        vref = np.full(t.shape, 400.0)
    # first sample index that sits on a cycle boundary T0 + 0.02 j (j may be negative)
    phase = int(round((t[0] - T0) * FS)) % NCYC
    k0 = (NCYC - phase) % NCYC
    n = (t.size - k0) // NCYC
    cols = {c: df[c].to_numpy() for c in df.columns}
    rows = []; tc = []
    prev = None
    for i in range(n):
        a = k0 + i * NCYC; b = a + NCYC
        sl = slice(a, b)
        vac = cols["Vac_int"][sl]; iac = cols["Iac_int"][sl]; vdc = cols["Vdc_int"][sl]
        iref = cols["Iref"][sl]; th = cols["theta_pll"][sl]; d = cols["D"][sl]
        vbat = cols["Vbat_int"][sl]; ibat = cols["Ibat_int"][sl]; ddc = cols["D_dcdc"][sl]
        st = cols["state"][sl]; irb = cols["Iref_bat"][sl]; vr = vref[sl]
        # grid voltage
        vac_amp = goertzel_amp(vac, 1); vac_mean = vac.mean()
        # grid current
        h1 = goertzel_amp(iac, 1); h2 = goertzel_amp(iac, 2); h3 = goertzel_amp(iac, 3)
        iac_mean = iac.mean(); iac_rms = np.sqrt(np.mean(iac ** 2))
        pos = iac.max(); neg = iac.min()
        ref = iref * np.abs(np.sin(th)) * np.sign(np.sin(th))       # signed reference shape
        cc = np.corrcoef(iac, ref)[0, 1] if np.std(ref) > 1e-6 and np.std(iac) > 1e-6 else 0.0
        ref_err = np.sqrt(np.mean((np.abs(iac) - np.abs(ref)) ** 2)) / max(iac_rms, 1e-3)
        ph_i = goertzel_phase(iac, 1); ph_v = goertzel_phase(vac, 1)
        dphi = np.angle(np.exp(1j * (ph_i - ph_v)))
        # bus
        vdc_mean = vdc.mean(); vdc_rip = vdc.max() - vdc.min(); vdc_err = vdc_mean - vr.mean()
        # outer loop / duty
        d_ff = 1.0 - np.abs(vac) / np.maximum(vdc, 50.0)
        # charger
        p_ac = np.mean(vac * iac); p_chg = np.mean(vbat * ibat)
        p_ratio = p_chg / max(p_ac, 50.0)
        row = np.array([
            vac_mean, vac_amp, vac_mean / max(vac_amp, 1.0),
            iac_mean, iac_rms, pos, neg, pos + neg, h2 / max(h1, 1e-3), h3 / max(h1, 1e-3), h1,
            cc, ref_err, iac_mean / max(h1, 1e-3), dphi,
            vdc_mean, vdc_rip, vdc_err,
            iref.mean(), iref.min(), iref.max(), np.mean(iref < 0), d.mean(), d.mean() - d_ff.mean(),
            vbat.mean(), ibat.mean(), ddc.mean(), st.mean(), irb.mean(), vbat.max() - vbat.min(), ibat.max() - ibat.min(),
            p_ac, p_chg, p_ratio,
        ], dtype=np.float64)
        if prev is None:
            deltas = np.zeros(7)
        else:
            deltas = np.array([row[15] - prev[15], row[18] - prev[18], row[4] - prev[4], row[3] - prev[3],
                               row[24] - prev[24], row[25] - prev[25], row[33] - prev[33]])
        rows.append(np.concatenate([row, deltas])); tc.append(t[b - 1] + 1.0 / FS)
        prev = row
    X = np.asarray(rows) if rows else np.zeros((0, len(FEATURE_NAMES)))
    assert X.shape[1] == len(FEATURE_NAMES), (X.shape, len(FEATURE_NAMES))
    return CycleFeatures(np.asarray(tc), X)


def vref_series(t: np.ndarray, vref_t: float = 0.0, vref_dv: float = 0.0) -> np.ndarray:
    v = np.full(t.shape, 400.0)
    if vref_t and vref_t > 0:
        v[t >= vref_t] += vref_dv
    return v


def class_of(channel1: str, shape1: str, amp1: float, channel2: str = "", n_inj: int | None = None) -> str:
    """Map an injection description to a detector class."""
    if n_inj is None:
        n_inj = int(bool(channel1)) + int(bool(channel2))
    if n_inj == 0:
        return "none"
    if n_inj >= 2:
        return "multi"
    ch = channel1; sh = shape1
    if ch == "Vdc":
        return "Vdc+" if amp1 > 0 else "Vdc-"
    if ch == "Vac":
        return "Vac_dc"
    if ch == "Iac":
        if sh == "sine":
            return "Iac_sine"
        if sh == "hall":
            return "Iac_hall"
        return "Iac_dc"
    if ch == "Vbat":
        return "Vbat"
    if ch == "Ibat":
        return "Ibat"
    return "none"


def cycle_labels(tc: np.ndarray, t_on: float, dwell: float, cls: str, amp_norm: float,
                 settle_cycles: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-cycle class id, normalized amplitude, and a 'transition' flag.

    A cycle is labelled with the injection class when it ends after t_on and
    starts before t_off.  Cycles that only partly overlap the injection window
    (the first one after onset, the first after removal) are flagged
    transition=1 so they can be excluded from precision/recall statistics.
    """
    t_off = t_on + dwell
    start = tc - 1.0 / F0
    inside = (tc > t_on) & (start < t_off)
    full = (start >= t_on) & (tc <= t_off)
    y = np.where(inside, CLASS_ID[cls], CLASS_ID["none"])
    if cls == "none":
        y[:] = CLASS_ID["none"]; inside[:] = False; full[:] = True
    amp = np.where(inside, amp_norm, 0.0)
    trans = (inside & ~full).astype(np.int8)
    # first cycle after removal is also a transition (recovery)
    after = (start >= t_off) & (start < t_off + 1.0 / F0)
    trans[after & (cls != "none")] = 1
    return y, amp, trans
