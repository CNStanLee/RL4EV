#ifndef EMI_FEAT_HLS_H
#define EMI_FEAT_HLS_H
// Per-cycle feature extraction for the EMI detector (plan step 4, `emi_feat_hls`): the 48 features of
// EMI_DET_FPGA/src/emi_det/features.py::cycle_features_v3 (the same code that runs as `emi_features` in the
// Simulink EMI Detector), computed from one grid cycle of the controller-internal signals sampled at 10 kHz.
//   buf   : 200 x 12 cycle buffer, row-major (sample, column); columns
//           0 Vdc_int 1 Vac_int 2 Iac_int 3 Iref 4 theta_pll 5 D 6 Vref 7 Vbat_int 8 Ibat_int 9 D_dcdc 10 state 11 Iref_bat
//   reset : 1 at the first cycle of a run (clears the previous-cycle state of the delta features)
//   feat  : the 48 features (float), order features.FEATURE_NAMES_V3
#define EF_N 200
#define EF_C 12
#define EF_NF 48
void emi_feat_hls(const float buf[EF_N * EF_C], unsigned int reset, float feat[EF_NF]);
#endif
