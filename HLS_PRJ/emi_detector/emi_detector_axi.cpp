#include "emi_detector_axi.h"
#include "firmware/emi_detector.h"

// standardization constants from artifacts/detector.json (fit on the clean training cycles)
static const float MU[48] = {
    4.236492515e-01f, 3.309611206e+02f, 1.278895768e-03f, -8.579470962e-02f, 2.418814468e+01f, 3.688135529e+01f,
    -3.723733139e+01f, -3.559753895e-01f, 4.346691072e-01f, 1.030905992e-01f, 3.335012817e+01f, 9.421547651e-01f,
    1.831237640e+02f, 2.648311853e-01f, 1.425772905e-02f, 4.005278625e+02f, 2.255851746e+01f, 1.057248354e+00f,
    3.429264069e+01f, 3.045306587e+01f, 3.818210220e+01f, 3.587521985e-02f, 4.638349712e-01f, -8.551449515e-03f,
    3.456467590e+02f, 1.592523956e+01f, 8.652107120e-01f, 2.789103389e-01f, 1.623883057e+01f, 2.780252993e-01f,
    4.311988354e-01f, 5.503657715e+03f, 5.499462402e+03f, 1.156785250e+00f, 1.892927685e-03f, -6.040251851e-01f,
    8.440938592e-02f, -2.957803011e-01f, -5.991514027e-02f, -1.565635204e-02f, -2.714059874e-02f, -5.418769643e-02f,
    -1.680800132e-02f, 1.788978457e+00f, 2.561174631e-01f, -3.975652158e-01f, 7.705302560e-04f, 0.000000000e+00f
};

static const float INV_SD[48] = {
    2.002748698e-01f, 4.952350855e-01f, 6.627664948e+01f, 6.015397310e-01f, 1.172919273e-01f, 6.210835651e-02f,
    6.206950173e-02f, 1.740370691e-01f, 8.143241704e-02f, 3.627184153e+00f, 8.374492079e-02f, 4.283827782e+00f,
    3.657028137e-04f, 1.759325713e-01f, 5.191930294e+00f, 8.432039618e-02f, 4.608960822e-02f, 1.054714546e-01f,
    4.103986174e-02f, 4.030073434e-02f, 4.068725929e-02f, 5.563406467e+00f, 1.216891956e+01f, 1.161923695e+01f,
    2.678139806e-01f, 1.822600365e-01f, 2.022879219e+01f, 2.231807232e+00f, 1.910185814e-01f, 5.678726435e-01f,
    3.943926096e-01f, 5.033135531e-04f, 5.315396120e-04f, 4.181021452e-01f, 1.783732796e+01f, 5.165788531e-02f,
    1.560598016e-01f, 1.384278983e-01f, 3.125458360e-01f, 7.634658217e-01f, 1.409210920e+00f, 8.761844039e-01f,
    3.494043946e-01f, 2.376833558e-01f, 7.852470279e-01f, 5.886685252e-01f, 2.817994308e+01f, 1.000000000e+06f
};

// per-channel logit thresholds (1 % false-alarm budget, detector.json thr = [0.10000000149011612, 0.05000000074505806, 0.20000000298023224, 0.05000000074505806, 0.05000000074505806]) and the hysteresis
// clear thresholds logit(hyst * thr), hyst = 0.6; persistence 2 cycles
static const float LOGIT_THR[5] = {
    -2.197224617e+00f, -2.944438934e+00f, -1.386294365e+00f, -2.944438934e+00f, -2.944438934e+00f
};

static const float LOGIT_CLR[5] = {
    -2.751535416e+00f, -3.476098776e+00f, -1.992430091e+00f, -3.476098776e+00f, -3.476098776e+00f
};

static const unsigned int PERSIST = 2;

void emi_detector_axi(float feat[EMI_DET_N_IN], float logit[EMI_DET_N_OUT], float amp[EMI_DET_N_OUT], unsigned int *flags, unsigned int reset) {
#pragma HLS INTERFACE mode=s_axilite port=feat   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=logit  bundle=control
#pragma HLS INTERFACE mode=s_axilite port=amp    bundle=control
#pragma HLS INTERFACE mode=s_axilite port=flags  bundle=control
#pragma HLS INTERFACE mode=s_axilite port=reset  bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
    static unsigned int cnt[EMI_DET_N_OUT] = {0, 0, 0, 0, 0};
    static unsigned int on[EMI_DET_N_OUT] = {0, 0, 0, 0, 0};
#pragma HLS ARRAY_PARTITION variable=cnt complete dim=0
#pragma HLS ARRAY_PARTITION variable=on complete dim=0
    features_t x[EMI_DET_N_IN];
#pragma HLS ARRAY_PARTITION variable=x complete dim=0
    result_t y[EMI_DET_N_HEAD];
#pragma HLS ARRAY_PARTITION variable=y complete dim=0
STD: for (int i = 0; i < EMI_DET_N_IN; ++i) {
#pragma HLS PIPELINE II=1
        x[i] = features_t((feat[i] - MU[i]) * INV_SD[i]);   // float affine, then the network's input quantizer (RND/SAT); one shared float datapath
    }
    emi_detector(x, y);
    unsigned int f = 0;
OUT: for (int k = 0; k < EMI_DET_N_OUT; ++k) {
#pragma HLS PIPELINE II=1
        float v = y[k].to_float();
        logit[k] = v;
        unsigned int above = (v >= LOGIT_THR[k]) ? 1u : 0u;
        unsigned int below = (v < LOGIT_CLR[k]) ? 1u : 0u;
        if (reset) { cnt[k] = 0; on[k] = 0; }
        cnt[k] = above ? cnt[k] + 1 : 0;
        on[k] = on[k] ? (below ? 0u : 1u) : (cnt[k] >= PERSIST ? 1u : 0u);
        if (on[k]) f |= (1u << k);
        amp[k] = (EMI_DET_N_AMP > 0 && on[k]) ? y[EMI_DET_N_OUT + (k < EMI_DET_N_AMP ? k : 0)].to_float() : 0.0f;
    }
    *flags = f;
}
