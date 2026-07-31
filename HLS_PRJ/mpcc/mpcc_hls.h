#ifndef MPCC_HLS_H
#define MPCC_HLS_H

void mpcc_hls(
    float i_L,
    float i_ref,
    float V_in,
    float Ts,
    float L_in,
    float V_o,
    float theta_pll,
    float A3,
    float A5,
    float A7,
    float phi3,
    float phi5,
    float phi7,
    bool use_harmonic,
    float *D
);

#endif