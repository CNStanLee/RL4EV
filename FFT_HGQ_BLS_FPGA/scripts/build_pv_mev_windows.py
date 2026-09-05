#!/usr/bin/env python3
"""Build the estimator training set from PV_MEV run_injection time series (plan step E1).

    python scripts/build_pv_mev_windows.py --ts ../Simulation/PV_MEV/results/emi/ts \
        --ts ../Simulation/PV_MEV/results/emi/dataset/ts --out data/pv_mev_windows_v2.npz

Input: the 10 kHz csv tables written by run_injection.m (baseline_*, E-*, D*). The estimator in the
model sees the controller-side (internal) PFC current at 4 kHz through an 80-sample sliding buffer with
CycleNorm (x / max|x|), so windows are cut from ``Iac_int`` resampled to 4 kHz.

Ground truth per window (end time t_e): causal two-cycle weighted least squares on the same 4 kHz
signal over [t_e - 40 ms, t_e] with DC + harmonics 1..15 at the PLL frequency (theta_pll slope), the
last cycle weighted twice the first; amplitude / phase of orders 1, 3, 5, 7 referenced to the last
sample (contract "phase_reference": window_last_sample).  This is the same GT definition as the
package's earlier real-data set (README, "GT 是因果两周期、PLL 同步、1–15 次联合加权最小二乘估计").

Splits are by run (scenario_id = run name): test_ood = runs matching --ood-regex (default the
tests.csv cases ``^E-``), the rest hashed 70 / 15 / 15 into train / val / test_id.  If no run matches
the OOD regex, the runs of --ood-fallback-variant (default MPCC_P) become test_ood.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hgq_model.contract import FS_HZ, HARMONICS, WINDOW_SIZE  # noqa: E402
from hgq_model.data import DatasetConfig, save_dataset  # noqa: E402
from hgq_model.real_data import build_labeled_dataset  # noqa: E402

FS_CSV = 10_000.0
N_FIT = 2 * WINDOW_SIZE          # two cycles at 4 kHz
ORDERS_FIT = np.arange(0, 16)    # DC + 1..15


def resample_4k(t: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """10 kHz samples -> the 4 kHz grid (linear interpolation; the model samples the continuous signal)."""
    t4 = np.arange(np.ceil(t[0] * FS_HZ), np.floor(t[-1] * FS_HZ) + 1) / FS_HZ
    return t4, np.interp(t4, t, x)


def pll_frequency(t: np.ndarray, theta: np.ndarray) -> float:
    th = np.unwrap(theta)
    p = np.polyfit(t, th, 1)
    return float(p[0] / (2 * np.pi))


def fit_window(x: np.ndarray, f0: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Weighted LS of the last N_FIT samples; returns amp[4], phase_end[4], clean_last80."""
    n = x.size
    tt = (np.arange(n) - (n - 1)) / FS_HZ
    w = np.linspace(0.5, 1.0, n)                       # emphasize the most recent cycle
    cols = [np.ones(n)]
    for h in ORDERS_FIT[1:]:
        cols += [np.sin(2 * np.pi * h * f0 * tt), np.cos(2 * np.pi * h * f0 * tt)]
    A = np.stack(cols, axis=1)
    sw = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(A * sw[:, None], x * sw, rcond=None)
    amp = np.zeros(4); ph = np.zeros(4); clean = np.zeros(WINDOW_SIZE)
    t80 = tt[-WINDOW_SIZE:]
    for k, h in enumerate(HARMONICS):
        a, b = coef[1 + 2 * (h - 1)], coef[2 + 2 * (h - 1)]
        amp[k] = np.hypot(a, b); ph[k] = np.arctan2(b, a)
        clean += amp[k] * np.sin(2 * np.pi * h * f0 * t80 + ph[k])
    return amp, ph, clean


