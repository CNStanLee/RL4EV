"""Detector SIL report from the Simulink per-cycle records (<run>_det.csv) of the
tests.csv campaign.

    python scripts/sil_report.py --ts ../Simulation/PV_MEV/results/emi/ts --tests ../Simulation/PV_MEV/tests.csv \
        [--variants CRPR,MPCC_P,...] [--out runs/sil_report]

Per run: injected channel(s), first cycle (after t_on) where the Simulink
channel flags (det_chan, after threshold + persistence) cover the injected
channel(s) -> latency in cycles; false-alarm cycles before t_on and after
t_off + 2 cycles; whether the flags cleared after removal.  Aggregates per
case and per variant, and compares the Simulink raw logits with onnxruntime on
the Simulink features (parity) for every run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
VARS = ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_F1", "MPCC_D_F10", "MPCC_D_R", "MPCC_D_M1", "MPCC_D_H1"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", required=True); ap.add_argument("--tests", required=True)
    ap.add_argument("--variants", default=",".join(VARS)); ap.add_argument("--out", default="runs/sil_report")
    ap.add_argument("--onnx", default=str(Path(__file__).resolve().parents[1] / "artifacts" / "detector.onnx"))
    args = ap.parse_args()
    T = pd.read_csv(args.tests); ts = Path(args.ts); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"]); in_name = sess.get_inputs()[0].name
    except Exception:
        sess = None
    rows = []
    for _, r in T.iterrows():
        chans = [c for c in (str(r["channel"]), "" if pd.isna(r.get("channel2", "")) else str(r["channel2"])) if c]
        idx = [CH.index(c) for c in chans]
        t_on = float(r["t_on"]); t_off = t_on + float(r["dwell"])
        for v in args.variants.split(","):
            p = ts / f"{r['test_id']}_{v}_det.csv"
            if not p.exists():
                continue
            d = pd.read_csv(p); t = d["t"].to_numpy(); flags = d[[f"chan_{k}" for k in range(1, 6)]].to_numpy() > 0.5
            pre = (t > 0.62) & (t <= t_on); dur = (t > t_on + 0.02) & (t <= t_off); post = t > t_off + 0.06
            fa_pre = int(flags[pre].any(1).sum()); fa_post = int(flags[post].any(1).sum())
            after = t > t_on
            hit = np.where(np.all(flags[after][:, idx], axis=1))[0] if idx else np.array([])
            lat = int(round((t[after][hit[0]] - t_on) / 0.02)) if hit.size else np.inf
            cover = float(np.all(flags[dur][:, idx], axis=1).mean()) if (idx and dur.any()) else np.nan
            wrong = float(flags[dur][:, [k for k in range(5) if k not in idx]].any(1).mean()) if dur.any() else np.nan
            cleared = bool(not flags[post].any()) if post.any() else None
            par = np.nan
            if sess is not None:
                fcols = [c for c in d.columns if c.startswith("f")][:43]; rcols = [c for c in d.columns if c.startswith("raw")]
                if fcols and rcols:
                    F = d[fcols].to_numpy().astype(np.float32); outs = sess.run(None, {in_name: F})
                    raw_py = np.concatenate([np.asarray(o).reshape(len(d), -1) for o in outs], axis=1)
                    par = float(np.abs(d[rcols].to_numpy() - raw_py).max())
            rows.append(dict(test_id=r["test_id"], variant=v, channels="+".join(chans), amp=float(r["amp"]), cycles_inj=int(dur.sum()),
                             latency_cycles=lat, coverage=cover, wrong_channel_frac=wrong, fa_pre=fa_pre, n_pre=int(pre.sum()),
                             fa_post=fa_post, n_post=int(post.sum()), cleared=cleared, onnx_parity=par))
    R = pd.DataFrame(rows); R.to_csv(out / "sil_runs.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
    print(R.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    det = np.isfinite(R.latency_cycles) & (R.coverage >= 0.5)
    print(f"\nruns: {len(R)}  detected (latency finite and >=50 % coverage): {int(det.sum())}  "
          f"median latency {np.median(R.latency_cycles[np.isfinite(R.latency_cycles)]) if np.isfinite(R.latency_cycles).any() else 'n/a'} cycles  "
          f"pre-injection false-alarm cycles {int(R.fa_pre.sum())}/{int(R.n_pre.sum())}  post-removal {int(R.fa_post.sum())}/{int(R.n_post.sum())}  "
          f"onnx parity max {np.nanmax(R.onnx_parity) if R.onnx_parity.notna().any() else 'n/a'}")
    print("\nper case:"); print(R.groupby("test_id").agg(det=("coverage", lambda s: int((s >= 0.5).sum())), n=("coverage", "size"),
          lat=("latency_cycles", lambda s: float(np.median(s[np.isfinite(s)])) if np.isfinite(s).any() else np.inf), fa_pre=("fa_pre", "sum")).to_string())
    print("\nper variant:"); print(R.groupby("variant").agg(det=("coverage", lambda s: int((s >= 0.5).sum())), n=("coverage", "size"),
          lat=("latency_cycles", lambda s: float(np.median(s[np.isfinite(s)])) if np.isfinite(s).any() else np.inf), fa_pre=("fa_pre", "sum"), fa_post=("fa_post", "sum")).to_string())
    json.dump(dict(runs=len(R), detected=int(det.sum()), fa_pre=int(R.fa_pre.sum()), n_pre=int(R.n_pre.sum()), fa_post=int(R.fa_post.sum()), n_post=int(R.n_post.sum())),
              open(out / "summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
