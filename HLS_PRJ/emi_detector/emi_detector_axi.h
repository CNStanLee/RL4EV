#ifndef EMI_DETECTOR_AXI_H
#define EMI_DETECTOR_AXI_H
// EMI sensor-chain injection detector, board version (HGQ2 chain via hls4ml, bit_exact).
// Inputs : the 43 per-cycle features of EMI_DET_FPGA/src/emi_det/features.py (raw, float),
//          computed on the PS or by the feature block from the controller-internal signals.
// Outputs: 5 channel logits (Vdc, Vac, Iac, Vbat, Ibat) and flag bits (logit >= logit(thr)).
//          Persistence (2 consecutive cycles, as in the Simulink SIL block) is applied by the caller.
#define EMI_DET_N_IN 43
#define EMI_DET_N_OUT 5
void emi_detector_axi(float feat[EMI_DET_N_IN], float logit[EMI_DET_N_OUT], unsigned int *flags);
#endif
