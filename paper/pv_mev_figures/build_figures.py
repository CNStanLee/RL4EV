"""Rebuild PV_MEV documentation figures and manuscript temporal comparisons.

Only preserved observations are used. No simulation, fitting or interpolation
is performed. Phase-one 1 MHz current histories and later rounded 10 kHz
exports retain separate metrics and provenance.
"""
from pathlib import Path
import argparse
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
PHASE = HERE / "raw/phase1"
FINAL = HERE / "raw/final_sil"
OUT = HERE / "rebuilt"
DERIVED = HERE / "derived"
VARIANTS = ["CRPR", "MPCC_P", "MPCC_D", "MPCC_D_F1", "MPCC_D_F10",
            "MPCC_D_R", "MPCC_D_M1", "MPCC_D_H1"]
LABELS = ["PR", "MPCC-P", "MPCC-D", "FFT1", "FFT10", "RLS", "BLS", "H (v5)"]
COLORS = ["#737373", "#00A8D6", "#AB9AC0", "#70A442", "#8656A1",
          "#C08A10", "#20A5BC", "#1A1AD1"]
FAMILIES = [("CRPR", "PR", "#737373", "-"),
            ("MPCC_P", "MPCC-P", "#00A8D6", "--"),
            ("MPCC_D", "MPCC-D", "#AB9AC0", "-."),
            ("MPCC_H6", "MPCC-H", "#1A1AD1", ":"),
            ("MPCC_R6", "MPCC-R", "#00A050", "-")]
PDF_META = {"CreationDate": None, "ModDate": None,
            "Creator": "PV_MEV preserved-data reconstruction"}
plt.rcParams.update({"font.size": 8, "axes.titlesize": 9,
                     "legend.fontsize": 7, "lines.linewidth": 0.8,
                     "svg.fonttype": "none", "pdf.fonttype": 42,
                     "path.simplify": True})


def verify_sources():
    entries = json.loads((HERE / "source_manifest.json").read_text())
    for entry in entries:
        path = HERE / entry["local"]
        assert path.stat().st_size == entry["bytes"], path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], path
    return len(entries)


def cycle_metrics(t, current, power, samples):
    """Non-overlapping 50 Hz cycles; preserve raw ratios and mask reasons."""
    count = len(current) // samples
    x = current[:count * samples].reshape(count, samples)
    amplitude = 2 * np.abs(np.fft.rfft(x, axis=1)) / samples
    fundamental = amplitude[:, 1]
    thd = np.divide(100 * np.sqrt(np.sum(amplitude[:, 2:51] ** 2, axis=1)),
                    fundamental, out=np.full(count, np.nan), where=fundamental >= 1e-6)
    # Both exports align their 10 kHz power samples with the same 20 ms windows.
    cycle_power = np.nanmean(power[:count * 200].reshape(count, 200), axis=1)
    pre_power = float(np.nanmean(power[:1000]))
    pre_fundamental = float(np.mean(fundamental[:5]))
    low_power = cycle_power < 0.05 * pre_power
    low_fundamental = fundamental < 0.01 * pre_fundamental
    masked = low_power | low_fundamental | ~np.isfinite(thd)
    return pd.DataFrame({
        "cycle": np.arange(count), "t_center_s": t[0] + 0.01 + np.arange(count) * 0.02,
        "THD50_pct": thd, "Iac_rms_A": np.sqrt(np.mean(x * x, axis=1)),
        "I1_peak_A": fundamental, "power_mean_W": cycle_power,
        "power_retention_pct": 100 * cycle_power / pre_power,
        "low_power": low_power, "low_fundamental": low_fundamental,
        "THD_masked": masked, "THD_display_pct": np.where(masked, np.nan, thd),
    })


def read_phase(case, variant):
    path = PHASE / "ts" / f"{case}_{variant}.csv"
    frame = pd.read_csv(path)
    mat = loadmat(PHASE / "ts" / f"{case}_{variant}_iac.mat")
    t = mat["t_iac"].ravel()
    current = mat["Iac"].ravel().astype(float)
    assert len(frame) == 7000 and len(current) == 700001, path
    assert np.allclose(frame.t, 0.6 + np.arange(7000) / 10000, rtol=0, atol=1e-9)
    assert np.allclose(t, 0.6 + np.arange(700001) / 1e6, rtol=0, atol=1e-9)
    return frame, t, current, cycle_metrics(t, current, frame.P_charge.to_numpy(), 20000)