def windows_of_run(csv: Path, stride: int, t_min: float) -> dict | None:
    df = pd.read_csv(csv, usecols=["t", "Iac_int", "theta_pll"])
    t = df["t"].to_numpy(); x = df["Iac_int"].to_numpy(); th = df["theta_pll"].to_numpy()
    if t.size < 2:
        return None
    t4, x4 = resample_4k(t, x)
    f0 = pll_frequency(t, th)
    if not (40.0 < f0 < 60.0):
        f0 = 50.0
    raw, amp, ph, clean, tend = [], [], [], [], []
    e0 = max(N_FIT, int(np.searchsorted(t4, t_min)))
    for e in range(e0, t4.size + 1, stride):
        seg = x4[e - N_FIT:e]
        if np.max(np.abs(seg[-WINDOW_SIZE:])) < 0.5:       # no current (charger off / trip): skip
            continue
        a, p, c = fit_window(seg, f0)
        raw.append(seg[-WINDOW_SIZE:]); amp.append(a); ph.append(p); clean.append(c); tend.append(t4[e - 1])
    if not raw:
        return None
    return dict(raw=np.asarray(raw, np.float32), amp=np.asarray(amp, np.float32), ph=np.asarray(ph, np.float32),
                clean=np.asarray(clean, np.float32), f0=np.full(len(raw), f0, np.float32), t=np.asarray(tend))


def split_of(run: str, ood: bool) -> str:
    if ood:
        return "test_ood"
    h = int(hashlib.sha1(run.encode()).hexdigest()[:8], 16) % 100
    return "train" if h < 70 else ("val" if h < 85 else "test_id")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ts", action="append", required=True, help="directory with run_injection csv tables (repeatable)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=int, default=8, help="window stride in 4 kHz samples (8 = 2 ms)")
    ap.add_argument("--t-min", type=float, default=0.10, help="earliest window end (s); baselines start at 0")
    ap.add_argument("--ood-regex", default=r"^E-")
    ap.add_argument("--ood-fallback-variant", default="MPCC_P")
    ap.add_argument("--exclude-regex", default=r"(_det$|^smoke_|_CRPR)", help="CRPR never uses the estimator; its PWM-ripple current is left out")
    a = ap.parse_args()

    files = []
    for d in a.ts:
        files += sorted(Path(d).glob("*.csv"))
    files = [f for f in files if not re.search(a.exclude_regex, f.stem)]
    if not files:
        sys.exit("no time-series csv found")
    ood_re = re.compile(a.ood_regex)
    runs = [f.stem for f in files]
    ood_runs = {r for r in runs if ood_re.search(r)}
    if not ood_runs:
        ood_runs = {r for r in runs if r.endswith("_" + a.ood_fallback_variant) or r.endswith("_" + a.ood_fallback_variant + "_cv")}
        print(f"no run matches {a.ood_regex!r}; test_ood = {len(ood_runs)} runs of {a.ood_fallback_variant}")
    # make sure every split is non-empty: force at least one run into val and test_id
    ordinary = [r for r in runs if r not in ood_runs]
    forced = {}
    if ordinary:
        forced[ordinary[0]] = "val"
        if len(ordinary) > 1:
            forced[ordinary[1]] = "test_id"

    W, A, P, C, F, S, SC = [], [], [], [], [], [], []
    for f in files:
        w = windows_of_run(f, a.stride, a.t_min)
        if w is None:
            print(f"[skip] {f.name}: no usable windows"); continue
        sp = forced.get(f.stem, split_of(f.stem, f.stem in ood_runs))
        n = w["raw"].shape[0]
        W.append(w["raw"]); A.append(w["amp"]); P.append(w["ph"]); C.append(w["clean"]); F.append(w["f0"])
        S += [sp] * n; SC += [f.stem] * n
        thd = np.sqrt(np.sum(w["amp"][:, 1:] ** 2, axis=1)) / np.maximum(w["amp"][:, 0], 1e-3)
        print(f"{f.stem:28s} {sp:8s} {n:5d} windows  f0={w['f0'][0]:.2f}  A1 {w['amp'][:,0].mean():6.2f} A  THD(3,5,7) {100*thd.mean():5.2f}%")
    waveform = np.concatenate(W); amplitude = np.concatenate(A); phase = np.concatenate(P); clean = np.concatenate(C)
    f0 = np.concatenate(F); split = np.asarray(S); scen = np.asarray(SC)
    ds = build_labeled_dataset(waveform, amplitude, phase, f0, split, scen, clean_waveform=clean)
    cfg = DatasetConfig(n_train=max(1, int(np.sum(split == "train"))), n_val=max(1, int(np.sum(split == "val"))),
                        n_test_id=max(1, int(np.sum(split == "test_id"))), n_test_ood=max(1, int(np.sum(split == "test_ood"))))
    out = save_dataset(a.out, ds, config=cfg)
    print("splits:", {k: len(v) for k, v in ds.items()}, "->", out)


if __name__ == "__main__":
    main()
