// C testbench: fixed-point network vs the host reference logits (artifacts/detector.onnx).
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
    std::vector<std::vector<float> > X, Y;
    if (!read_rows("tb_data/feat_raw.dat", EMI_DET_N_IN, X) || !read_rows("tb_data/ref_logits.dat", EMI_DET_N_OUT, Y)) return 1;
    std::ofstream fo("tb_data/csim_results.log");
    double maxerr = 0, sumsq = 0; int nflag_mismatch = 0, n = 0;
    for (size_t r = 0; r < X.size(); ++r) {
        float logit[EMI_DET_N_OUT]; unsigned int flags = 0;
        emi_detector_axi(&X[r][0], logit, &flags);
        unsigned int fref = 0;
        for (int k = 0; k < EMI_DET_N_OUT; ++k) {
            double e = std::fabs((double)logit[k] - Y[r][k]); if (e > maxerr) maxerr = e; sumsq += e * e; ++n;
            if (Y[r][k] >= std::log(0.05 / 0.95)) fref |= (1u << k);
            fo << logit[k] << (k + 1 < EMI_DET_N_OUT ? ' ' : '\n');
        }
        if (fref != flags) ++nflag_mismatch;
    }
    std::printf("emi_detector: %zu cycles  max |dlogit| %.4g  rms %.4g  flag-word mismatches %d\n", X.size(), maxerr, std::sqrt(sumsq / n), nflag_mismatch);
    return (maxerr < 0.05 && nflag_mismatch == 0) ? 0 : 2;
}