def style_time(ax, onset=0.7, removal=1.0):
    ax.axvspan(onset, removal, color="#FAE7DE", zorder=0)
    for when in [onset, removal]:
        ax.axvline(when, color="#B84B2D", linestyle=":", linewidth=0.6)
    ax.set_xlim(0.65, 1.3)
    ax.grid(axis="y", alpha=0.2)


def save(fig, name, atlas, inventory, original=None, scope="phase1"):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".pdf"), metadata=PDF_META, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), metadata={"Date": None}, bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=300 if name == "final_cycle_thd" else 160,
                bbox_inches="tight")
    if atlas is not None:
        atlas.savefig(fig, bbox_inches="tight")
    inventory.append({"original": original or f"{name}.svg",
                      "rebuilt_pdf": f"rebuilt/{name}.pdf", "scope": scope})
    plt.close(fig)


def overview(score, cases, atlas, inventory):
    # The timing diagram contains specified envelopes, not experimental samples.
    t = np.linspace(0.6, 1.3, 701)
    active = (t >= 0.7) & (t < 1.0)
    fig, ax = plt.subplots(figsize=(7.2, 2.3), layout="constrained")
    ax.plot(t, active.astype(float), label="Step")
    ax.plot(t, np.where(active, (t - 0.7) / 0.3, 0), label="Ramp (illustration)")
    ax.plot(t, np.where(active, np.sin(2 * np.pi * 50 * (t - 0.7)), 0), label="50 Hz sine")
    style_time(ax); ax.set(xlabel="Simulation time (s)", ylabel="Normalised envelope")
    ax.legend(ncol=3); ax.set_title("Snapshot 0.60 s; attack 0.70–1.00 s; recovery to 1.30 s")
    save(fig, "fig1_timing", atlas, inventory, scope="specified timing schematic")

    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4), sharex=True, layout="constrained")
    for i, v in enumerate(VARIANTS):
        frame = pd.read_csv(PHASE / "ts" / f"E-DC-01c_{v}.csv")
        axes[0].plot(frame.t, frame.Vdc_real, color=COLORS[i], label=LABELS[i])
        axes[1].plot(frame.t, frame.Iref, color=COLORS[i])
        if i == 0:
            axes[0].plot(frame.t, frame.Vdc_int, "--", color="black", label="Injected sample (PR)")
    for ax in axes: style_time(ax)
    axes[0].axhline(300, color="red", ls=":", lw=0.6)
    axes[0].set_ylabel("DC-link voltage (V)"); axes[0].legend(ncol=3)
    axes[1].set(xlabel="Time (s)", ylabel="Outer-loop reference (A)")
    axes[0].set_title("E-DC-01c: +100 V sensing bias; rectifier clamping and reference saturation")
    save(fig, "fig2_edc01c", atlas, inventory)

    for case in ["E-AC-02b", "E-AC-01a"]:
        fig, axes = plt.subplots(3, 4, figsize=(10.5, 6), layout="constrained")
        slots = [0, 1, 2, 4, 5, 6, 8, 9]
        for i, v in enumerate(VARIANTS):
            _, t, current, _ = read_phase(case, v)
            ax = axes.flat[slots[i]]
            for start, color, label in [(0.66, "#999999", "Before"), (0.96, COLORS[i], "During")]:
                mask = (t >= start) & (t < start + 0.04)
                ax.plot((t[mask] - start) * 1000, current[mask], color=color, label=label)
            ax.set(title=LABELS[i], xlabel="Cycle time (ms)", ylabel="True current (A)")
            ax.grid(alpha=0.2)
            if i == 0: ax.legend()
        q = score.loc[case].reindex(VARIANTS)
        x = np.arange(8)
        for ax, columns, title, unit in [
            (axes.flat[3], [q.I_dc_A, q.I_peak_A - 43], "DC / peak minus 43 A", "A"),
            (axes.flat[7], [q.THD50_dur_pct - q.THD50_pre_pct, q.I2_dur_pct - q.I2_pre_pct],
             "THD50 / second harmonic rise", "pp")]:
            ax.bar(x - 0.17, columns[0], width=0.34)
            ax.bar(x + 0.17, columns[1], width=0.34)
            ax.set_xticks(x, LABELS, rotation=75, fontsize=6)
            ax.set(title=title, ylabel=unit)
        for slot in [10, 11]: axes.flat[slot].set_visible(False)
        fig.suptitle(f"{case}: true 1 MHz current, two cycles before/during bias")
        save(fig, "fig3_" + case.lower().replace("-", ""), atlas, inventory)

    # A legible main-paper comparison of the two mechanisms in the full fig3s.
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.9), layout="constrained")
    for column, case in enumerate(["E-AC-01a", "E-AC-02b"]):
        for i in [0, 2, 3, 7]:
            _, t, current, _ = read_phase(case, VARIANTS[i])
            mask = (t >= 0.96) & (t < 1.0)
            axes[0, column].plot((t[mask] - 0.96) * 1000, current[mask],
                                 color=COLORS[i], label=LABELS[i])
        axes[0, column].set(title=f"{case}: late-attack current", xlabel="Cycle time (ms)", ylabel="True current (A)")
        q = score.loc[case].reindex(VARIANTS)
        axes[1, column].barh(np.arange(8), q.I_dc_A, color=COLORS)
        axes[1, column].set_yticks(np.arange(8), LABELS)
        axes[1, column].set_xlabel("Mean true-current DC component (A)")
        axes[1, column].invert_yaxis()
    axes[0, 0].legend(ncol=2)
    save(fig, "ac_chain_diagnostics", atlas, inventory, scope="phase1; manuscript selection from both original fig3s")

    matrix = score.t_rec_ms.unstack("VARIANT_NAME").reindex(index=cases, columns=VARIANTS)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.25, top=0.78)
    x = np.arange(len(cases)); width = 0.10
    for i, v in enumerate(VARIANTS):
        bars = ax.bar(x + (i - 3.5) * width, matrix[v], width, color=COLORS[i], label=LABELS[i])
        for k, case in enumerate(cases):
            if score.loc[(case, v), "trip"] > 0: bars[k].set_hatch("///")
    ax.set_xticks(x, cases, rotation=45, ha="right")
    ax.set_ylabel("Recovery after bias removal (ms)")
    fig.legend(*ax.get_legend_handles_labels(), ncol=8, loc="upper center", fontsize=6.5)
    ax.set_title("Recovery after removal; hatched bars indicate a latched violation", fontsize=8)
    save(fig, "fig4_recovery", atlas, inventory)

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), layout="constrained")
    di = np.linspace(-5, 20, 200); current = np.maximum(0, 20 - di)
    axes[0].plot(di, current * (335 + 0.5 * current) / 1000, color="black", label="Analytic CC model")
    dv = np.linspace(0, 25, 200)
    current = np.where(345 + dv >= 350, np.maximum(0, (350 - dv - 335) / 0.5), 20)
    axes[1].plot(dv, current * (335 + 0.5 * current) / 1000, color="black")
    for i, v in enumerate(VARIANTS):
        for ax, ids in zip(axes, [["E-BAT-01b", "E-BAT-01n"], ["E-BAT-02b", "E-BAT-02c"]]):
            for case in ids:
                row = score.loc[(case, v)]
                ax.plot(row.amp, row.P_charge_dur_kW, "o", ms=4, color=COLORS[i], mfc="none")
    axes[0].set(xlabel="Battery-current sensing bias (A)", ylabel="Charging power (kW)")
    axes[1].set(xlabel="Battery-voltage sensing bias (V)", ylabel="Charging power (kW)")
    for x, label in [(5, "CV entry"), (15, "Zero-current boundary")]:
        axes[1].axvline(x, ls=":", color="#777777", lw=0.6)
        axes[1].text(x + 0.3, 5.8, label, rotation=90, va="top", fontsize=7)
    for ax in axes: ax.grid(alpha=0.2)
    axes[0].legend(); fig.suptitle("Battery-chain power loss: analytic lines and measured scorecard points")
    save(fig, "fig5_ebat_curves", atlas, inventory)

    fig, axes = plt.subplots(5, 1, figsize=(7.2, 6), sharex=True, layout="constrained")
    frame = pd.read_csv(PHASE / "ts/E-BAT-02b_CRPR.csv")
    axes[0].plot(frame.t, frame.Vbat_int, color="#C84431", label="Injected")
    axes[0].plot(frame.t, frame.Vbat_real, color="black", label="True")
    axes[0].legend(ncol=2); axes[0].set_ylabel("Battery voltage (V)")
    for ax, column, label, scale in [
        (axes[1], "Ibat_real", "Battery current (A)", 1),
        (axes[2], "state", "CC=0 / CV=1", 1),
        (axes[3], "P_charge", "Charging power (kW)", 1000)]:
        ax.plot(frame.t, frame[column] / scale, color="black"); ax.set_ylabel(label)
    for i, v in enumerate(VARIANTS):
        frame = pd.read_csv(PHASE / "ts" / f"E-BAT-02b_{v}.csv")
        axes[4].plot(frame.t, frame.Vdc_real, color=COLORS[i], label=LABELS[i])
    axes[4].set(xlabel="Time (s)", ylabel="True bus (V)"); axes[4].legend(ncol=4)
    for ax in axes: style_time(ax)
    axes[0].set_title("E-BAT-02b: +10 V bias → premature CV → 3.40 kW charging → PFC load step")
    save(fig, "fig6_ebat02b", atlas, inventory)

    values = np.empty((3, 8, len(cases)))
    for k, case in enumerate(cases):
        q = score.loc[case].reindex(VARIANTS)
        values[0, :, k] = q.THD50_dur_pct - q.THD50_pre_pct
        values[0, q.power_retention_pct.to_numpy() < 5, k] = np.nan
        values[1, :, k] = q.t_rec_ms
        values[2, :, k] = q[["Vdc_over_on_V", "Vdc_under_on_V", "Vdc_over_off_V", "Vdc_under_off_V"]].abs().max(axis=1)
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), layout="constrained")
    for ax, raw, title in zip(axes, values, ["THD50 rise (pp); unavailable below 5% power",
                                           "Recovery after removal (ms)", "Largest bus excursion (V)"]):
        available = np.any(np.isfinite(raw), axis=0)
        lo = np.zeros(len(cases)); hi = np.ones(len(cases))
        lo[available] = np.nanmin(raw[:, available], axis=0)
        hi[available] = np.nanmax(raw[:, available], axis=0)
        normalised = (raw - lo) / np.maximum(hi - lo, 1e-9)
        ax.imshow(normalised, vmin=0, vmax=1, cmap="Greys", aspect="auto")
        ax.set_xticks(np.arange(len(cases)), cases, rotation=35, ha="right", fontsize=7)
        ax.set_yticks(np.arange(8), LABELS); ax.set_title(title)
        for i in range(8):
            for k in range(len(cases)):
                if np.isfinite(raw[i, k]):
                    ax.text(k, i, f"{raw[i,k]:.2g}", ha="center", va="center", fontsize=6,
                            color="white" if normalised[i, k] > 0.55 else "black")
    save(fig, "fig7_heatmap", atlas, inventory)

    fig, ax = plt.subplots(figsize=(6.2, 3.2), layout="constrained")
    points = []
    for i, v in enumerate(VARIANTS):
        baseline = pd.read_csv(PHASE / f"baseline_{v}.csv").iloc[0]
        rows = [("baseline", baseline.P_charge_kW, baseline.THD50_pct)]
        for case in ["E-BAT-01n", "E-BAT-01b", "E-BAT-02b"]:
            q = score.loc[(case, v)]; rows.append((case, q.P_charge_dur_kW, q.THD50_dur_pct))
        rows.sort(key=lambda r: r[1])
        ax.plot([r[1] for r in rows], [r[2] for r in rows], "-o", ms=3, color=COLORS[i], label=LABELS[i])
        points.extend(dict(strategy=v, case=c, power_kW=p, THD50_pct=h) for c, p, h in rows)
    ax.set(xlabel="Charging power (kW)", ylabel="THD50 (%)", title="Current quality at attack-induced charging operating points")
    ax.legend(ncol=2); ax.grid(alpha=0.2)
    pd.DataFrame(points).to_csv(DERIVED / "partial_load_points.csv", index=False)
    save(fig, "fig8_partial_load", atlas, inventory)


