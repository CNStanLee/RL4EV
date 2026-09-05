#include <cmath>
#include "harmonic_estimator_axi.h"
#include "firmware/harmonic_estimator.h"

void harmonic_estimator_axi(float wave[HE_N_IN], float enc[HE_N_ENC], float *peak) {
#pragma HLS INTERFACE mode=s_axilite port=wave   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=enc    bundle=control
#pragma HLS INTERFACE mode=s_axilite port=peak   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
    // CycleNorm: A = max(|x|, 1e-6), x_norm = x / A
    float A = 1e-6f;
PEAK: for (int i = 0; i < HE_N_IN; ++i) {
#pragma HLS PIPELINE
        float a = std::fabs(wave[i]); if (a > A) A = a;
    }
    float invA = 1.0f / A;
    waveform_t x[HE_N_IN];
#pragma HLS ARRAY_PARTITION variable=x complete dim=0
NORM: for (int i = 0; i < HE_N_IN; ++i) {
#pragma HLS PIPELINE II=1
        x[i] = waveform_t(wave[i] * invA);          // ap_fixed<8,3,AP_RND,AP_SAT>: the network's input quantizer; one shared float multiplier
    }
    result_t y[HE_N_ENC];
#pragma HLS ARRAY_PARTITION variable=y complete dim=0
    harmonic_estimator(x, y);
OUT: for (int k = 0; k < HE_N_ENC; ++k) {
#pragma HLS PIPELINE II=1
        enc[k] = y[k].to_float();
    }
    *peak = A;
}
