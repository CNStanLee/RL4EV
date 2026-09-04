"""Detector SIL report from the Simulink per-cycle records (<run>_det.csv) of the
tests.csv campaign, with an offline reference decision next to it.

    python scripts/sil_report.py --ts ../Simulation/PV_MEV/results/emi/ts --tests ../Simulation/PV_MEV/tests.csv \
        [--variants CRPR,MPCC_P,...] [--onnx artifacts/detector_bitexact.onnx] [--persist 2] [--out runs/sil_report]

Per run, for the Simulink flags (det_chan: threshold + persistence inside the
model) and for the offline path (features.py on the logged 10 kHz record ->
ONNX -> the same threshold + persistence): first cycle after t_on where the
flags cover the injected channel(s) -> latency in cycles; coverage of the
injected cycles; wrong-channel cycles; false-alarm cycles before t_on and after
t_off + 3 cycles; whether the flags cleared.  Also the ONNX parity between the
Simulink raw logits and onnxruntime on the Simulink features, the cycles where
the Simulink and offline flag words differ, and aggregates per case / variant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from emi_det.features import cycle_features, vref_series  # noqa: E402

CH = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]
VARS = ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_F1", "MPCC_D_F10", "MPCC_D_R", "MPCC_D_M1", "MPCC_D_H1"]


def decide(logits, thr, persist):
    raw = 1 / (1 + np.exp(-logits)) >= thr[None, :]
    cnt = np.zeros(raw.shape[1], int); out = np.zeros_like(raw)
    for i in range(raw.shape[0]):
        cnt = np.where(raw[i], cnt + 1, 0); out[i] = cnt >= persist
    return out


def flag_metrics(t, flags, idx, t_on, t_off):
    pre = (t > 0.62) & (t <= t_on); dur = (t > t_on + 0.02) & (t <= t_off); post = t > t_off + 0.06
    after = t > t_on
    hit = np.where(np.all(flags[after][:, idx], axis=1))[0] if idx else np.array([])
    lat = int(round((t[after][hit[0]] - t_on) / 0.02)) if hit.size else np.inf
    cover = float(np.all(flags[dur][:, idx], axis=1).mean()) if (idx and dur.any()) else np.nan
    wrong = float(flags[dur][:, [k for k in range(5) if k not in idx]].any(1).mean()) if dur.any() else np.nan
    return dict(latency_cycles=lat, coverage=cover, wrong_channel_frac=wrong, fa_pre=int(flags[pre].any(1).sum()), n_pre=int(pre.sum()),
                fa_post=int(flags[post].any(1).sum()), n_post=int(post.sum()), cleared=(bool(not flags[post].any()) if post.any() else None), cycles_inj=int(dur.sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ts", required=True); ap.add_argument("--tests", required=True)
    ap.add_argument("--variants", default=",".join(VARS)); ap.add_argument("--out", default="runs/sil_report")
    ap.add_argument("--onnx", default=str(ROOT / "artifacts" / "detector_bitexact.onnx")); ap.add_argument("--persist", type=int, default=2)
    args = ap.parse_args()
    T = pd.read_csv(args.tests); ts = Path(args.ts); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cfg = json.load(open(ROOT / "artifacts" / "detector.json")); thr = np.array(cfg["thr"]); n_in = len(cfg["features"])
    import onnxruntime as ort
    sess = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"]); in_name = sess.get_inputs()[0].name
    rows = []
    for _, r in T.iterrows():
        c2 = r.get("channel2", ""); chans = [c for c in (str(r["channel"]), "" if (isinstance(c2, float) and np.isnan(c2)) else str(c2)) if c and c != "nan"]
        idx = [CH.index(c) for c in chans]
        t_on = float(r["t_on"]); t_off = t_on + float(r["dwell"])
        for v in args.variants.split(","):
            p = ts / f"{r['test_id']}_{v}_det.csv"
            if not p.exists():
                continue
            d = pd.read_csv(p); t = d["t"].to_numpy(); flags = d[[f"chan_{k}" for k in range(1, 6)]].to_numpy() > 0.5
            fcols = [c for c in d.columns if c.startswith("f")][:n_in]; rcols = [c for c in d.columns if c.startswith("raw")][:5]
            F = d[fcols].to_numpy().astype(np.float32); L_sim = np.asarray(sess.run(None, {in_name: F})[0])
            par = float(np.abs(d[rcols].to_numpy() - L_sim).max()) if rcols else np.nan
            m = flag_metrics(t, flags, idx, t_on, t_off)
            row = dict(test_id=r["test_id"], variant=v, channels="+".join(chans), amp=float(r["amp"]), **m, onnx_parity=par)
            # offline reference: features.py on the logged record -> ONNX -> same decision rule, aligned on cycle end time
            log = ts / f"{r['test_id']}_{v}.csv"
            if log.exists():
                df = pd.read_csv(log); cf = cycle_features(df, vref_series(df["t"].to_numpy(), float(r.get("vref_t", 0) or 0), float(r.get("vref_dV", 0) or 0)))
                X = np.nan_to_num(cf.X[:, :n_in].astype(np.float32)); L_off = np.asarray(sess.run(None, {in_name: X})[0])
                fl_off = decide(L_off, thr, args.persist); t_off_c = cf.t
                mo = flag_metrics(t_off_c, fl_off, idx, t_on, t_off)
                row.update({f"off_{k}": val for k, val in mo.items() if k in ("latency_cycles", "coverage", "fa_pre", "fa_post", "cleared")})
                # cycles present in both records whose flag word differs
                key_sim = {round(x, 3): i for i, x in enumerate(t)}; diff = 0; common = 0
                for j, tj in enumerate(t_off_c):
                    i = key_sim.get(round(float(tj), 3))
                    if i is not None:
                        common += 1; diff += int((flags[i] != fl_off[j]).any())
                row.update(common_cycles=common, sim_vs_off_diff=diff)
            rows.append(row)
    R = pd.DataFrame(rows); R.to_csv(out / "sil_runs.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    show = ["test_id", "variant", "channels", "amp", "latency_cycles", "coverage", "wrong_channel_frac", "fa_pre", "fa_post", "cleared", "onnx_parity",
            "off_latency_cycles", "off_coverage", "off_fa_pre", "off_fa_post", "sim_vs_off_diff", "common_cycles"]
    print(R[[c for c in show if c in R.columns]].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    det = np.isfinite(R.latency_cycles) & (R.coverage >= 0.5)
    lat = R.latency_cycles[np.isfinite(R.latency_cycles)]
    print(f"\nSimulink SIL: runs {len(R)}  detected (latency finite and >=50 % coverage) {int(det.sum())}  median latency {np.median(lat) if lat.size else 'n/a'} cycles  "
          f"pre-injection false-alarm cycles {int(R.fa_pre.sum())}/{int(R.n_pre.sum())}  post-removal {int(R.fa_post.sum())}/{int(R.n_post.sum())}  "
          f"onnx parity max {np.nanmax(R.onnx_parity) if R.onnx_parity.notna().any() else 'n/a'}")
    summ = dict(runs=len(R), detected=int(det.sum()), fa_pre=int(R.fa_pre.sum()), n_pre=int(R.n_pre.sum()), fa_post=int(R.fa_post.sum()), n_post=int(R.n_post.sum()))
    if "off_latency_cycles" in R.columns:
        deto = np.isfinite(R.off_latency_cycles) & (R.off_coverage >= 0.5); lato = R.off_latency_cycles[np.isfinite(R.off_latency_cycles)]
        print(f"offline reference (features.py + {Path(args.onnx).name}): detected {int(deto.sum())}  median latency {np.median(lato) if lato.size else 'n/a'}  "
              f"fa_pre {int(R.off_fa_pre.sum())}  fa_post {int(R.off_fa_post.sum())}  cycles with a different flag word {int(R.sim_vs_off_diff.sum())}/{int(R.common_cycles.sum())}")
        summ.update(off_detected=int(deto.sum()), off_fa_pre=int(R.off_fa_pre.sum()), off_fa_post=int(R.off_fa_post.sum()), diff_cycles=int(R.sim_vs_off_diff.sum()), common_cycles=int(R.common_cycles.sum()))
    agg = dict(det=("coverage", lambda s: int((s >= 0.5).sum())), n=("coverage", "size"),
               lat=("latency_cycles", lambda s: float(np.median(s[np.isfinite(s)])) if np.isfinite(s).any() else np.inf), fa_pre=("fa_pre", "sum"), fa_post=("fa_post", "sum"))
    print("\nper case:"); print(R.groupby("test_id").agg(**agg).to_string())
    print("\nper variant:"); print(R.groupby("variant").agg(**agg).to_string())
    json.dump(summ, open(out / "summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
