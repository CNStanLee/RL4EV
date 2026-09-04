#include <cmath>
#include "harmonic_estimator_axi.h"
#include "firmware/harmonic_estimator.h"

static const float ORDER_SCALE[4] = {1.0f, 0.25f, 0.20f, 0.15f};
static const float ORDERS[3] = {3.0f, 5.0f, 7.0f};

void harmonic_estimator_axi(float wave[HE_N_IN], float enc[HE_N_ENC], float *peak, float legacy[HE_N_LEGACY]) {
#pragma HLS INTERFACE mode=s_axilite port=wave   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=enc    bundle=control
#pragma HLS INTERFACE mode=s_axilite port=peak   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=legacy bundle=control
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
#pragma HLS UNROLL
        x[i] = waveform_t(wave[i] * invA);          // ap_fixed<8,3,AP_RND,AP_SAT>: the network's input quantizer
    }
    result_t y[HE_N_ENC];
#pragma HLS ARRAY_PARTITION variable=y complete dim=0
    harmonic_estimator(x, y);
    float amp[4], ph[4];
DEC: for (int h = 0; h < 4; ++h) {
#pragma HLS UNROLL
        float re = y[2 * h].to_float(), im = y[2 * h + 1].to_float();
        enc[2 * h] = re; enc[2 * h + 1] = im;
        amp[h] = A * ORDER_SCALE[h] * std::sqrt(re * re + im * im);
        ph[h] = std::atan2(im, re);
    }
    *peak = A;
    for (int h = 0; h < 4; ++h) legacy[h] = amp[h];
REL: for (int k = 0; k < 3; ++k) {
#pragma HLS UNROLL
        float rel = ph[k + 1] - ORDERS[k] * ph[0];
        legacy[4 + k] = std::atan2(std::sin(rel), std::cos(rel));
    }
}
