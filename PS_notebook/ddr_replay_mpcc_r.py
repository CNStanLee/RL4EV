"""ZCU104 real-time test of the MPCC_R overlay without TCP (docs/HIL_TEST_PLAN.md stage H6, plus the H7 PMBus reading).

    sudo bash -lc "python3 -u ddr_replay_mpcc_r.py --data ../replay_E-DC-01b_MPCC_R.npz --out ../replay/<tag> [--seconds 20]"

The SIL record exported by EMI_DET_FPGA/scripts/make_hil_replay_data.py (control-tick frames, detector cycle buffers,
estimator windows) sits in PS DDR; the PS drives the PL from it and measures with the 100 MHz axi_timer:
  pl_us : ap_start write -> ap_done seen (PS-observed PL latency; upper bound, includes one AXI-Lite write and the polling reads)
  ps_us : whole call, AXI-Lite input writes + pl + output reads (wall clock)
Runs: (1) every IP once over its dataset (full register writes; mpcc_r also in "delta" mode = only changed registers
written, as a deployed PS loop would do), (2) paced replay for --seconds at the real rates
(mpcc_r 20 kHz, detector 50 Hz, estimator 4 kHz) counting deadline misses, (3) PMBus rail power idle vs. during (2).
Outputs: latency_<ip>[_delta].csv, paced_<ip>.csv, power.csv, summary.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "libs"))
from mpcc_r_overlay import MPCC_INPUTS, AP_CTRL, MpccROverlay  # noqa: E402

TIMER_HZ = 100e6


class Timer:
    """axi_timer_0 as a free-running 32-bit up counter at the AXI clock."""

    def __init__(self, ov):
        self.m = ov.overlay.axi_timer_0.mmio
        self.m.write(0x00, 0x0); self.m.write(0x04, 0); self.m.write(0x00, 0x20); self.m.write(0x00, 0x90)   # LOAD0 then ENT0 | ARHT0
        self.a = self.m.array

    def ticks(self) -> int:
        return int(self.a[2])          # TCR0 at 0x08

    @staticmethod
    def us(d: int) -> float:
        return 1e6 * (d & 0xFFFFFFFF) / TIMER_HZ


def run_timed(ip, tm: Timer) -> float:
    """ap_start -> ap_done on the PL timer; returns micro-seconds."""
    a = ip.mmio.array
    t0 = tm.ticks(); a[0] = 1
    while not (a[0] & 2):
        pass
    return Timer.us(tm.ticks() - t0)


def stats(x):
    x = np.asarray(x, float)
    return dict(n=int(x.size), mean=float(x.mean()), median=float(np.median(x)), p99=float(np.percentile(x, 99)), max=float(x.max()), std=float(x.std()))


class Power:
    def __init__(self):
        try:
            from pynq import get_rails
            self.rails = get_rails()
        except Exception as e:                       # noqa: BLE001
            print("PMBus rails unavailable:", e); self.rails = {}
        self.rows = []; self.stop = False

    def sample(self, tag):
        row = dict(t=time.time(), tag=tag)
        for n, r in self.rails.items():
            try:
                row[n] = float(r.power.value)
            except Exception:                        # noqa: BLE001
                pass
        self.rows.append(row); return row

    def loop(self, tag, period=0.5):
        while not self.stop:
            self.sample(tag); time.sleep(period)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bit", default=str(HERE / "hardware/mpcc_r.bit"))
    ap.add_argument("--data", default=str(HERE.parent / "replay_E-DC-01b_MPCC_R.npz"))
    ap.add_argument("--out", default=str(HERE.parent / "replay" / time.strftime("%Y%m%d_%H%M%S")))
    ap.add_argument("--seconds", type=float, default=20.0)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Z = np.load(a.data); frames, bufs, waves = Z["frames"], Z["bufs"], Z["waves"]
    ov = MpccROverlay(a.bit); tm = Timer(ov); pw = Power()
    summary = dict(data=str(a.data), n_frames=int(len(frames)), n_bufs=int(len(bufs)), n_waves=int(len(waves)))
    # AXI-Lite access cost (timer read pair, MMIO word write) for reference
    t = [tm.ticks() for _ in range(2000)]; rd = np.diff(t); summary["axi_read_us"] = stats(Timer.us(rd) if False else [Timer.us(int(d)) for d in rd])
    idle = [pw.sample("idle") for _ in range(5)]; time.sleep(0.5)

    # ---------------- 1. one pass per IP, per-frame latency
    def mpcc_pass(delta: bool):
        ip = ov.mpcc; rows = []; last = {}
        names = list(MPCC_INPUTS[:13]) + ["use_harmonic", "flags", "amp_iac", "mask", "t_ramp"]
        kinds = ["f"] * 13 + ["u", "u", "f", "u", "f"]
        offs = [ip.off(n) // 4 for n in names]; a_ = ip.mmio.array; dofs = ip.off("D") // 4
        for k, fr in enumerate(frames):
            t0 = time.perf_counter()
            vals = fr.tolist()
            for j in range(18):
                v = vals[j]
                u = int(round(v)) & 0xFFFFFFFF if kinds[j] == "u" else int(np.float32(v).view(np.uint32))
                if delta and last.get(j) == u:
                    continue
                a_[offs[j]] = u; last[j] = u
            pl = run_timed(ip, tm)
            D = float(np.uint32(a_[dofs]).view(np.float32))
            rows.append((k, pl, 1e6 * (time.perf_counter() - t0), D))
        return np.array(rows)

    R = mpcc_pass(False); np.savetxt(out / "latency_mpcc_r.csv", R, delimiter=",", header="n,pl_us,ps_us,D", comments="", fmt="%.6g")
    summary["mpcc_r_full"] = dict(pl_us=stats(R[:, 1]), ps_us=stats(R[:, 2]))
    ov.reset_pl(); tm = Timer(ov)
    R = mpcc_pass(True); np.savetxt(out / "latency_mpcc_r_delta.csv", R, delimiter=",", header="n,pl_us,ps_us,D", comments="", fmt="%.6g")
    summary["mpcc_r_delta"] = dict(pl_us=stats(R[:, 1]), ps_us=stats(R[:, 2]))
    print("mpcc_r  full :", summary["mpcc_r_full"]); print("mpcc_r  delta:", summary["mpcc_r_delta"], flush=True)

    rows = []
    for c, b in enumerate(bufs):
        t0 = time.perf_counter(); ov.feat.write_f("buf", b); ov.feat.write_u("reset", 1 if c == 0 else 0); t1 = time.perf_counter()
        pl_f = run_timed(ov.feat, tm); feat = ov.feat.read_f("feat", 48); t2 = time.perf_counter()
        ov.det.write_f("feat", feat); ov.det.write_u("reset", 1 if c == 0 else 0); pl_d = run_timed(ov.det, tm)
        logit = ov.det.read_f("logit", 5); flags = ov.det.read_u("flags"); t3 = time.perf_counter()
        rows.append((c, pl_f, pl_d, 1e6 * (t1 - t0), 1e6 * (t2 - t0), 1e6 * (t3 - t0), flags, *logit))
    R = np.array(rows); np.savetxt(out / "latency_detector.csv", R, delimiter=",", header="cycle,pl_feat_us,pl_det_us,buf_write_us,feat_call_us,total_us,flags,l1,l2,l3,l4,l5", comments="", fmt="%.6g")
    summary["detector"] = dict(pl_feat_us=stats(R[:, 1]), pl_det_us=stats(R[:, 2]), buf_write_us=stats(R[:, 3]), total_us=stats(R[:, 5]))
    print("detector:", summary["detector"], flush=True)

    rows = []
    for k, w in enumerate(waves):
        t0 = time.perf_counter(); ov.est.write_f("wave", w); pl = run_timed(ov.est, tm); enc = ov.est.read_f("enc", 8); pk = ov.est.read_f("peak", 1)[0]
        rows.append((k, pl, 1e6 * (time.perf_counter() - t0), pk, enc[0], enc[1]))
    R = np.array(rows); np.savetxt(out / "latency_estimator.csv", R, delimiter=",", header="n,pl_us,ps_us,peak,e0,e1", comments="", fmt="%.6g")
    summary["estimator"] = dict(pl_us=stats(R[:, 1]), ps_us=stats(R[:, 2]))
    print("estimator:", summary["estimator"], flush=True)

    # ---------------- 2. paced replay at the real rates, PMBus sampled meanwhile
    pw.stop = False; th = threading.Thread(target=pw.loop, args=("paced",), daemon=True); th.start()

    def paced(name, period_s, n_total, step):
        late = 0; miss = 0; svc = []; t_start = time.perf_counter()
        for k in range(n_total):
            deadline = t_start + (k + 1) * period_s
            t0 = time.perf_counter(); step(k); t1 = time.perf_counter()
            svc.append(1e6 * (t1 - t0))
            if t1 > deadline:
                late += 1
                if t1 > deadline + period_s:
                    miss += 1
            else:
                while time.perf_counter() < deadline:
                    pass
        el = time.perf_counter() - t_start
        r = dict(period_us=1e6 * period_s, frames=n_total, elapsed_s=el, late=late, dropped=miss, service_us=stats(svc))
        np.savetxt(out / f"paced_{name}.csv", np.array(svc), header="service_us", comments="", fmt="%.2f")
        print(f"paced {name}: {r}", flush=True); return r

    ip = ov.mpcc; a_ = ip.mmio.array; offs = [ip.off(n) // 4 for n in ("i_L", "i_ref", "V_in", "V_o", "theta_pll", "flags", "amp_iac")]
    dofs = ip.off("D") // 4; F32 = frames.view(np.uint32)
    for j, n in enumerate(MPCC_INPUTS[:13]):      # constants once
        a_[ip.off(n) // 4] = int(F32[0, j])
    a_[ip.off("use_harmonic") // 4] = 1; a_[ip.off("mask") // 4] = 437; a_[ip.off("t_ramp") // 4] = int(F32[0, 17])
    idx = [0, 1, 2, 5, 6]; nf = len(frames)

    def step_mpcc(k):
        fr = F32[k % nf]
        for o, j in zip(offs[:5], idx):
            a_[o] = int(fr[j])
        a_[offs[5]] = int(round(float(frames[k % nf, 14]))); a_[offs[6]] = int(fr[15])
        a_[0] = 1
        while not (a_[0] & 2):
            pass
        return a_[dofs]

    summary["paced_mpcc_r"] = paced("mpcc_r", 50e-6, int(a.seconds / 50e-6), step_mpcc)

    nb = len(bufs); fs = ov.feat.mmio.array; ds = ov.det.mmio.array; bo = ov.feat.off("buf") // 4; fo = ov.feat.off("feat") // 4; dfo = ov.det.off("feat") // 4
    B32 = bufs.view(np.uint32)

    def step_det(k):
        b = B32[k % nb].tolist()
        for i, u in enumerate(b):
            fs[bo + i] = u
        fs[0] = 1
        while not (fs[0] & 2):
            pass
        for i in range(48):
            ds[dfo + i] = fs[fo + i]
        ds[0] = 1
        while not (ds[0] & 2):
            pass
        return ds[ov.det.off("flags") // 4]

    summary["paced_detector"] = paced("detector", 20e-3, int(a.seconds / 20e-3), step_det)

    nw = len(waves); es = ov.est.mmio.array; wo = ov.est.off("wave") // 4; eo = ov.est.off("enc") // 4; W32 = waves.view(np.uint32)

    def step_est(k):
        w = W32[k % nw].tolist()
        for i, u in enumerate(w):
            es[wo + i] = u
        es[0] = 1
        while not (es[0] & 2):
            pass
        return es[eo]

    summary["paced_estimator"] = paced("estimator", 250e-6, int(a.seconds / 250e-6), step_est)
    pw.stop = True; th.join(timeout=2)
    # ---------------- 3. power
    if pw.rails:
        import csv
        keys = ["t", "tag"] + sorted(k for k in pw.rows[0] if k not in ("t", "tag"))
        with open(out / "power.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(pw.rows)
        def avg(tag):
            rs = [r for r in pw.rows if r["tag"] == tag]
            return {k: float(np.mean([r[k] for r in rs if k in r])) for k in keys[2:]}
        summary["power_W"] = dict(idle=avg("idle"), paced=avg("paced"))
        print("power idle :", summary["power_W"]["idle"]); print("power paced:", summary["power_W"]["paced"])
    json.dump(summary, open(out / "summary.json", "w"), indent=1)
    print("written", out)


if __name__ == "__main__":
    main()
