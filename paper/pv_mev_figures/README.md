# Reconstructed PV_MEV figures and raw observations

This standalone package preserves 784 original files, including all available
inputs needed by `Simulation/PV_MEV/docs/figures`. Every source path, version,
byte count and SHA-256 is in `source_manifest.json`.

## Provenance and versions

The original eight-strategy campaign was recovered from the first public RL4EV
data bundle (Drive ID `186uhv86RkQAilBb9XWfCzl1BwmxdGY6W`). The downloaded ZIP
SHA-256 is `12c07cf8881952ad763ca550f46dfb6bb0844490879e90c27077c3ff2478feb0`.
The two original campaign archives were independently verified:

| Archive | SHA-256 |
|---|---|
| `emi_campaign_ts_10kHz.tar.xz` | `95617498859c6aad62056443a8a7dc6eaa95f52d80a040014f8495131247c4ac` |
| `emi_campaign_iac_1MHz.tar` | `a66f34db787628e3b60f44d5e4a92f248e61a2e4722637e1a9d97104edcba97e` |

`raw/phase1/ts/` contains the exact extracted files: 104 state CSVs with 25
columns, 104 detector-cycle CSVs and 104 MAT current histories. State logs have
7000 samples at 10 kHz; MAT files have 700001 samples at 1 MHz, including the
1.30 s endpoint. The missing first power sample is retained and is never imputed.
The configuration and scorecards preserve the eight unprotected variants. In
particular, `MPCC_D_R` means RLS; it is distinct from resilient MPCC-R.

`raw/final_sil/` preserves the 234 six-column, rounded 10 kHz exports from
manuscript revision `1e48d62cf1b89eead880d25070b389af3a06423b`. The source ZIP
SHA-256 is `253735fc4c0c86852a4ff1cf31e47b65da66e631676913eb228a0d7fd7a67e49`.
This later set includes MPCC-H6/R6 and ablations. Its original README's claim
that FFT/RLS/BLS are detector configurations is incorrect: they are harmonic
controller variants. Their actual original 1 MHz histories are now recovered
in `raw/phase1/`. The two sets retain distinct version and sampling scopes.

## Rebuild

From the manuscript root:

```bash
python -m pip install -r data/requirements.txt
python data/pv_mev/build_figures.py
```

From a standalone copy, invoke its `build_figures.py` by path. All inputs resolve
relative to that script. The code repository carries an identical package at
`paper/pv_mev_figures/`.

`rebuilt/` contains 51 vector PDF/editable SVG/PNG figures and a 51-page atlas:
nine original overview/timing figures, 39 original waveform panels, one
legible AC-chain manuscript selection and two later SIL temporal comparisons.
`figure_inventory.csv` lists reconstructed outputs;
`original_figure_coverage.csv` maps every original SVG/PNG to its reconstruction.
The unused anticipated `fig3_eac02c.svg` remains a schematic, not a measurement.

## Numerical rules and corrections

Cycle FFT uses consecutive complete 20 ms windows, harmonic orders 2–50 and
the actual saved current samples. Earlier cycles use 20000 samples at 1 MHz;
later exported cycles use 200 samples at 10 kHz. No waveform smoothing,
interpolation or replacement of missing data is performed. Matplotlib may
simplify vector paths during rendering; original numeric samples remain intact.

Raw THD ratios are retained. Display omits cycles below 5% of pre-attack
charging power or below 1% of pre-attack fundamental amplitude. The heatmap
also withholds THD comparisons below 5% charging power. Original scorecard
THD values remain unchanged. These display rules avoid presenting halted
charging as a normal current-quality operating point; current and voltage
waveforms are always retained, including the PR high-current pulses.

The rebuilt DC-link title describes observed rectifier clamping and reference
saturation, correcting the original title's anticipated 300 V equilibrium.
Recovery uses all eight controls; the original MATLAB generator's six-row
matrix allocations have been corrected in RL4EV. Transition panels retain
current and bus on separate ordinates. Original images and generators remain
unchanged in `original_figures/` and `provenance/` for comparison.

`derived/` contains 104 selected original scorecards, 3640 high-rate cycle
records, 8190 later export cycle records, partial-load plotting points,
transient summaries and validation. In the three main final-family cases,
67/525 cycles are masked; maximum source-table discrepancy among displayed
cycles is 0.001995 pp. Across all 234 exports it is 0.058659 pp. These are
source consistency checks, not error bounds on the physical simulation.

The main manuscript embeds the verified 300 dpi cycle-THD PNG because the local
Tectonic PDF importer displaced disconnected log-axis paths in the native PDF.
The numerical reconstruction and standalone vector PDF/SVG remain available.
The image preserves the same plotted samples, gaps and axis scale.

No new simulation, training or board experiment was performed. Earlier SIL,
final SIL, historical HIL and local hardware timing retain separate scopes.
