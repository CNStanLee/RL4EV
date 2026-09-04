#ifndef HARMONIC_ESTIMATOR_AXI_H
#define HARMONIC_ESTIMATOR_AXI_H
// HGQ2 Residual-BLS harmonic estimator (FFT_HGQ_BLS_FPGA contract), board version.
// Input : one grid cycle of the PFC current, 80 samples at 4 kHz (raw amperes; the wrapper normalizes by the window peak).
// Output: enc[8] = [c1,s1,c3,s3,c5,s5,c7,s7] (network output, normalized), peak (side channel), and the legacy
//         MPCC vector legacy[7] = [A1,A3,A5,A7,delta3,delta5,delta7] decoded as in harmonic_postprocess8_block
//         (ema_alpha = 1: the EMA, if wanted, is applied by the caller on enc[]).
#define HE_N_IN 80
#define HE_N_ENC 8
#define HE_N_LEGACY 7
void harmonic_estimator_axi(float wave[HE_N_IN], float enc[HE_N_ENC], float *peak, float legacy[HE_N_LEGACY]);
#endif
