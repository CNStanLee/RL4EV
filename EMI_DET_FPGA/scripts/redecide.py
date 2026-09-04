"""Re-run the detector decision offline on the Simulink per-cycle features of a
campaign (<run>_det.csv) with another ONNX (default: the bit-exact export) and
compare with the flags the Simulink SIL block produced.

    python scripts/redecide.py --ts ../Simulation/PV_MEV/results/emi/ts [--onnx artifacts/detector_bitexact.onnx] [--persist 2]

Decision = sigmoid(logit) >= thr, then `persist` consecutive cycles (as emi_decide
in build_detector.m).  Reports cycles / runs whose channel-flag word differs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]


def decide(logits, thr, persist):
    p = 1 / (1 + np.exp(-logits)); raw = p >= thr[None, :]
    cnt = np.zeros(raw.shape[1], int); out = np.zeros_like(raw)
    for i in range(raw.shape[0]):
        cnt = np.where(raw[i], cnt + 1, 0); out[i] = cnt >= persist
    return raw, out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ts", required=True); ap.add_argument("--onnx", default=str(ROOT / "artifacts/detector_bitexact.onnx"))
    ap.add_argument("--persist", type=int, default=2); ap.add_argument("--out", default=None); a = ap.parse_args()
    cfg = json.load(open(ROOT / "artifacts/detector.json")); thr = np.array(cfg["thr"])
    s = ort.InferenceSession(a.onnx, providers=["CPUExecutionProvider"]); name = s.get_inputs()[0].name
    rows = []
    for p in sorted(Path(a.ts).glob("E-*_det.csv")):
        d = pd.read_csv(p); F = d[[c for c in d.columns if c.startswith("f")][:43]].to_numpy(np.float32)
        sim_raw = d[[f"raw{k}" if f"raw{k}" in d.columns else f"raw{k:02d}" for k in range(1, 6)]].to_numpy() if any(c.startswith("raw") for c in d.columns) else None
        sim = d[[f"chan_{k}" for k in range(1, 6)]].to_numpy() > 0.5
        L = np.asarray(s.run(None, {name: F})[0]); raw, dec = decide(L, thr, a.persist)
        # the Simulink decision uses the ORIGINAL onnx: reproduce it from the logged raw logits to validate the decision emulation
        emu_ok = np.nan
        if sim_raw is not None:
            _, dec0 = decide(sim_raw[:, :5], thr, a.persist); emu_ok = float((dec0 == sim).mean())
        rows.append(dict(run=p.stem.replace("_det", ""), cycles=len(d), flag_cycles_sim=int(sim.any(1).sum()), flag_cycles_new=int(dec.any(1).sum()),
                         cycles_differ=int((dec != sim).any(1).sum()), first_flag_sim=float(d.t[sim.any(1)].min()) if sim.any() else np.nan,
                         first_flag_new=float(d.t[dec.any(1)].min()) if dec.any() else np.nan, emu_matches_sim=emu_ok, max_dlogit=float(np.abs(L - sim_raw[:, :5]).max()) if sim_raw is not None else np.nan))
    R = pd.DataFrame(rows); pd.set_option("display.width", 200); print(R.to_string(index=False))
    print(f"\nruns {len(R)}  runs with any differing cycle {int((R.cycles_differ > 0).sum())}  differing cycles {int(R.cycles_differ.sum())}/{int(R.cycles.sum())}  "
          f"first-flag time changed in {int((R.first_flag_sim.fillna(-1) != R.first_flag_new.fillna(-1)).sum())} runs")
    if a.out:
        R.to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
