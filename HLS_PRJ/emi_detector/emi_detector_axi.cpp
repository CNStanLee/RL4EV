#include "emi_detector_axi.h"
#include "firmware/emi_detector.h"

// standardization constants from artifacts/detector.json (fit on the clean training cycles)
static const float MU[43] = {
    0.452427208f, 330.968567f, 0.00136590679f, -0.110357597f, 24.3419266f, 36.8576317f,
    -37.3611794f, -0.503640831f, 0.515204668f, 0.102745511f, 33.6285934f, 0.943373978f,
    169.768158f, 0.317339271f, 0.0169617943f, 400.775665f, 22.9975262f, 1.38252556f,
    34.2839394f, 30.3594303f, 38.2718048f, 0.0360722989f, 0.460454315f, -0.00668719318f,
    335.240692f, 15.6070681f, 0.838858843f, 0.233473971f, 15.8857546f, 0.322431296f,
    0.428881049f, 5550.42529f, 5386.72412f, 1.19960403f, 0.00161808683f, -0.535636067f,
    0.0827274844f, -0.331068784f, -0.105745643f, -0.0202678833f, -0.0238384716f, -0.0680045635f,
    -0.0180891175f
};

static const float INV_SD[43] = {
    0.188361973f, 0.435125053f, 62.3328018f, 0.551350534f, 0.118013203f, 0.0640394837f,
    0.0634084493f, 0.163350761f, 0.0744036585f, 3.54814243f, 0.0836282969f, 4.36267328f,
    0.000386802945f, 0.160766721f, 4.87428236f, 0.0622568764f, 0.0433760062f, 0.0701699927f,
    0.0410983339f, 0.0401347131f, 0.0407579988f, 5.54805231f, 10.5066071f, 11.5857353f,
    0.0171141345f, 0.164401978f, 6.53403473f, 2.36599827f, 0.170070127f, 0.489731461f,
    0.404061973f, 0.000502668496f, 0.000478076574f, 0.320901692f, 21.3969498f, 0.063426435f,
    0.129464343f, 0.125259876f, 0.301011562f, 0.694449306f, 1.49527252f, 0.912822008f,
    0.281426698f
};

// per-channel logit thresholds (1 % false-alarm budget, detector.json thr = [0.05000000074505806, 0.05000000074505806, 0.05000000074505806, 0.05000000074505806, 0.05000000074505806])
static const float LOGIT_THR[5] = {
    -2.94443893f, -2.94443893f, -2.94443893f, -2.94443893f, -2.94443893f
};


void emi_detector_axi(float feat[EMI_DET_N_IN], float logit[EMI_DET_N_OUT], unsigned int *flags) {
#pragma HLS INTERFACE mode=s_axilite port=feat   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=logit  bundle=control
#pragma HLS INTERFACE mode=s_axilite port=flags  bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
    features_t x[EMI_DET_N_IN];
#pragma HLS ARRAY_PARTITION variable=x complete dim=0
    result_t y[EMI_DET_N_OUT];
#pragma HLS ARRAY_PARTITION variable=y complete dim=0
STD: for (int i = 0; i < EMI_DET_N_IN; ++i) {
#pragma HLS UNROLL
        x[i] = features_t((feat[i] - MU[i]) * INV_SD[i]);   // float affine, then the network's input quantizer (RND/SAT)
    }
    emi_detector(x, y);
    unsigned int f = 0;
OUT: for (int k = 0; k < EMI_DET_N_OUT; ++k) {
#pragma HLS UNROLL
        float v = y[k].to_float();
        logit[k] = v;
        if (v >= LOGIT_THR[k]) f |= (1u << k);
    }
    *flags = f;
}