def waveform_case(case, score, atlas, inventory):
    records = [read_phase(case, v) for v in VARIANTS]
    cycles = pd.concat([q.assign(case=case, strategy=v) for v, (_, _, _, q) in zip(VARIANTS, records)])
    fig, axes = plt.subplots(5, 1, figsize=(9, 7.5), sharex=True, layout="constrained")
    for i, (frame, _, _, q) in enumerate(records):
        axes[0].plot(frame.t, frame.Vdc_real, color=COLORS[i], label=LABELS[i])
        axes[1].plot(frame.t, frame.Iref, color=COLORS[i])
        axes[2].plot(q.t_center_s, q.Iac_rms_A, ".-", ms=2, color=COLORS[i])
        axes[3].plot(q.t_center_s, q.THD_display_pct, ".-", ms=2, color=COLORS[i])
        axes[4].plot(frame.t, frame.P_charge / 1000, color=COLORS[i])
        row = score.loc[(case, VARIANTS[i])]
        if row.trip > 0 and np.isfinite(row.t_trip_ms):
            axes[0].axvline(0.7 + row.t_trip_ms / 1000, color=COLORS[i], lw=0.5, ls=":")
    first = records[0][0]
    axes[0].plot(first.t, first.Vdc_int, "--", color="black", label="Injected sample (PR)")
    for ax, label in zip(axes, ["Bus voltage (V)", "Reference (A)", "Cycle RMS (A)", "Cycle THD50 (%)", "Charging power (kW)"]):
        style_time(ax); ax.set_ylabel(label)
    axes[0].legend(ncol=5); axes[3].set_yscale("log"); axes[4].set_xlabel("Time (s)")
    axes[0].set_title(f"{case}: full unprotected phase-one state response (1 MHz cycle metrics)")
    save(fig, f"waveforms/{case}_state", atlas, inventory, f"waveforms/{case}_state.png")

    fig, axes = plt.subplots(3, 3, figsize=(10, 7), layout="constrained")
    for i, (_, t, current, _) in enumerate(records):
        ax = axes.flat[i]
        for start, color, label in [(0.66, "#999999", "Before"), (0.96, "#C84431", "During"), (1.26, "#246CA4", "After")]:
            mask = (t >= start) & (t < start + 0.04)
            ax.plot((t[mask] - start) * 1000, current[mask], color=color, label=label)
        ax.set(title=LABELS[i], xlabel="Cycle time (ms)", ylabel="True current (A)")
        ax.grid(alpha=0.2)
        if i == 0: ax.legend()
    axes.flat[8].set_visible(False); fig.suptitle(f"{case}: 1 MHz true current before/during/after sensing bias")
    save(fig, f"waveforms/{case}_iac", atlas, inventory, f"waveforms/{case}_iac.png")

    fig, axes = plt.subplots(4, 2, figsize=(9, 7), layout="constrained")
    for i, (frame, t, current, _) in enumerate(records):
        ax = axes.flat[i]
        bus_ax = ax.twinx()
        for start, ls, label in [(0.7, "-", "Onset"), (1.0, "--", "Removal")]:
            mask = (t >= start - 0.02) & (t < start + 0.02)
            ax.plot((t[mask] - start) * 1000, current[mask], ls=ls, color=COLORS[i], label=label)
            mask_bus = (frame.t >= start - 0.02) & (frame.t < start + 0.02)
            bus_ax.plot((frame.t[mask_bus] - start) * 1000, frame.Vdc_real[mask_bus],
                        ls=ls, color="#888888", lw=0.6, alpha=0.8)
        bus_ax.set_ylabel("True bus (V)", color="#777777")
        ax.axvline(0, ls=":", color="black", lw=0.5)
        ax.set(title=LABELS[i], xlabel="Time from event (ms)", ylabel="True current (A)")
        ax.grid(alpha=0.2)
        if i == 0: ax.legend()
    fig.suptitle(f"{case}: true current (colour) and bus (grey) at injection onset/removal")
    save(fig, f"waveforms/{case}_transition", atlas, inventory, f"waveforms/{case}_transition.png")
    return cycles


