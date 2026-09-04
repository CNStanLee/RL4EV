# harmonic_estimator (Vitis HLS component)

Board version of the HGQ2 Residual-BLS harmonic estimator (`FFT_HGQ_BLS_FPGA`, 8-bit KIF, 30,664 parameters; the
model behind the MPCC_D_M1 / MPCC_D_H1 variants), exported with hls4ml 1.3 (Vitis backend, `bit_exact=True`,
io_parallel) from `EMI_DET_FPGA/fpga/estimator_hls4ml`, wrapped like `HLS_PRJ/mpcc`:

- `harmonic_estimator_axi(float wave[80], float enc[8], float *peak, float legacy[7])`, one `s_axilite` bundle `control`.
- `wave` is one grid cycle of the PFC current sampled at 4 kHz (raw amperes). The wrapper performs the contract's
  CycleNorm (`x / max|x|`, side channel `peak`) and the input quantizer `ap_fixed<8,3,AP_RND,AP_SAT>`.
- `enc` = `[c1,s1,c3,s3,c5,s5,c7,s7]` (network output); `legacy` = `[A1,A3,A5,A7,delta3,delta5,delta7]` decoded exactly as
  `harmonic_postprocess8_block` in `Simulation/PV_MEV/build_estimator.m` with `ema_alpha = 1` (apply the EMA on `enc` in
  the caller if wanted). `A3..A7`, `delta3..7` feed `mpcc_hls` (`use_harmonic = 1`); the FFT anchor / watchdog fusion
  (`hgq_fusion_alpha`, `hgq_min_ratio` in `init_paras.m`) stays on the PS.

Build (same flow as `mpcc`):

```
vitis-run --mode hls --cfg hls_config.cfg --work_dir harmonic_estimator --csim
vitis-run --mode hls --cfg hls_config.cfg --work_dir harmonic_estimator --csynth
```

`tb_data/` holds the 361 ID windows of `FFT_HGQ_BLS_FPGA/artifacts/onnx_reference_test_id.npz` (un-normalized) with
the host ONNX outputs; the testbench passes when every output is within 2 LSB (0.0625) of the reference.
Local C simulation without Vitis: `EMI_DET_FPGA/scripts/csim_local.sh harmonic_estimator`.
