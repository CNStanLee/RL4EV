// C testbench: fixed-point network vs the host reference logits (artifacts/detector_bitexact.onnx).
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "emi_detector_axi.h"

static bool read_rows(const char *path, int ncol, std::vector<std::vector<float> > &rows) {
    std::ifstream f(path); std::string line;
    if (!f) { std::printf("cannot open %s\n", path); return false; }
    while (std::getline(f, line)) {
        std::istringstream ss(line); std::vector<float> r(ncol); for (int i = 0; i < ncol; ++i) ss >> r[i]; rows.push_back(r);
    }
    return true;
}

int main() {
    std::vector<std::vector<float> > X, Y, T;
    if (!read_rows("tb_data/feat_raw.dat", EMI_DET_N_IN, X) || !read_rows("tb_data/ref_logits.dat", EMI_DET_N_OUT, Y)) return 1;
    if (!read_rows("tb_data/thresholds.dat", 2 * EMI_DET_N_OUT + 1, T)) return 1;     // [thr_logit x5, clr_logit x5, persist]
    float THR_LOGIT[EMI_DET_N_OUT], CLR_LOGIT[EMI_DET_N_OUT];
    for (int k = 0; k < EMI_DET_N_OUT; ++k) { THR_LOGIT[k] = T[0][k]; CLR_LOGIT[k] = T[0][EMI_DET_N_OUT + k]; }
    const unsigned int PERSIST_REF = (unsigned int)T[0][2 * EMI_DET_N_OUT];
    std::ofstream fo("tb_data/csim_results.log");
    double maxerr = 0, sumsq = 0; int nflag_mismatch = 0, n = 0;
    // reference flag words: the same persistence / hysteresis rule applied to the host logits (rows are consecutive cycles)
    unsigned int rcnt[EMI_DET_N_OUT] = {0, 0, 0, 0, 0}, ron[EMI_DET_N_OUT] = {0, 0, 0, 0, 0};
    for (size_t r = 0; r < X.size(); ++r) {
        float logit[EMI_DET_N_OUT], amp[EMI_DET_N_OUT]; unsigned int flags = 0;
        emi_detector_axi(&X[r][0], logit, amp, &flags, r == 0 ? 1u : 0u);
        unsigned int fref = 0;
        for (int k = 0; k < EMI_DET_N_OUT; ++k) {
            double e = std::fabs((double)logit[k] - Y[r][k]); if (e > maxerr) maxerr = e; sumsq += e * e; ++n;
            unsigned int above = Y[r][k] >= THR_LOGIT[k], below = Y[r][k] < CLR_LOGIT[k];
            rcnt[k] = above ? rcnt[k] + 1 : 0;
            ron[k] = ron[k] ? (below ? 0u : 1u) : (rcnt[k] >= PERSIST_REF ? 1u : 0u);
            if (ron[k]) fref |= (1u << k);
            fo << logit[k] << (k + 1 < EMI_DET_N_OUT ? ' ' : '\n');
        }
        if (fref != flags) ++nflag_mismatch;
    }
    std::printf("emi_detector: %zu cycles  max |dlogit| %.4g  rms %.4g  flag-word mismatches %d\n", X.size(), maxerr, std::sqrt(sumsq / n), nflag_mismatch);
    return (maxerr < 0.05 && nflag_mismatch == 0) ? 0 : 2;
}
