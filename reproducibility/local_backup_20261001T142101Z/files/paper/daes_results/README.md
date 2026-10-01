# DAES experimental results

This package assembles existing experiments for the HIL-SAR manuscript. It
recomputes comparisons from individual scorecards and generates seven native
LaTeX tables and three vector PDF figures. No experiments or training runs were
performed during this assembly.

The source files were recovered byte-for-byte from DAES_Special_Issue commit
`1e48d62` (the complete evidence revision preceding the current Overleaf
skeleton). `source_manifest.json` records each original repository, full commit,
path, byte count and SHA-256. That revision contains later final-policy and
board evidence beyond the September 5 RL4EV snapshot at `e2b41c3`.

The manuscript carries the same package at `results_evidence/`, so it can be
rebuilt without the RL4EV checkout. The Git histories preserve the larger
waveform archive and original analysis packages; this compact selection keeps
the scorecards needed to independently verify the primary endpoints.

## Rebuild

Install the analysis dependencies and audit the records:

```bash
python -m pip install -r paper/daes_results/requirements.txt
python paper/daes_results/build_results.py
python paper/daes_results/build_results.py --manuscript /path/to/DAES_Special_Issue
```

From the manuscript repository, use:

```bash
python -m pip install -r results_evidence/requirements.txt
python results_evidence/build_results.py --manuscript .
```

`derived/` contains the recomputed controller, ablation and detector summaries
and a validation report. The export writes `tables/*.tex` and
`figs/results/*.pdf`. Ordinary manuscript compilation requires no Python or
shell escape. The generator checks source hashes before writing results and
checks 117 comparison endpoints plus 26 additional ablation scorecards against
the original individual records.

## Evidence that supports the introduction

| Claim | Result | Manuscript evidence |
|---|---|---|
| Sensor corruption matters beyond harmonic quality | Eight unprotected strategies each achieve 5/13 joint successes despite differing clean THD | Controller table and attack sweeps |
| The compact IDS can trigger a response | 102/104 attacked-channel hits; 40/104 exact sets | Detector table and channel/latency figure |
| Detection-conditioned correction improves regulation | 5/13 to 10/13 joint success; 23.99 to 0.32 V mean absolute bus error | Final SIL case figure and ablations |
| The hardware participates in closed-loop control | Seven complete MATLAB–PL pairs, five joint passes; matching latch outcomes | HIL outcome table |
| Embedded timing requires a separate check | 124/400001 control deadline misses despite a 3.97 us median local service time | Concurrent board-replay table |

Joint success means power retention within 1 percentage point of 100% and no
latched true-state violation. Tables use mean absolute bus error, not signed
mean error, peak error or transient overshoot.

## Cohorts and reconstruction limits

- **Final policy:** the 13-case SIL development benchmark uses MPCC_H6/R6;
  settings were refined on these cases. Power, bus, latch and joint metrics
  retain all 13. The power-11 subset excludes BAT-01b/01n; the THD-11 subset
  instead excludes DC-01c/BAT-02c. These subsets must not be interchanged.
- **Detector:** 104 trajectories are 13 attacks under eight unprotected
  software controls. The random cohort has 17 attacked and three benign runs.
  These are neither 104 hardware trials nor same-run final-policy attribution
  measurements. Channel precision/recall are original attack-cycle summaries.
  Original false-flag denominators are preserved in `ids_original_table.tex`;
  full cycle arrays are not included here. No deployment false-alarm estimate
  or cross-family generalisation claim follows from these small cohorts.
- **HIL:** the seven full pairs test the earlier response configuration. Its
  historical release differs from final SIL routing and safeguards. Five passes
  are endpoint counts, not five cases newly rescued over a hardware baseline.
  Three random full-loop records lack paired scorecards.
- **Timing:** service and response describe independent local board replay,
  excluding the MATLAB/network round trip. The provided task summaries are
  preserved originals, not newly measured timing. The full 400001-row control
  trace remains in the archived revision rather than this compact package.
- **Sweeps:** the original harmonic baseline and final common-case rerun have
  different versions. The figure labels these scopes; missing amplitudes and
  THD withheld below 5% retained power are not zero observations.
- **Early experiments:** the local `sensor_attack_il` campaign has a roughly
  780 V / 14.75 kW baseline; the `Simulation/PV_MEV/exp` diagnostics include
  incorrect strategy flags or off-target bus operating points. Their summaries
  and scripts remain separate in RL4EV and are not pooled into the 400 V /
  6.90 kW charging benchmark. `FFT_HGQ_BLS_FPGA/reports/estimator_comparison.csv`
  is an offline phasor study, not final IDS or hardware-recovery evidence.

The exact historical HIL platform additionally needs its original communication
service, build dependencies and saved operating points. The archived methodology
and interface audits at the source revision describe those missing components.
