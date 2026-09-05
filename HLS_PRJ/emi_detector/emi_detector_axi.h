#ifndef EMI_DETECTOR_AXI_H
#define EMI_DETECTOR_AXI_H
// EMI sensor-chain injection detector, board version (HGQ2 chain via hls4ml, bit_exact).
// Inputs : the 48 per-cycle features of EMI_DET_FPGA/src/emi_det/features.py (raw, float),
//          computed on the PS or by the feature block from the controller-internal signals.
// Outputs: 5 channel logits (Vdc, Vac, Iac, Vbat, Ibat) and flag bits (logit >= logit(thr)).
//          Persistence (2 consecutive cycles, as in the Simulink SIL block) is applied by the caller.
#define EMI_DET_N_IN 48
#define EMI_DET_N_OUT 5
#define EMI_DET_N_HEAD 10
#define EMI_DET_N_AMP 5
// v5: the network head is [5 logits, 5 signed normalized amplitudes]; the IP keeps the per-channel
// persistence counter and hysteresis state (set after EMI_DET_PERSIST cycles >= thr, clear when p < hyst*thr),
// flags = current flag word, amp = amplitudes (0 while a channel is not flagged).  reset = 1 clears the state.
void emi_detector_axi(float feat[EMI_DET_N_IN], float logit[EMI_DET_N_OUT], float amp[EMI_DET_N_OUT], unsigned int *flags, unsigned int reset);
#endif
