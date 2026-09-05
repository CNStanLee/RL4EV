# emi_detector (Vitis HLS component)

Board version of the EMI sensor-chain injection detector (`EMI_DET_FPGA/runs/det_v4`, HGQ2 QDense
[64, 64] chain, weights 2,7 / activations 4,7 bits KIF, 32315 parameters), exported with
hls4ml 1.3 (Vitis backend, `bit_exact=True`, io_parallel, ReuseFactor 1) and wrapped like `HLS_PRJ/mpcc`:

- `emi_detector_axi(float feat[43], float logit[5], unsigned *flags)`, one `s_axilite` bundle `control`.
- Inputs are the raw 43 per-cycle features (`EMI_DET_FPGA/src/emi_det/features.py`); the wrapper applies the
  standardization `(x - mu) * inv_sd` in float and the network's input quantizer `ap_fixed<12,5,AP_RND,AP_SAT>`.
- Outputs: the 5 channel logits (Vdc, Vac, Iac, Vbat, Ibat) and `flags` bit k = logit_k >= logit(thr_k) with the
  1 % false-alarm thresholds of `artifacts/detector.json`. The 2-cycle persistence used by the Simulink SIL block is
  left to the caller (PS), so the IP is stateless.

Build (Vitis 2023.2+ unified flow, same as `mpcc`): open the component in Vitis, or

```
vitis-run --mode hls --cfg hls_config.cfg --work_dir emi_detector --csim   # tb_emi_detector.cpp vs tb_data/ref_logits.dat
vitis-run --mode hls --cfg hls_config.cfg --work_dir emi_detector --csynth
```

`tb_data/feat_raw.dat` holds 1089 dataset cycles (every 8th cycle of `data/cycles_dataset.npz`) and
`tb_data/ref_logits.dat` the host logits from `artifacts/detector_bitexact.onnx` (bit-exact export, scripts/export_bitexact_onnx.py); the testbench passes when the fixed-point
logits are within 0.05 and every flag word agrees. Local C simulation without Vitis: `EMI_DET_FPGA/scripts/csim_local.sh emi_detector`.
