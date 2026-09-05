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
from emi_det.features import (AMP_SCALE, CHANNELS, CLASSES, FEATURE_NAMES_V2, FEATURE_NAMES_V3, baseline_relative,  # noqa: E402
                              channel_targets, class_of, cycle_features, cycle_features_v3, cycle_labels, variant_onehot, vref_series)

V3 = False   # --v3: 48 base features (features.FEATURE_NAMES_V3) instead of the 92-column v2 layout

VARIANTS = ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_F1", "MPCC_D_F10", "MPCC_D_R", "MPCC_D_M1", "MPCC_D_H1"]


def add_run(store: dict, run_id: str, variant: str, ts_path: Path, t_on: float, dwell: float,
            cls: str, amp_norm: float, vref_t: float = 0.0, vref_dv: float = 0.0, extra: dict | None = None,
            t_min: float | None = None, channels: list[str] | None = None) -> None:
    df = pd.read_csv(ts_path)
    if t_min is not None:
        df = df[df["t"] >= t_min].reset_index(drop=True)
    need = ["Vac_int", "Iac_int", "Vdc_int", "Iref", "theta_pll", "D", "Vbat_int", "Ibat_int", "D_dcdc", "state", "Iref_bat"]
    if any(c not in df.columns for c in need):
        print(f"[skip] {ts_path.name}: missing columns"); return
    vr = vref_series(df["t"].to_numpy(), vref_t, vref_dv)
    cf = cycle_features_v3(df, vr) if V3 else cycle_features(df, vr)
    y, a, tr = cycle_labels(cf.t, t_on, dwell, cls, amp_norm)
    n = cf.t.size
    Xv2 = cf.X if V3 else np.concatenate([baseline_relative(cf.X), variant_onehot(variant, n)], axis=1)
    ych = channel_targets(cf.t, t_on, dwell, channels or [])
    store["ych"].append(ych)
    # signed normalized amplitude per channel (0 where the channel is not injected); amps aligned with channels
    amp_ch = np.zeros((n, len(CHANNELS)))
    for c, av in zip(channels or [], (extra or {}).get("_amps", [amp_norm])):
        if c in CHANNELS:
            amp_ch[:, CHANNELS.index(c)] = np.where(ych[:, CHANNELS.index(c)] == 1, av, 0.0)
    store["amp_ch"].append(amp_ch)
    extra = {k: v for k, v in (extra or {}).items() if not k.startswith("_")}
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
                chans = [c for c in (str(r["channel"]), ch2) if c]
                amps = [amp_norm] + ([float(r["amp2"]) / AMP_SCALE[ch2]] if ch2 else [])
                add_run(store, f"{r['test_id']}_{v}", v, p, float(r["t_on"]), float(r["dwell"]), cls, amp_norm,
                        extra={"source": "tests", "_amps": amps}, channels=chans)
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
                       "chg_t": float(r.get("chg_t", 0) or 0),
                       "_amps": [amp_norm] + ([float(r["amp2"]) / AMP_SCALE[ch2]] if ch2 else [])},
                channels=[c for c in (ch1, ch2) if c])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tests"); ap.add_argument("--labels")
    ap.add_argument("--ts", required=True); ap.add_argument("--baselines")
    ap.add_argument("--v3", action="store_true", help="48 base features (detector v5) instead of the 92-column v2 layout")
    args = ap.parse_args()
    global V3
    V3 = bool(args.v3)
    store = {k: [] for k in ("X", "y", "a", "tr", "t", "run_id", "variant", "t_on", "t_off", "ych", "amp_ch")}
    if args.tests:
        from_tests(store, Path(args.tests), Path(args.ts), Path(args.baselines) if args.baselines else None)
    if args.labels:
        from_labels(store, Path(args.labels), Path(args.ts))
    out = {
        "X": np.concatenate(store["X"]), "y": np.concatenate(store["y"]), "a": np.concatenate(store["a"]),
        "tr": np.concatenate(store["tr"]), "t": np.concatenate(store["t"]),
        "t_on": np.concatenate(store["t_on"]), "t_off": np.concatenate(store["t_off"]),
        "run_id": np.array(store["run_id"]), "variant": np.array(store["variant"]), "ych": np.concatenate(store["ych"]),
        "amp_ch": np.concatenate(store["amp_ch"]),
        "feature_names": np.array(FEATURE_NAMES_V3 if V3 else FEATURE_NAMES_V2), "classes": np.array(CLASSES),
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
