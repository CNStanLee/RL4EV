// C testbench: emi_feat_hls vs features.cycle_features_v3 (tb_data from EMI_DET_FPGA/scripts/make_feat_vectors.py).
// Pass criterion per value: relative error <= 1e-3 (denominator max(|ref|, 1)) or absolute error <= 1e-2.  The absolute
// tolerance covers float32 vs float64 differences that are not errors: the phase of a sub-volt 50 Hz bus component
// (vdc_h1_phase) and the half-cycle duty asymmetry when a sample sits exactly on a zero crossing (sinf(pi) < 0).
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "emi_feat_hls.h"

static bool read_rows(const char *path, int ncol, std::vector<std::vector<float> > &rows) {
    std::ifstream f(path); std::string line;
    if (!f) { std::printf("cannot open %s\n", path); return false; }
    while (std::getline(f, line)) { std::istringstream ss(line); std::vector<float> r(ncol); for (int i = 0; i < ncol; ++i) ss >> r[i]; rows.push_back(r); }
    return true;
}

int main() {
    std::vector<std::vector<float> > X, F, S;
    if (!read_rows("tb_data/buf_raw.dat", EF_N * EF_C, X) || !read_rows("tb_data/ref_feat.dat", EF_NF, F) || !read_rows("tb_data/run_start.dat", 1, S)) return 1;
    std::ofstream fo("tb_data/csim_results.log");
    double worst = 0; int worst_k = -1, nbad = 0;
    for (size_t r = 0; r < X.size(); ++r) {
        float feat[EF_NF];
        unsigned int flags = (unsigned int)S[r][0];
        emi_feat_hls(&X[r][0], flags & 1u, feat);
        if (flags & 2u) continue;                       // cycle excluded from the comparison (NaN in the log)
        for (int k = 0; k < EF_NF; ++k) {
            double ref = F[r][k], ae = std::fabs((double)feat[k] - ref), e = ae / std::fmax(std::fabs(ref), 1.0);
            if (e > worst) { worst = e; worst_k = k; }
            if (e > 1e-3 && ae > (k == 46 ? 2e-2 : 1e-2)) ++nbad;   // d_asym: one zero-crossing sample = up to 0.02 of duty
            fo << feat[k] << (k + 1 < EF_NF ? ' ' : '\n');
        }
    }
    std::printf("emi_feat: %zu cycles  worst rel err %.3g (feature %d)  values outside tolerance: %d\n", X.size(), worst, worst_k, nbad);
    return nbad == 0 ? 0 : 2;
}
