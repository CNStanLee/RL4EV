# harmonic_estimator (Vitis HLS component)

Board version of the HGQ2 Residual-BLS harmonic estimator (`FFT_HGQ_BLS_FPGA`, 8-bit KIF, 30,664 parameters; the
model behind the MPCC_D_M1 / MPCC_D_H1 variants), exported with hls4ml 1.3 (Vitis backend, `bit_exact=True`,
io_parallel) from `EMI_DET_FPGA/fpga/estimator_hls4ml`, wrapped like `HLS_PRJ/mpcc`:

- `harmonic_estimator_axi(float wave[80], float enc[8], float *peak)`, one `s_axilite` bundle `control`.
- `wave` is one grid cycle of the PFC current sampled at 4 kHz (raw amperes). The wrapper performs the contract's
  CycleNorm (`x / max|x|`, side channel `peak`) and the input quantizer `ap_fixed<8,3,AP_RND,AP_SAT>`.
- `enc` = `[c1,s1,c3,s3,c5,s5,c7,s7]` (network output). The legacy MPCC vector `[A1,A3,A5,A7,delta3,delta5,delta7]`
  (decode of `harmonic_postprocess8_block` in `Simulation/PV_MEV/build_estimator.m`, `ema_alpha = 1`) is computed on the
  PS from `enc` and `peak` (`mpcc_r_overlay.decode_legacy`): it needs sqrt / atan2 in float, which cost about 30k LUT in
  the IP. `A3..A7`, `delta3..7` feed `mpcc_r_hls`; the FFT anchor / watchdog fusion stays on the PS.

Build (same flow as `mpcc`):

```
vitis-run --mode hls --cfg hls_config.cfg --work_dir harmonic_estimator --csim
vitis-run --mode hls --cfg hls_config.cfg --work_dir harmonic_estimator --csynth
```

`tb_data/` holds the 1287 test_id windows of `FFT_HGQ_BLS_FPGA/artifacts/pv_mev_v2/residual_bls/onnx_reference_test_id.npz` (un-normalized) with
the host ONNX outputs; the testbench passes when every output is within 2 LSB (0.0625) of the reference.
Local C simulation without Vitis: `EMI_DET_FPGA/scripts/csim_local.sh harmonic_estimator`.
