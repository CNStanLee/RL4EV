#!/usr/bin/env python3
"""Analyze one control-mode IL-attack campaign (calibrated MPCC or CRPR).
Usage: python3 analyze_mode.py [MPCC|CRPR]"""
import json
import os
import sys

import h5py
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODE = sys.argv[1] if len(sys.argv) > 1 else "MPCC"
BASE = "/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA/experiments/sensor_attack_il"
RES = os.path.join(BASE, f"results_{MODE}")
FIG = os.path.join(BASE, f"figures_{MODE}")
os.makedirs(FIG, exist_ok=True)

C = {"true": "#4c78a8", "meas": "#e45756", "vdc": "#54a24b",
     "pac": "#b279a2", "thd": "#f58518"}


def sig(mat, name, chan=0):
    with h5py.File(mat, "r") as f:
        g = f["res"][name]
        t = np.array(g["t"]).squeeze().astype(float)
        y = np.array(g["y"]).squeeze().astype(float)
    if y.ndim == 2:
        y = y[chan] if y.shape[0] < y.shape[1] else y[:, chan]
    return t, y


def onset_of(mat):
    try:
        with h5py.File(mat, "r") as f:
            return float(np.array(f["res"]["onset"]).squeeze())
    except Exception:
        return 0.12


def main():
    df = pd.read_csv(os.path.join(RES, "summary_kpis.csv")).sort_values("tag").reset_index(drop=True)
    b = df[df.enable == 0].iloc[0]
    P0, THD0, RIP0, VDC0 = b.Pac_kW, b.THD_sys, b.Vdc_ripple, b.Vdc_mean
    VMAX0, IAC0 = b.Vdc_max, b.Iac_rms
    onset = onset_of(os.path.join(RES, "run_S00_baseline.mat"))

    def classify(r):
        if r.enable == 0:
            return "baseline"
        pr = abs(r.Pac_kW) / max(abs(P0), 1e-6)
        ir = r.Iac_rms / max(IAC0, 1e-6)
        if pr < 0.30 or ir < 0.30 or (pr < 0.55 and r.Vdc_mean < 0.9 * VDC0):
            return "DoS / voltage-collapse"
        if r.Vdc_max > 1.12 * VMAX0:
            return "Over-voltage stress (Damage risk)"
        if pr < 0.90:
            return "Damping (power reduced)"
        if r.THD_sys > 1.25 * THD0 or r.Vdc_ripple > 1.3 * RIP0:
            return "Quality degradation"
        return "Marginal / recovered"

    df["Pac_ratio"] = df.Pac_kW.abs() / max(abs(P0), 1e-6)
    df["THD_delta"] = df.THD_sys - THD0
    df["THD_ratio"] = df.THD_sys / max(THD0, 1e-6)
    df["outcome"] = df.apply(classify, axis=1)
    df.to_csv(os.path.join(RES, "summary_kpis_annotated.csv"), index=False)

    labels = [l.replace("_", " ") for l in df.tag.str.replace(r"^S\d+_", "", regex=True)]
    x = np.arange(len(df))
    ib = int(np.where(df.enable.values == 0)[0][0])

    # Fig1 KPI overview
    fig, ax = plt.subplots(2, 2, figsize=(15, 8))
    specs = [("THD_sys", "Grid-current THD (%)", THD0, C["thd"]),
             ("Vdc_ripple", "DC-bus ripple (%)", RIP0, C["vdc"]),
             ("Pac_kW", "Transferred power (kW)", P0, C["pac"]),
             ("PF", "Power factor", b.PF, C["true"])]
    for a, (col, ttl, ref, cc) in zip(ax.flat, specs):
        bars = a.bar(x, df[col].values, color=cc, alpha=.85)
        a.axhline(ref, color="k", ls="--", lw=1, label=f"baseline={ref:.2f}")
        bars[ib].set_edgecolor("k"); bars[ib].set_linewidth(1.5)
        a.set_title(ttl, fontsize=11)
        a.set_xticks(x); a.set_xticklabels(labels, rotation=55, ha="right", fontsize=8)
        a.grid(axis="y", alpha=.3); a.legend(fontsize=8)
    fig.suptitle(f"[{MODE}] IL sensor-attack impact on MPCC / system KPIs "
                 f"(baseline THD={THD0:.1f}%, steady window)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(FIG, "fig1_kpi_overview.png"), dpi=110)
    plt.close(fig)

    # Fig2 bias dose-response
    bias = df[df.mode_flag == 1].copy()
    base_row = df[df.enable == 0]
    bias = pd.concat([base_row.assign(A=0.0), bias]).sort_values("A")
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    ax[0].plot(bias.A, bias.THD_sys, "o-", color=C["thd"]); ax[0].set_title("THD vs bias"); ax[0].set_ylabel("THD (%)")
    ax[1].plot(bias.A, bias.Pac_kW, "o-", color=C["pac"]); ax[1].set_title("Power vs bias"); ax[1].set_ylabel("kW")
    ax[2].plot(bias.A, bias.Vdc_ripple, "o-", color=C["vdc"])
    ax2 = ax[2].twinx(); ax2.plot(bias.A, bias.Vdc_mean, "s--", color="k")
    ax[2].set_title("DC bus vs bias"); ax[2].set_ylabel("ripple (%)"); ax2.set_ylabel("Vdc mean (V)")
    for a in ax:
        a.set_xlabel("injected IL bias (A)"); a.grid(alpha=.3)
    fig.suptitle(f"[{MODE}] Bias-attack dose-response on IL current sensor", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(os.path.join(FIG, "fig2_bias_dose.png"), dpi=110)
    plt.close(fig)

    # Fig3 time-domain
    want = ["S00_baseline", "S03_bias_p60", "S06_sine_A60_f50", "S11_scale_g0p6"]
    reps = [t for t in want if os.path.exists(os.path.join(RES, f"run_{t}.mat"))]
    fig, ax = plt.subplots(4, len(reps), figsize=(4.2 * len(reps), 11), sharex=True)
    if len(reps) == 1:
        ax = ax.reshape(-1, 1)
    for j, tag in enumerate(reps):
        mat = os.path.join(RES, f"run_{tag}.mat")
        lab = df[df.tag == tag].label.iloc[0]
        tt, itr = sig(mat, "iL_true"); _, ime = sig(mat, "iL_meas")
        ax[0, j].plot(tt, itr, color=C["true"], lw=.7, label="true iL")
        ax[0, j].plot(tt, ime, color=C["meas"], lw=.7, alpha=.8, label="measured (spoofed)")
        ax[0, j].set_title(lab, fontsize=9)
        tv, vdc = sig(mat, "Vdc"); ax[1, j].plot(tv, vdc, color=C["vdc"], lw=.8)
        tp, pac = sig(mat, "Pac_Pdc_kW"); ax[2, j].plot(tp, pac, color=C["pac"], lw=.9)
        th, thd = sig(mat, "THD_sys"); ax[3, j].plot(th, thd, color=C["thd"], lw=.9)
        for i in range(4):
            ax[i, j].axvline(onset, color="r", ls=":", lw=1); ax[i, j].grid(alpha=.3)
    ax[0, 0].legend(fontsize=7, loc="upper left")
    for i, yl in enumerate(["iL (A)", "Vdc (V)", "P (kW)", "THD (%)"]):
        ax[i, 0].set_ylabel(yl)
    for j in range(len(reps)):
        ax[3, j].set_xlabel("time (s)")
    fig.suptitle(f"[{MODE}] Attack mechanism (row 1: controller-seen vs real current) "
                 f"and system response; red = onset {onset:.2f}s", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(FIG, "fig3_timedomain.png"), dpi=110)
    plt.close(fig)

    out = {"mode": MODE,
           "baseline": {k: float(b[k]) for k in
                        ["THD_sys", "Vdc_ripple", "Vdc_mean", "Vdc_max", "Pac_kW", "PF", "Iac_rms"]},
           "onset": onset,
           "scenarios": json.loads(df.to_json(orient="records"))}
    with open(os.path.join(RES, "results.json"), "w") as f:
        json.dump(out, f, indent=2)

    cols = ["tag", "label", "THD_sys", "Vdc_ripple", "Vdc_mean", "Vdc_max",
            "Pac_kW", "PF", "delta_rms", "outcome"]
    print(f"[{MODE}] baseline THD={THD0:.2f}% P={P0:.2f}kW Vdc={VDC0:.0f}V")
    print(df[cols].to_string(index=False))
    print("figures ->", FIG)


if __name__ == "__main__":
    main()
