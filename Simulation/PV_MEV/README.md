# PV_MEV — PV + EV charger (totem-pole PFC) controller benchmark

## Files
| File | Purpose |
|---|---|
| `PV_MEV.slx` | Simulink model (grid + PV + one active EV charger; `EV System1/2` are commented out). Model StopTime is the variable `simu_time`. |
| `init_paras.m` | Model InitFcn. Defines all plant/controller parameters and loads the controller variant selected by `VARIANT_NAME` from `config.csv`. `Ts_Control = 1/Fc` is derived only here. |
| `config.csv` | Controller variant table: `VARIANT_NAME, Fc, use_d_predict, use_p_predict, use_harmonic, estimation_src, simu_time, note`. |
| `run_benchmark.m` | Runs variants headlessly, logs EV-side metrics, writes `results/<VARIANT>.csv` and merges into `results/benchmark_results.csv`. |
| `results/` | Latest benchmark output. |

## Usage
```matlab
% interactive: pick a variant, then press Run in Simulink
VARIANT_NAME = "MPCC_D_F1";

% headless benchmark (all rows of config.csv, or a subset)
run_benchmark
run_benchmark({'CRPR','MPCC_D'})
run_benchmark('merge')                            % only rebuild results/benchmark_results.csv
run_benchmark({'CRPR'}, struct('stop_time',0.05)) % smoke test
```
Several MATLAB processes may run different subsets in parallel; each writes its own `results/<VARIANT>.csv`.

## Variant flags
- `use_p_predict = 1`: MPCC decides the gate directly every `Ts_Control` (PWM generator bypassed).
- `use_d_predict = 1`: MPCC predicts the duty cycle, fed to the 100 kHz PWM generator.
- both 0: PR current controller (CRPR).
- `use_harmonic = 1`: 3rd/5th/7th harmonic estimate subtracted from the current reference (MPCC_D only).
- `estimation_src`: 1 FFT 1-cycle, 2 FFT 10-cycle, 3 ONNX 1-cycle, 4 ONNX half-cycle, 5 RLS. The ONNX subsystems are commented out in the model and need the Python environment (`pyenv` line in `init_paras.m`).

## Metrics (last 100 ms of the run)
`Vdc_V, Vdc_ripple_pct, Pdc_kW, Pac_kW, eff_pct, PF, Iref_A, D_mean, Vdc_min_step_V, t_settle_ms`
plus three THD figures for the AC current:
- `THD50_pct`: offline FFT of `Iac` sampled at 1 MHz, harmonics 2..50 (≤ 2.5 kHz). Comparable across control frequencies.
- `THD_full_pct`: same FFT, all non-fundamental content up to 500 kHz (includes switching ripple).
- `THD_model_pct`: the THD block inside `Measurements 1`, sampled at `Ts_Control`; not comparable between different `Fc`.

## Notes
- `Pac`/`Pdc` in `Measurements 1` are averaged at `Ts_Power`. Sampling them at `Ts_Control` (= PWM frequency for CRPR) aliased the current ripple and under-read `Pac` by ~115 W.
- `D_predict` keeps the sign of the current reference. Taking `abs(i_ref)` turned a negative voltage-loop output into a positive current demand and latched `Vdc` at 600–830 V.
- The HIL TCP/IP blocks in `EV System/PFC Control` need an external server; `run_benchmark` comments them out in memory when `ENABLE_HIL = 0`.
