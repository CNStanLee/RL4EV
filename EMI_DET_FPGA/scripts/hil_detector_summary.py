"""Per-run summary of the detector decisions in complete-loop HIL runs (board flag word) and in the paired SIL runs.

    python hil_detector_summary.py --sil Simulation/PV_MEV/results/emi --hil Simulation/PV_MEV/results/emi/hil_v6 \
                                   --out Simulation/PV_MEV/results/emi/hil_v6/detector_summary.csv

One row per HIL scorecard <test>_<variant>.csv that has a per-cycle record ts/<test>_<variant>_det.csv:
  truth            attacked channels (scorecard columns channel / channel2)
  hil_latency_ms   onset to the end of the first detector cycle in which the board flags an attacked channel
  hil_flagged      union of the channels flagged by the board during the attack
  hil_all_attacked 1 if every attacked channel is flagged during the attack; hil_exact 1 if the union equals the truth
  hil_pre_flags / pre_cycles   flagged cycles before the onset
  sil_*            the same quantities from the software run of the same case (chan_1..5), when it exists
The board flag word (hil_flags) has bit k-1 for channel k in the order Vdc, Vac, Iac, Vbat, Ibat.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

NAMES = ["Vdc", "Vac", "Iac", "Vbat", "Ibat"]


def decisions(det, flags, truth, t_on, dwell):
    t = det["t"].to_numpy(); eps = 1e-9
    att = (t > t_on + eps) & (t < t_on + dwell + 0.02 - eps)       # 20 ms cycles (ending at t) that contain attacked samples
    pre = t <= t_on + eps
    hit = np.array([any((v >> k) & 1 for k in truth) for v in flags])
    idx = np.where(att & hit)[0]
    union = 0
    for v in flags[att]:
        union |= int(v)
    return dict(latency_ms=1e3 * (t[idx[0]] - t_on) if idx.size else np.nan,
                flagged="+".join(NAMES[k] for k in range(5) if (union >> k) & 1),
                all_attacked=int(all((union >> k) & 1 for k in truth)),
                exact=int(union == sum(1 << k for k in truth)),
                pre_flags=int((flags[pre] != 0).sum()), pre_cycles=int(pre.sum()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sil", required=True); ap.add_argument("--hil", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(); rows = []
    for card in sorted(Path(a.hil).glob("*_*.csv")):
        rec = Path(a.hil) / "ts" / f"{card.stem}_det.csv"
        if card.name in ("scorecard.csv", "equivalence.csv", "detector_summary.csv") or not rec.exists():
            continue
        s = pd.read_csv(card).iloc[0]
        truth = [NAMES.index(c) for c in (s.get("channel"), s.get("channel2")) if isinstance(c, str) and c in NAMES]
        if not truth:
            continue
        dh = pd.read_csv(rec); r = dict(run=card.stem, test_id=s.test_id, variant=s.VARIANT_NAME, t_on=float(s.t_on), dwell=float(s.dwell),
                                       truth="+".join(NAMES[k] for k in truth))
        h = decisions(dh, dh["hil_flags"].to_numpy().astype(int), truth, r["t_on"], r["dwell"])
        r.update({f"hil_{k}": v for k, v in h.items()})
        rs = Path(a.sil) / "ts" / f"{card.stem}_det.csv"
        if rs.exists():
            ds = pd.read_csv(rs); fs = sum((ds[f"chan_{k}"].to_numpy() > 0.5).astype(int) << (k - 1) for k in range(1, 6))
            r.update({f"sil_{k}": v for k, v in decisions(ds, fs, truth, r["t_on"], r["dwell"]).items()})
        rows.append(r)
    out = pd.DataFrame(rows); out.to_csv(a.out, index=False, float_format="%.6g")
    hits = out.hil_latency_ms.notna()
    print(f"{len(out)} runs: board hit on an attacked channel in {int(hits.sum())}, median/max latency "
          f"{out.hil_latency_ms.median():.1f}/{out.hil_latency_ms.max():.1f} ms, pre-attack flagged cycles "
          f"{int(out.hil_pre_flags.sum())}/{int(out.hil_pre_cycles.sum())}")


if __name__ == "__main__":
    main()