def final_comparison(atlas, inventory):
    manifest = pd.read_csv(FINAL / "manifest.csv")
    assert len(manifest) == 234
    cycles = []; transients = []
    for row in manifest.to_dict("records"):
        frame = pd.read_csv(FINAL / row["file"])
        assert len(frame) == 7000 and list(frame) == ["t", "Iac_real", "Iac_int", "Vdc_real", "Vdc_int", "P_charge"]
        assert np.allclose(frame.t, 0.6 + np.arange(7000) / 10000, rtol=0, atol=1e-10)
        assert frame.P_charge.isna().sum() == 1 and pd.isna(frame.P_charge.iloc[0])
        q = cycle_metrics(frame.t.to_numpy(), frame.Iac_real.to_numpy(), frame.P_charge.to_numpy(), 200)
        cycles.append(q.assign(case=row["case"], strategy=row["strategy"]))
        attack = frame[(frame.t >= 0.7) & (frame.t < 1)]
        late = frame[(frame.t >= 0.85) & (frame.t < 1)]
        recovery = frame[frame.t >= 1]
        transients.append({"case": row["case"], "strategy": row["strategy"],
            "late_bus_mean_V": late.Vdc_real.mean(),
            "late_power_retention_pct": 100 * late.P_charge.mean() / frame.P_charge.iloc[:1000].mean(),
            "record_bus_peak_V": frame.Vdc_real.max(),
            "attack_current_peak_A": attack.Iac_real.abs().max(),
            "recovery_current_peak_A": recovery.Iac_real.abs().max(),
            "recovery_valid_THD_peak_pct": q.loc[(q.t_center_s >= 1) & ~q.THD_masked, "THD50_pct"].max()})
    all_cycles = pd.concat(cycles, ignore_index=True)
    supplied = pd.read_csv(FINAL / "THD50_per_cycle.csv")
    check = all_cycles.merge(supplied[["case", "strategy", "cycle", "THD50_pct"]],
                            on=["case", "strategy", "cycle"], suffixes=("", "_supplied"), validate="one_to_one")
    difference = (check.THD50_pct - check.THD50_pct_supplied).abs()
    all_cycles.to_csv(DERIVED / "final_cycles.csv", index=False)
    pd.DataFrame(transients).to_csv(DERIVED / "final_transients.csv", index=False)
    selected_cases = ["E-DC-01b", "E-AC-01b", "E-BAT-02c"]
    titles = [r"DC-link bias $+50$ V", r"AC-voltage bias $+34$ V", r"Battery-voltage bias $+20$ V"]
    fig, axes = plt.subplots(2, 3, figsize=(7.3, 4.5), layout="constrained")
    thdfig, thdaxes = plt.subplots(1, 3, figsize=(7.3, 2.6), layout="constrained")
    for column, (case, title) in enumerate(zip(selected_cases, titles)):
        for variant, label, color, ls in FAMILIES:
            frame = pd.read_csv(FINAL / "waveforms" / f"{case}__{variant}.csv")
            axes[0, column].plot(frame.t, frame.Vdc_real, color=color, ls=ls, lw=0.8, label=label)
            late = frame[(frame.t >= 0.96) & (frame.t < 0.98)]
            axes[1, column].plot((late.t - 0.96) * 1000, late.Iac_real, color=color, ls=ls, lw=0.9)
            q = all_cycles[(all_cycles["case"] == case) & (all_cycles.strategy == variant)]
            thdaxes[column].plot(q.t_center_s, q.THD_display_pct, color=color, ls=ls,
                                 marker="o", ms=2, mfc="white", lw=0.8, label=label)
        axes[0, column].set(title=title, xlabel="Time (s)", ylabel="True bus (V)")
        style_time(axes[0, column])
        axes[0, column].set_xlim(0.6, 1.3)
        axes[1, column].set(xlabel="Late-cycle time (ms)", ylabel="True current (A)")
        axes[1, column].grid(alpha=0.2)
        thdaxes[column].set(title=title, xlabel="Window centre (s)", ylabel="Cycle THD50 (%)")
        style_time(thdaxes[column])
        thdaxes[column].set_xlim(0.6, 1.3)
        if case == "E-BAT-02c": thdaxes[column].set_yscale("log")
    axes[0, 0].legend(ncol=2, fontsize=6); thdaxes[0].legend(ncol=2, fontsize=6)
    save(fig, "final_waveforms", atlas, inventory, scope="five-family later SIL, rounded 10 kHz exports")
    save(thdfig, "final_cycle_thd", atlas, inventory, scope="five-family later SIL, recomputed 10 kHz cycle FFT")
    selection = all_cycles[all_cycles["case"].isin(selected_cases) & all_cycles.strategy.isin([v for v, *_ in FAMILIES])]
    selection_check = check[check["case"].isin(selected_cases) & check.strategy.isin([v for v, *_ in FAMILIES]) & ~check.THD_masked]
    selected_difference = (selection_check.THD50_pct - selection_check.THD50_pct_supplied).abs().max()
    assert len(selection) == 525 and int(selection.THD_masked.sum()) == 67
    assert selected_difference < 0.0021
    return {"waveforms": len(manifest), "cycles": len(all_cycles),
            "displayed_cycles": int((~all_cycles.THD_masked).sum()),
            "max_supplied_difference_valid_pp": float(difference[~check.THD_masked].max()),
            "selected_cycles": len(selection), "selected_masked_cycles": int(selection.THD_masked.sum()),
            "selected_max_supplied_difference_valid_pp": float(selected_difference)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-waveform-atlas", action="store_true",
                        help="Rebuild overview/main figures without the 39 per-case plots")
    args = parser.parse_args()
    sources = verify_sources()
    OUT.mkdir(exist_ok=True); DERIVED.mkdir(exist_ok=True)
    tests = pd.read_csv(PHASE / "tests.csv")
    cases = tests.test_id.tolist()
    assert len(cases) == 13
    frame = pd.read_csv(PHASE / "scorecard.csv")
    frame = frame[frame.test_id.isin(cases) & frame.VARIANT_NAME.isin(VARIANTS)].copy()
    assert len(frame) == 104 and frame.status.eq("OK").all()
    score = frame.set_index(["test_id", "VARIANT_NAME"], verify_integrity=True)
    frame.to_csv(DERIVED / "phase1_scorecards.csv", index=False)
    inventory = []
    with PdfPages(OUT / "figure_atlas.pdf", metadata=PDF_META) as atlas:
        overview(score, cases, atlas, inventory)
        if not args.skip_waveform_atlas:
            cycles = []
            for case in cases:
                cycles.append(waveform_case(case, score, atlas, inventory))
                print("Rebuilt original waveform case:", case, flush=True)
            pd.concat(cycles, ignore_index=True).to_csv(DERIVED / "phase1_cycles.csv", index=False)
        final_audit = final_comparison(atlas, inventory)
    # This unused file is an anticipated -10 A sine-shift illustration, not a run.
    inventory.append({"original": "fig3_eac02c.svg", "rebuilt_pdf": "",
                      "scope": "original unused schematic retained as editable SVG; no measured data"})
    pd.DataFrame(inventory).to_csv(HERE / "figure_inventory.csv", index=False)
    coverage = []
    for original in sorted((HERE / "original_figures").rglob("*")):
        if not original.is_file(): continue
        relative = original.relative_to(HERE / "original_figures").as_posix()
        stem = str(Path(relative).with_suffix(""))
        rebuilt = OUT / (stem + ".pdf")
        schematic = relative == "fig3_eac02c.svg"
        assert rebuilt.is_file() or schematic, ("Original figure not covered", relative)
        coverage.append({"original": relative, "rebuilt_pdf": "rebuilt/" + stem + ".pdf" if rebuilt.exists() else "",
                         "kind": "unused schematic retained as SVG" if schematic else "rebuilt from preserved inputs"})
    pd.DataFrame(coverage).to_csv(HERE / "original_figure_coverage.csv", index=False)
    audit = {"source_files_verified": sources, "phase1_scorecards": len(frame),
             "phase1_current_sample_hz": 1_000_000, "phase1_waveform_runs": 104,
             "phase1_cycle_windows": 3640 if not args.skip_waveform_atlas else None,
             "rebuilt_figures": len(inventory) - 1, "final_sil": final_audit,
             "new_experiments": False, "input_interpolation": False,
             "phase1_ranking_thd_mask": "withheld below 5% charging power",
             "cycle_display_mask": "power below 5% baseline or fundamental below 1% baseline"}
    (DERIVED / "validation.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
