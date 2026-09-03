"""Assemble the per-cycle detector dataset from run_injection outputs.

    python scripts/build_dataset.py --out data/cycles_phase1.npz \
        --tests ../Simulation/PV_MEV/tests.csv --ts ../Simulation/PV_MEV/results/emi/ts \
        --baselines ../Simulation/PV_MEV/results/emi
    python scripts/build_dataset.py --out data/cycles_dataset.npz \
        --labels ../Simulation/PV_MEV/results/emi/dataset/labels.csv \
        --ts ../Simulation/PV_MEV/results/emi/dataset/ts

Each sample is one grid cycle: features X (see features.FEATURE_NAMES), class
id y, normalized amplitude a, transition flag tr, plus run_id / variant / cycle
end time for run-wise splits and latency evaluation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from emi_det.features import (AMP_SCALE, CLASSES, FEATURE_NAMES_V2, baseline_relative, channel_targets,  # noqa: E402
                              class_of, cycle_features, cycle_labels, variant_onehot, vref_series)

VARIANTS = ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_F1", "MPCC_D_F10", "MPCC_D_R"]


def add_run(store: dict, run_id: str, variant: str, ts_path: Path, t_on: float, dwell: float,
            cls: str, amp_norm: float, vref_t: float = 0.0, vref_dv: float = 0.0, extra: dict | None = None,
            t_min: float | None = None, channels: list[str] | None = None) -> None:
    df = pd.read_csv(ts_path)
    if t_min is not None:
        df = df[df["t"] >= t_min].reset_index(drop=True)
    need = ["Vac_int", "Iac_int", "Vdc_int", "Iref", "theta_pll", "D", "Vbat_int", "Ibat_int", "D_dcdc", "state", "Iref_bat"]
    if any(c not in df.columns for c in need):
        print(f"[skip] {ts_path.name}: missing columns"); return
    cf = cycle_features(df, vref_series(df["t"].to_numpy(), vref_t, vref_dv))
    y, a, tr = cycle_labels(cf.t, t_on, dwell, cls, amp_norm)
    n = cf.t.size
    Xv2 = np.concatenate([baseline_relative(cf.X), variant_onehot(variant, n)], axis=1)
    store["ych"].append(channel_targets(cf.t, t_on, dwell, channels or []))
    store["X"].append(Xv2); store["y"].append(y); store["a"].append(a); store["tr"].append(tr)
    store["t"].append(cf.t); store["run_id"].extend([run_id] * n); store["variant"].extend([variant] * n)
    store["t_on"].append(np.full(n, t_on)); store["t_off"].append(np.full(n, t_on + dwell))
    for k, v in (extra or {}).items():
        store.setdefault(k, []).extend([v] * n)
    print(f"[ok] {run_id:10s} {variant:11s} {n:3d} cycles  class={cls:9s} amp={amp_norm:+.2f}")


def from_tests(store: dict, tests: Path, ts: Path, baselines: Path | None) -> None:
    T = pd.read_csv(tests)
    for _, r in T.iterrows():
        ch2 = "" if pd.isna(r.get("channel2", "")) else str(r["channel2"])
        cls = class_of(r["channel"], r["shape"], float(r["amp"]), ch2)
        amp_norm = float(r["amp"]) / AMP_SCALE[r["channel"]]
        for v in VARIANTS:
            p = ts / f"{r['test_id']}_{v}.csv"
            if p.exists():
                add_run(store, f"{r['test_id']}_{v}", v, p, float(r["t_on"]), float(r["dwell"]), cls, amp_norm,
                        extra={"source": "tests"}, channels=[c for c in (str(r["channel"]), ch2) if c])
    if baselines is not None:
        for v in VARIANTS:
            for sfx in ("", "_cv"):
                p = ts / f"baseline_{v}{sfx}.csv"
                if p.exists():
                    # baselines run 0 -> 0.6 s; keep only the settled part after the charger ramp
                    add_run(store, f"baseline{sfx}_{v}", v, p, 9.0, 0.0, "none", 0.0, extra={"source": "baseline"}, t_min=0.44)


def from_labels(store: dict, labels: Path, ts: Path) -> None:
    L = pd.read_csv(labels)
    for _, r in L.iterrows():
        if str(r.get("status", "OK")) != "OK":
            continue
        ch1 = "" if pd.isna(r["channel1"]) else str(r["channel1"]); ch2 = "" if pd.isna(r["channel2"]) else str(r["channel2"])
        sh1 = "" if pd.isna(r["shape1"]) else str(r["shape1"])
        cls = class_of(ch1, sh1, float(r["amp1"]), ch2, int(r["n_inj"]))
        amp_norm = float(r["amp1"]) / AMP_SCALE[ch1] if ch1 else 0.0
        p = ts / f"{r['run_id']}_{r['VARIANT_NAME']}.csv"
        if not p.exists():
            print(f"[missing] {p.name}"); continue
        add_run(store, r["run_id"], r["VARIANT_NAME"], p, float(r["t_on"]), float(r["dwell"]), cls, amp_norm,
                float(r.get("vref_t", 0) or 0), float(r.get("vref_dV", 0) or 0),
                extra={"source": "dataset", "op": str(r.get("op", "cc")), "noise_ch": str(r.get("noise_ch", "")),
                       "chg_t": float(r.get("chg_t", 0) or 0)}, channels=[c for c in (ch1, ch2) if c])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tests"); ap.add_argument("--labels")
    ap.add_argument("--ts", required=True); ap.add_argument("--baselines")
    args = ap.parse_args()
    store = {k: [] for k in ("X", "y", "a", "tr", "t", "run_id", "variant", "t_on", "t_off", "ych")}
    if args.tests:
        from_tests(store, Path(args.tests), Path(args.ts), Path(args.baselines) if args.baselines else None)
    if args.labels:
        from_labels(store, Path(args.labels), Path(args.ts))
    out = {
        "X": np.concatenate(store["X"]), "y": np.concatenate(store["y"]), "a": np.concatenate(store["a"]),
        "tr": np.concatenate(store["tr"]), "t": np.concatenate(store["t"]),
        "t_on": np.concatenate(store["t_on"]), "t_off": np.concatenate(store["t_off"]),
        "run_id": np.array(store["run_id"]), "variant": np.array(store["variant"]), "ych": np.concatenate(store["ych"]),
        "feature_names": np.array(FEATURE_NAMES_V2), "classes": np.array(CLASSES),
    }
    for k in store:
        if k not in out and store[k]:
            out[k] = np.array(store[k])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **out)
    y = out["y"]
    print(f"\nsaved {args.out}: {out['X'].shape[0]} cycles x {out['X'].shape[1]} features, "
          f"{len(set(out['run_id']))} runs")
    for i, c in enumerate(CLASSES):
        m = y == i
        print(f"  {c:9s} {m.sum():6d} cycles ({(m & (out['tr'] == 0)).sum()} steady)")


if __name__ == "__main__":
    main()
