#ifndef MPCC_R_HLS_H
#define MPCC_R_HLS_H
// Resilient MPCC (MPCC_R, plan step 4): the validated mpcc_hls duty predictor plus the
// detection-conditioned input corrections of Simulation/PV_MEV/build_mitigation.m that belong
// to the inner current loop (M2 Vac feed-forward reconstruction, M3 Iac DC compensation,
// M4 harmonic-phasor hold, M7 ramp-out).  The voltage-loop corrections (M0/M1) and the charger
// corrections (M5/M6) act on the outer loops that run on the PS.
// With flags == 0 (and after the ramp has expired) the output is bit-identical to mpcc_hls.
//   flags   : detector flag word, bit0 Vdc bit1 Vac bit2 Iac bit3 Vbat bit4 Ibat (2-cycle persistence applied upstream)
//   amp_iac : detector signed normalized Iac amplitude (x 20 A)
//   mask    : mitigation_mask bits (4 Vac feed-forward, 8 Iac DC, 16 estimator hold, 128 ramp-out)
//   t_ramp  : ramp-out time (s) after a flag clears
//   dbg     : [g_vac, g_iac, V_amp, hold, V_in_used, i_L_used]
void mpcc_r_hls(
    float i_L, float i_ref, float V_in, float Ts, float L_in, float V_o, float theta_pll,
    float A3, float A5, float A7, float phi3, float phi5, float phi7, bool use_harmonic,
    unsigned int flags, float amp_iac, unsigned int mask, float t_ramp,
    float *D, float dbg[6]);
#endif
