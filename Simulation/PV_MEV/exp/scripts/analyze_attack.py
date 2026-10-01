#!/usr/bin/env python3
"""Compare IL-attack impact across control modes (MPCC_D vs CRPR) on PV_MEV.
Reads exp/results/attack_<MODE>/attack_kpis.csv + per-run .mat, emits figures + a
combined comparison table."""
import os
import glob
import h5py
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = "/mnt/data6/playground/RL4EV/Simulation/PV_MEV/exp"
RES = os.path.join(BASE, "results")
FIG = os.path.join(BASE, "figures")
os.makedirs(FIG, exist_ok=True)
MODES = ["MPCC_D", "CRPR"]
C = {"MPCC_D": "#2f7d8c", "CRPR": "#e45756",
     "true": "#4c78a8", "meas": "#e45756", "vdc": "#54a24b", "pac": "#b279a2", "thd": "#f58518"}


def sig(mat, name, chan=0):
    with h5py.File(mat, "r") as f:
        g = f["res"][name]
        t = np.array(g["t"]).squeeze().astype(float)
        y = np.array(g["y"]).squeeze().astype(float)
    if y.ndim == 2:
        y = y[chan] if y.shape[0] < y.shape[1] else y[:, chan]
    return t, y


def load():
    frames = []
    for m in MODES:
        p = os.path.join(RES, f"attack_{m}", "attack_kpis.csv")
        if os.path.exists(p):
            df = pd.read_csv(p)
            df["mode"] = m
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else None


def main():
    df = load()
    if df is None:
        print("no attack results yet")
        return
    df.to_csv(os.path.join(RES, "attack_comparison.csv"), index=False)
    scen = df[df["mode"] == MODES[0]]["tag"].tolist()
    labels = [s.replace("S0", "").split("_", 1)[-1] for s in scen]

    # Fig A: grouped bars per KPI (post-attack), MPCC_D vs CRPR
    kpis = [("THD_post", "Grid-current THD (%)"), ("Vdc_peak", "DC-bus peak (V)"),
            ("Pac_post", "Power (kW)"), ("PF_post", "Power factor")]
    fig, ax = plt.subplots(2, 2, figsize=(15, 8))
    x = np.arange(len(scen)); w = 0.38
    for a, (col, ttl) in zip(ax.flat, kpis):
        for i, m in enumerate(MODES):
            d = df[df["mode"] == m].set_index("tag").reindex(scen)
            a.bar(x + (i - 0.5) * w, d[col].values, w, label=m, color=C[m], alpha=.85)
        # baseline line per mode
        for m in MODES:
            b = df[(df["mode"] == m) & (df.tag == "S00_baseline")]
            if len(b):
                a.axhline(b[col].iloc[0], color=C[m], ls="--", lw=.8)
        a.set_title(ttl, fontsize=11); a.set_xticks(x)
        a.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        a.grid(axis="y", alpha=.3); a.legend(fontsize=8)
    fig.suptitle("IL sensor-attack impact: calibrated MPCC vs conventional CRPR (post-attack steady window)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(FIG, "figA_mode_compare.png"), dpi=110)
    plt.close(fig)

    # Fig B: time-domain for representative scenarios (per mode), around onset
    reps = ["S02_bias_p60", "S04_sine_A60_f50", "S06_scale_g0p6"]
    for m in MODES:
        rows = [r for r in reps if os.path.exists(os.path.join(RES, f"attack_{m}", f"run_{r}.mat"))]
        if not rows:
            continue
        fig, ax = plt.subplots(4, len(rows), figsize=(4.5 * len(rows), 11), sharex=True)
        if len(rows) == 1:
            ax = ax.reshape(-1, 1)
        for j, tag in enumerate(rows):
            mat = os.path.join(RES, f"attack_{m}", f"run_{tag}.mat")
            with h5py.File(mat, "r") as f:
                onset = float(np.array(f["res"]["onset"]).squeeze())
            tt, itr = sig(mat, "iL_true"); _, ime = sig(mat, "iL_meas")
            ax[0, j].plot(tt, itr, color=C["true"], lw=.6, label="true iL")
            ax[0, j].plot(tt, ime, color=C["meas"], lw=.6, alpha=.8, label="measured (spoofed)")
            ax[0, j].set_title(tag.replace("S0", "").split("_", 1)[-1], fontsize=9)
            tv, vdc = sig(mat, "Vdc_inst"); ax[1, j].plot(tv, vdc, color=C["vdc"], lw=.7)
            tp, pac = sig(mat, "Pac_Pdc_kW"); ax[2, j].plot(tp, pac, color=C["pac"], lw=.9)
            th, thd = sig(mat, "THD_sys"); ax[3, j].plot(th, thd, color=C["thd"], lw=.9)
            for i in range(4):
                ax[i, j].axvline(onset, color="r", ls=":", lw=1); ax[i, j].grid(alpha=.3)
        ax[0, 0].legend(fontsize=7, loc="upper left")
        for i, yl in enumerate(["iL (A)", "Vdc (V)", "P (kW)", "THD (%)"]):
            ax[i, 0].set_ylabel(yl)
        for j in range(len(rows)):
            ax[3, j].set_xlabel("time (s)")
        fig.suptitle(f"[{m}] attack mechanism & response (red = onset)", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, 0.97])
        fig.savefig(os.path.join(FIG, f"figB_timedomain_{m}.png"), dpi=110)
        plt.close(fig)

    # console comparison
    cols = ["mode", "tag", "THD_pre", "THD_post", "Vdc_post", "Vdc_peak", "Pac_post", "PF_post"]
    print(df[cols].to_string(index=False))
    print("figures ->", FIG)


if __name__ == "__main__":
    main()
