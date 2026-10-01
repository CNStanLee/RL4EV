"""HIL report (Simulation/PV_MEV/docs/HIL_TEST_PLAN.md section 5): equivalence of the HIL runs against the SIL runs of the
same model, PL / PS / TCP latency figures from the board records.

    python hil_report.py equivalence --sil Simulation/PV_MEV/results/emi --hil Simulation/PV_MEV/results/emi/hil \
                                    --runs E-DC-01b_MPCC_R ... [--pslog PS_notebook/logs] --out EMI_DET_FPGA/runs/hil_report
    python hil_report.py latency --replay EMI_DET_FPGA/runs/hil_report/h6_run1 [--pslog ...] --out EMI_DET_FPGA/runs/hil_report

equivalence.csv : one row per run: max |dD| (10 kHz record, from the injection onset), ticks with |dD| > 1e-5,
                  max |dlogit| per cycle (raw01..05), flag-word mismatches (chan_1..5 vs board flags), detection cycle
                  SIL / HIL, scorecard deltas (power retention, bus deviation, THD50 rise), sim wall time
fig15_hil_vs_sil.png : first run: D, flags and bus voltage of SIL and HIL overlaid
latency.csv / fig16_latency_hist.png / fig17_latency_breakdown.png : from ddr_replay_mpcc_r.py, rt_loop_mpcc_r.c and the
                  ps_server_mpcc_r.py per-frame logs (TCP frame gaps = end-to-end pace as seen by the PS)
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SC_COLS = ["power_retention_pct", "dVdc_V", "THD50_pre_pct", "THD50_dur_pct", "trip", "sim_wall_s"]


def load_ts(d, run):
    p = Path(d) / "ts" / f"{run}.csv"; q = Path(d) / "ts" / f"{run}_det.csv"
    return (pd.read_csv(p) if p.exists() else None), (pd.read_csv(q) if q.exists() else None)


def equivalence(a):
    rows = []; out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    sc_s = pd.read_csv(Path(a.sil) / "scorecard.csv") if (Path(a.sil) / "scorecard.csv").exists() else pd.DataFrame(columns=["test_id", "VARIANT_NAME"])
    sc_h = pd.read_csv(Path(a.hil) / "scorecard.csv") if (Path(a.hil) / "scorecard.csv").exists() else None
    # hil_mode per run from the summary files; PS detector logs mapped to runs in chronological order (--pslog dir)
    mode = {}
    for run in a.runs:
        f = Path(a.hil) / f"{run}.csv"
        if f.exists():
            T0 = pd.read_csv(f); mode[run] = str(T0["hil_mode"].iloc[0]) if "hil_mode" in T0 else ""
    pslog = {}
    if a.pslog:
        # map each detector-path run to the PS log whose flag-word sequence equals the run's logged board flags
        logs = []
        for f in sorted(glob.glob(str(Path(a.pslog) / "det_*.csv"))):
            try:
                P = pd.read_csv(f)
            except Exception:                  # noqa: BLE001
                continue
            if len(P) >= 30:
                logs.append((f, P))
        for run in a.runs:
            if "det" not in mode.get(run, ""):
                continue
            _, dh = load_ts(a.hil, run)
            if dh is None or "hil_flags" not in dh:
                continue
            want = dh["hil_flags"].to_numpy().astype(int); lg = [f"raw{k:02d}" for k in range(1, 6)]
            ds_, _ = load_ts(a.sil, run); best = None
            for f, P in logs:
                n = min(len(want), len(P))
                if n >= 30 and np.array_equal(P["flags"].to_numpy()[:n].astype(int), want[:n]) and f not in pslog.values():
                    # several cases share a flag sequence (same channel and timing): take the log closest in logits from cycle 2
                    score = float(np.abs(ds_[lg].to_numpy()[1:n] - P[["l1", "l2", "l3", "l4", "l5"]].to_numpy()[1:n]).max()) if ds_ is not None else 0.0
                    if best is None or score < best[0]:
                        best = (score, f)
            if best is not None:
                pslog[run] = best[1]
        print(f"pslog: {len(pslog)} runs mapped to detector logs")
    first = None
    for run in a.runs:
        case, var = run.split("_", 1)
        ws, ds = load_ts(a.sil, run); wh, dh = load_ts(a.hil, run)
        if wh is None:
            print("missing HIL record", run); continue
        r = dict(run=run, test_id=case, variant=var)
        if ws is not None:
            n = min(len(ws), len(wh)); t = ws["t"].to_numpy()[:n]
            dD = np.abs(ws["D"].to_numpy()[:n] - wh["D"].to_numpy()[:n]); dV = np.abs(ws["Vdc_real"].to_numpy()[:n] - wh["Vdc_real"].to_numpy()[:n])
            r.update(max_dD=float(dD.max()), n_dD_gt_1e5=int((dD > 1e-5).sum()), n_dD_gt_1e3=int((dD > 1e-3).sum()), max_dVdc=float(dV.max()),
                     t_first_dD_gt_1e3=float(t[np.argmax(dD > 1e-3)]) if (dD > 1e-3).any() else np.nan)
        if ds is not None and dh is not None:
            n = min(len(ds), len(dh)); lg = [f"raw{k:02d}" for k in range(1, 6)]; r["n_cycles"] = n
            # Simulink ONNX logits on the two trajectories (identical when the run is otherwise identical)
            r["max_dlogit_onnx"] = float(np.abs(ds[lg].to_numpy()[:n] - dh[lg].to_numpy()[:n]).max())
            det_on = "det" in str(mode.get(run, "")) if run in mode else ("hil_flags" in dh and (dh["hil_flags"] != 0).any())
            # board logits: 'used01..05' (switch output, runs after 2026-09-05 20:20) or the PS log of the run
            bl = None
            if all(f"used{k:02d}" in dh for k in range(1, 6)) and det_on:
                bl = dh[[f"used{k:02d}" for k in range(1, 6)]].to_numpy()[:n]
            elif run in pslog:
                P = pd.read_csv(pslog[run]); bl = P[["l1", "l2", "l3", "l4", "l5"]].to_numpy()[:n]; n = min(n, len(bl))
            if bl is not None:
                dl = np.abs(ds[lg].to_numpy()[:n] - bl[:n]); r["max_dlogit_board"] = float(dl.max())
                r["max_dlogit_board_from_cycle2"] = float(dl[1:].max()) if n > 1 else np.nan   # cycle 1 = reset cycle (differential features from a zero state)
            fs = sum((ds[f"chan_{k}"].to_numpy()[:n] > 0.5) << (k - 1) for k in range(1, 6))
            fh = sum((dh[f"chan_{k}"].to_numpy()[:n] > 0.5) << (k - 1) for k in range(1, 6))
            r["flag_mismatch_cycles"] = int((fs != fh).sum())
            if "hil_flags" in dh and det_on:
                fb = dh["hil_flags"].to_numpy()[:n].astype(int); r["board_flag_mismatch_cycles"] = int((fb != fh).sum())
            on_s = np.flatnonzero(fs > 0); on_h = np.flatnonzero(fh > 0)
            r["t_detect_sil"] = float(ds["t"].iloc[on_s[0]]) if on_s.size else np.nan; r["t_detect_hil"] = float(dh["t"].iloc[on_h[0]]) if on_h.size else np.nan
            am = [f"amp_{k}" for k in range(1, 6)]
            if all(c in ds and c in dh for c in am):
                r["max_damp"] = float(np.abs(ds[am].to_numpy()[:n] - dh[am].to_numpy()[:n]).max())
        ss = sc_s[(sc_s.test_id == case) & (sc_s.VARIANT_NAME == var)]
        sh = sc_h[(sc_h.test_id == case) & (sc_h.VARIANT_NAME == var)] if sc_h is not None else None
        if len(ss) and sh is not None and len(sh):
            for c in SC_COLS:
                if c in ss and c in sh:
                    r[f"sil_{c}"] = float(ss[c].iloc[0]); r[f"hil_{c}"] = float(sh[c].iloc[0]); r[f"d_{c}"] = float(sh[c].iloc[0] - ss[c].iloc[0])
            if "hil_mode" in sh:
                r["hil_mode"] = str(sh["hil_mode"].iloc[0])
        rows.append(r)
        if first is None and ws is not None:
            first = (run, ws, wh, ds, dh)
    T = pd.DataFrame(rows); T.to_csv(out / "equivalence.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        print(T)
    if first is not None:
        run, ws, wh, ds, dh = first
        fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
        ax[0].plot(ws.t, ws.D, lw=0.6, label="SIL"); ax[0].plot(wh.t, wh.D, lw=0.6, ls="--", label="HIL"); ax[0].set_ylabel("D"); ax[0].legend()
        ax[1].plot(ws.t, ws.Vdc_real, label="SIL"); ax[1].plot(wh.t, wh.Vdc_real, ls="--", label="HIL"); ax[1].set_ylabel("Vdc real [V]")
        if ds is not None and dh is not None:
            for k in range(1, 6):
                ax[2].step(ds.t, ds[f"chan_{k}"] + 1.2 * (k - 1), where="post", lw=0.8, label=f"SIL ch{k}" if k == 1 else None)
                ax[2].step(dh.t, dh[f"chan_{k}"] + 1.2 * (k - 1), where="post", lw=0.8, ls="--", label=f"HIL ch{k}" if k == 1 else None)
            ax[2].set_ylabel("flags Vdc/Vac/Iac/Vbat/Ibat"); ax[2].legend()
        ax[2].set_xlabel("t [s]"); fig.suptitle(f"{run}: SIL vs HIL"); fig.tight_layout(); fig.savefig(out / "fig15_hil_vs_sil.png", dpi=130)
    return T


def stats(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return dict(n=int(x.size), mean=float(x.mean()), median=float(np.median(x)), p99=float(np.percentile(x, 99)), max=float(x.max()), std=float(x.std()))


def latency(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); rp = Path(a.replay); rows = []; series = {}
    def add(name, what, x, **kw):
        s = stats(x); s.update(ip=name, quantity=what, **kw); rows.append(s); series[(name, what)] = np.asarray(x, float)
    S = json.load(open(rp / "summary.json"))
    for ip, f, pl, ps in [("mpcc_r", "latency_mpcc_r.csv", "pl_us", "ps_us"), ("mpcc_r", "latency_mpcc_r_delta.csv", "pl_us", "ps_us"),
                          ("estimator", "latency_estimator.csv", "pl_us", "ps_us")]:
        if (rp / f).exists():
            D = pd.read_csv(rp / f); tag = "python_delta" if "delta" in f else "python_full"
            add(ip, f"pl_seen_us_{tag}", D[pl]); add(ip, f"ps_call_us_{tag}", D[ps])
    if (rp / "latency_detector.csv").exists():
        D = pd.read_csv(rp / "latency_detector.csv")
        add("emi_feat", "pl_seen_us_python_full", D.pl_feat_us); add("detector", "pl_seen_us_python_full", D.pl_det_us)
        add("emi_feat", "buf_write_us_python", D.buf_write_us); add("detector", "ps_call_us_python_full", D.total_us)
    for f in sorted(glob.glob(str(rp / "paced_*.csv"))):
        D = pd.read_csv(f); add(Path(f).stem.replace("paced_", ""), "paced_service_us_python", D.service_us)
    for f in sorted(glob.glob(str(rp / "rt_c_mode*.csv"))):
        D = pd.read_csv(f); tag = Path(f).stem.replace("rt_c_", "")
        add("mpcc_r", f"service_us_C_{tag}", D.service_us); add("mpcc_r", f"pl_timer_us_C_{tag}", D.pl_us)
    for k in ("paced_mpcc_r", "paced_detector", "paced_estimator"):
        if k in S:
            rows.append(dict(ip=k.replace("paced_", ""), quantity="paced_python_late_dropped", n=S[k]["frames"], mean=S[k]["late"], median=S[k]["dropped"], p99=np.nan, max=np.nan, std=np.nan))
    if a.pslog:
        for path in ("mpcc", "det", "est"):
            fs = sorted(glob.glob(str(Path(a.pslog) / f"{path}_*.csv")))
            if not fs:
                continue
            parts = []
            for f in fs:
                try:
                    P = pd.read_csv(f)
                except Exception:              # noqa: BLE001  (empty log of an aborted run)
                    continue
                if len(P) > 30:
                    parts.append(P)
            if not parts:
                continue
            D = pd.concat(parts); D = D[D.n > 0]
            add(path, "tcp_frame_gap_us", D.gap_us); add(path, "ps_service_us_tcp", D.ps_us); add(path, "pl_seen_us_tcp", D.pl_us)
    T = pd.DataFrame(rows); T.to_csv(out / "latency.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(T[["ip", "quantity", "n", "mean", "median", "p99", "max"]])
    # fig16: histograms
    keys = [("mpcc_r", "pl_timer_us_C_mode0"), ("mpcc_r", "service_us_C_mode0"), ("mpcc_r", "service_us_C_mode1"), ("mpcc_r", "paced_service_us_python"),
            ("emi_feat", "pl_seen_us_python_full"), ("detector", "pl_seen_us_python_full"), ("estimator", "pl_seen_us_python_full"), ("estimator", "paced_service_us_python")]
    keys = [k for k in keys if k in series]
    fig, axs = plt.subplots(2, 4, figsize=(15, 6)); axs = axs.ravel()
    for ax, k in zip(axs, keys):
        x = series[k]; ax.hist(x, bins=60, range=(0, min(np.percentile(x, 99.9) * 1.1, x.max())), color="#4a7fb5"); ax.set_title(f"{k[0]}: {k[1]}", fontsize=9); ax.set_xlabel("us")
    fig.suptitle("ZCU104 PL / PS latency, DDR replay (E-DC-01b record)"); fig.tight_layout(); fig.savefig(out / "fig16_latency_hist.png", dpi=130)
    # fig17: breakdown bars per path: PL (HLS csynth), PL seen from PS, PS call (Python), PS call (C), TCP frame gap
    hls = dict(mpcc_r=2.6, emi_feat=24.2, detector=2.6, estimator=7.6)
    paths = ["mpcc_r", "emi_feat", "detector", "estimator"]; labels = ["HLS latency (csynth)", "ap_start->done seen (PS)", "PS call Python (paced loop)", "PS call C", "TCP frame gap (median)"]
    vals = np.full((len(paths), len(labels)), np.nan)
    for i, p in enumerate(paths):
        vals[i, 0] = hls[p]
        for key, j in [((p, "pl_seen_us_python_full"), 1), ((p, "ps_call_us_python_full"), 2), ((p, "paced_service_us_python"), 2), ((p, "service_us_C_mode0"), 3)]:
            if key in series:
                vals[i, j] = np.median(series[key])
        if p == "mpcc_r" and ("mpcc_r", "pl_timer_us_C_mode0") in series:
            vals[i, 1] = np.median(series[("mpcc_r", "pl_timer_us_C_mode0")])
        tcp = {"mpcc_r": "mpcc", "detector": "det", "emi_feat": "det", "estimator": "est"}[p]
        if (tcp, "tcp_frame_gap_us") in series:
            vals[i, 4] = np.median(series[(tcp, "tcp_frame_gap_us")])
    fig, ax = plt.subplots(figsize=(10, 4.5)); w = 0.16; x = np.arange(len(paths))
    for j, lab in enumerate(labels):
        ax.bar(x + (j - 2) * w, vals[:, j], w, label=lab)
    ax.set_yscale("log"); ax.set_xticks(x); ax.set_xticklabels(paths); ax.set_ylabel("us (log)"); ax.legend(fontsize=8)
    for p, b in [("mpcc_r", 50), ("emi_feat", 20000), ("detector", 20000), ("estimator", 250)]:
        ax.hlines(b, paths.index(p) - 0.45, paths.index(p) + 0.45, colors="k", linestyles=":", lw=1)
    ax.set_title("latency breakdown per IP (dotted: real-time budget per call)"); fig.tight_layout(); fig.savefig(out / "fig17_latency_breakdown.png", dpi=130)
    return T


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("equivalence"); e.add_argument("--sil", default="Simulation/PV_MEV/results/emi"); e.add_argument("--hil", default="Simulation/PV_MEV/results/emi/hil")
    e.add_argument("--runs", nargs="+", required=True); e.add_argument("--pslog", default=None); e.add_argument("--out", default="EMI_DET_FPGA/runs/hil_report")
    l = sub.add_parser("latency"); l.add_argument("--replay", default="EMI_DET_FPGA/runs/hil_report/h6_run1"); l.add_argument("--pslog", default=None); l.add_argument("--out", default="EMI_DET_FPGA/runs/hil_report")
    a = ap.parse_args()
    (equivalence if a.cmd == "equivalence" else latency)(a)


if __name__ == "__main__":
    main()
