// C testbench: fixed-point estimator vs the host reference (artifacts/onnx_reference_test_id.npz).
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "harmonic_estimator_axi.h"

static bool read_rows(const char *path, int ncol, std::vector<std::vector<float> > &rows) {
    std::ifstream f(path); std::string line;
    if (!f) { std::printf("cannot open %s\n", path); return false; }
    while (std::getline(f, line)) {
        std::istringstream ss(line); std::vector<float> r(ncol); for (int i = 0; i < ncol; ++i) ss >> r[i]; rows.push_back(r);
    }
    return true;
}

int main() {
    std::vector<std::vector<float> > X, Y, S;
    if (!read_rows("tb_data/wave_raw.dat", HE_N_IN, X) || !read_rows("tb_data/ref_enc.dat", HE_N_ENC, Y) || !read_rows("tb_data/ref_peak.dat", 1, S)) return 1;
    std::ofstream fo("tb_data/csim_results.log");
    double maxerr = 0, sumsq = 0, maxpk = 0; int n = 0;
    for (size_t r = 0; r < X.size(); ++r) {
        float enc[HE_N_ENC], peak;
        harmonic_estimator_axi(&X[r][0], enc, &peak);
        double ep = std::fabs((double)peak - S[r][0]) / S[r][0]; if (ep > maxpk) maxpk = ep;
        for (int k = 0; k < HE_N_ENC; ++k) {
            double e = std::fabs((double)enc[k] - Y[r][k]); if (e > maxerr) maxerr = e; sumsq += e * e; ++n;
            fo << enc[k] << ' ';
        }
        fo << peak << '\n';
    }
    std::printf("harmonic_estimator: %zu windows  max |denc| %.4g  rms %.4g  (output LSB 1/32 = 0.03125)  peak rel err %.3g\n",
                X.size(), maxerr, std::sqrt(sumsq / n), maxpk);
    return (maxerr <= 0.0625 && maxpk < 1e-5) ? 0 : 2;
}
