// C testbench for mpcc_r_hls:
//   1. flags = 0, mask = all: the output must be bit-identical to the validated mpcc_hls over a synthetic
//      grid cycle sequence (identity path);
//   2. Iac flag with amp_iac: the predictor current is shifted by -amp*20 A and the harmonic phasors are held;
//   3. Vac flag: the feed-forward voltage becomes V_amp * sin(theta) from the previous cycle (a DC bias on V_in
//      is removed); after the flag clears the correction ramps out over t_ramp.
#include <cmath>
#include <cstdio>
#include "mpcc_r_hls.h"
#include "../mpcc/mpcc_hls.h"

int main() {
    const float Ts = 50e-6f, L = 600e-6f, Vo = 400.0f, Iamp = 32.0f, Vamp = 325.0f, w = 2.0f * 3.14159265f * 50.0f;
    const float A3 = 1.5f, A5 = 0.8f, A7 = 0.4f, p3 = 0.3f, p5 = -0.5f, p7 = 1.0f;
    float dbg[6];
    int n_diff = 0, n = 0; double max_diff = 0.0;
    // ---- 1. identity: 4 cycles, flags 0
    for (int k = 0; k < 4 * 400; ++k) {
        float t = k * Ts, th = std::fmod(w * t, 2.0f * 3.14159265f);
        float vin = Vamp * std::sin(th), iL = Iamp * std::sin(th) + 0.5f * std::sin(3.0f * th), iref = Iamp;
        float D0, D1;
        mpcc_hls(iL, iref, vin, Ts, L, Vo, th, A3, A5, A7, p3, p5, p7, true, &D0);
        mpcc_r_hls(iL, iref, vin, Ts, L, Vo, th, A3, A5, A7, p3, p5, p7, true, 0u, 0.0f, 511u, 0.06f, &D1, dbg);
        double d = std::fabs((double)D0 - D1); if (d > max_diff) max_diff = d; if (d != 0.0) ++n_diff; ++n;
    }
    std::printf("identity: %d ticks, %d differ, max |dD| %.3g\n", n, n_diff, max_diff);
    // ---- 2. Iac flag: i_used = i_L - 0.25*20 = i_L - 5 A, phasors held at the pre-flag values
    bool ok_iac = true;
    for (int k = 0; k < 400; ++k) {
        float t = k * Ts, th = std::fmod(w * t, 2.0f * 3.14159265f);
        float vin = Vamp * std::sin(th), iL = Iamp * std::sin(th), D1;
        mpcc_r_hls(iL, Iamp, vin, Ts, L, Vo, th, 9.0f, 9.0f, 9.0f, 0.0f, 0.0f, 0.0f, true, 4u, 0.25f, 511u, 0.06f, &D1, dbg);
        if (std::fabs(dbg[5] - (iL - 5.0f)) > 1e-4f || dbg[3] != 1.0f || dbg[1] != 1.0f) ok_iac = false;
    }
    std::printf("iac flag: i_used = i_L - 5 A, hold = 1: %s\n", ok_iac ? "ok" : "FAIL");
    // ---- 3. Vac flag with a +20 V DC bias on V_in: after one full cycle V_amp ~ 325 and V_used ~ Vamp*sin(theta)
    bool ok_vac = true; float worst = 0.0f;
    for (int k = 0; k < 3 * 400; ++k) {
        float t = k * Ts, th = std::fmod(w * t, 2.0f * 3.14159265f);
        float vin = Vamp * std::sin(th) + 20.0f, iL = Iamp * std::sin(th), D1;
        mpcc_r_hls(iL, Iamp, vin, Ts, L, Vo, th, A3, A5, A7, p3, p5, p7, true, 2u, 0.0f, 511u, 0.06f, &D1, dbg);
        if (k >= 2 * 400) { float e = std::fabs(dbg[4] - Vamp * std::sin(th)); if (e > worst) worst = e; }
    }
    if (worst > 2.0f) ok_vac = false;
    std::printf("vac flag: |V_used - Vamp sin(theta)| max %.2f V after one cycle (bias 20 V removed): %s\n", worst, ok_vac ? "ok" : "FAIL");
    // ---- 4. ramp-out: after clearing the Vac flag g_vac decays to 0 within t_ramp = 60 ms (1200 ticks)
    float g_mid = -1.0f, g_end = -1.0f;
    for (int k = 0; k < 1300; ++k) {
        float t = k * Ts, th = std::fmod(w * t, 2.0f * 3.14159265f);
        float vin = Vamp * std::sin(th), iL = Iamp * std::sin(th), D1;
        mpcc_r_hls(iL, Iamp, vin, Ts, L, Vo, th, A3, A5, A7, p3, p5, p7, true, 0u, 0.0f, 511u, 0.06f, &D1, dbg);
        if (k == 600) g_mid = dbg[0];
        if (k == 1299) g_end = dbg[0];
    }
    bool ok_ramp = (g_mid > 0.3f && g_mid < 0.7f && g_end == 0.0f);
    std::printf("ramp-out: g_vac after 30 ms %.3f, after 65 ms %.3f: %s\n", g_mid, g_end, ok_ramp ? "ok" : "FAIL");
    return (n_diff == 0 && ok_iac && ok_vac && ok_ramp) ? 0 : 2;
}
