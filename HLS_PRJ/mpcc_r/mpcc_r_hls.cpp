#include "mpcc_r_hls.h"
#include <hls_math.h>

static float abs_float(float x) { return x >= 0.0f ? x : -x; }

// ---- the validated duty predictor (HLS_PRJ/mpcc/mpcc_hls.cpp, verbatim apart from the static theta state
//      being passed in so that the same instance serves the resilient wrapper)
static void mpcc_core(float i_L, float i_ref, float V_in, float Ts, float L_in, float V_o, float theta_pll,
                      float A3, float A5, float A7, float phi3, float phi5, float phi7, bool use_harmonic,
                      float &theta_prev, bool &theta_initialized, float *D)
{
    if (!theta_initialized) { theta_prev = theta_pll; theta_initialized = true; }
    const float track_gain = 0.35f;
    const float damp_gain  = 0.015f;
    const float lead_steps = 1.0f;
    float L = L_in > 1.0e-9f ? L_in : 1.0e-9f;
    float Ts_eff = Ts > 1.0e-9f ? Ts : 1.0e-9f;
    float abs_Vo = abs_float(V_o);
    float Vo = abs_Vo > 1.0f ? abs_Vo : 1.0f;
    float ui_L = abs_float(i_L);
    float ui_L_safe = ui_L > 1.0e-6f ? ui_L : 1.0e-6f;
    float line_sign = (V_in > 0.0f) ? 1.0f : -1.0f;
    float i_ref_signed = line_sign * abs_float(i_ref);
    float plant_gain = line_sign * L / (Vo * Ts_eff);
    float D_ff = 1.0f - abs_float(V_in) / Vo;
    if (use_harmonic) {
        float theta_delta = theta_pll - theta_prev;
        float dtheta = hls::atan2(hls::sin(theta_delta), hls::cos(theta_delta));
        theta_prev = theta_pll;
        float omega_inst = dtheta / Ts_eff;
        float theta_ctrl = theta_pll + omega_inst * Ts_eff * lead_steps;
        float A3_abs = abs_float(A3), A5_abs = abs_float(A5), A7_abs = abs_float(A7);
        const float phase_sign = 1.0f;
        float ih3 = A3_abs * hls::sin(3.0f * theta_ctrl + phase_sign * phi3);
        float ih5 = A5_abs * hls::sin(5.0f * theta_ctrl + phase_sign * phi5);
        float ih7 = A7_abs * hls::sin(7.0f * theta_ctrl + phase_sign * phi7);
        const float k3 = 1.00f, k5 = 1.08f, k7 = 1.00f;
        float ih_357 = k3 * ih3 + k5 * ih5 + k7 * ih7;
        i_ref_signed = i_ref_signed - ih_357;
    }
    float i_err = i_ref_signed - i_L;
    float D_corr = plant_gain * track_gain * i_err;
    float D_damp = -line_sign * damp_gain * (i_L - i_ref_signed) / ui_L_safe;
    *D = D_ff + D_corr + D_damp;
}

void mpcc_r_hls(
    float i_L, float i_ref, float V_in, float Ts, float L_in, float V_o, float theta_pll,
    float A3, float A5, float A7, float phi3, float phi5, float phi7, bool use_harmonic,
    unsigned int flags, float amp_iac, unsigned int mask, float t_ramp,
    float *D, float dbg[6])
{
#pragma HLS INTERFACE mode=s_axilite port=i_L          bundle=control
#pragma HLS INTERFACE mode=s_axilite port=i_ref        bundle=control
#pragma HLS INTERFACE mode=s_axilite port=V_in         bundle=control
#pragma HLS INTERFACE mode=s_axilite port=Ts           bundle=control
#pragma HLS INTERFACE mode=s_axilite port=L_in         bundle=control
#pragma HLS INTERFACE mode=s_axilite port=V_o          bundle=control
#pragma HLS INTERFACE mode=s_axilite port=theta_pll    bundle=control
#pragma HLS INTERFACE mode=s_axilite port=A3           bundle=control
#pragma HLS INTERFACE mode=s_axilite port=A5           bundle=control
#pragma HLS INTERFACE mode=s_axilite port=A7           bundle=control
#pragma HLS INTERFACE mode=s_axilite port=phi3         bundle=control
#pragma HLS INTERFACE mode=s_axilite port=phi5         bundle=control
#pragma HLS INTERFACE mode=s_axilite port=phi7         bundle=control
#pragma HLS INTERFACE mode=s_axilite port=use_harmonic bundle=control
#pragma HLS INTERFACE mode=s_axilite port=flags        bundle=control
#pragma HLS INTERFACE mode=s_axilite port=amp_iac      bundle=control
#pragma HLS INTERFACE mode=s_axilite port=mask         bundle=control
#pragma HLS INTERFACE mode=s_axilite port=t_ramp       bundle=control
#pragma HLS INTERFACE mode=s_axilite port=D            bundle=control
#pragma HLS INTERFACE mode=s_axilite port=dbg          bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return       bundle=control
    static float theta_prev = 0.0f;
    static bool theta_initialized = false;
    static float g_vac = 0.0f, g_iac = 0.0f;                  // ramp gains (M7)
    static float pkp = 0.0f, pkn = 0.0f, V_amp = 0.0f, th_prev = 0.0f;   // previous-cycle peak tracker (M2)
    static float hA3 = 0.0f, hA5 = 0.0f, hA7 = 0.0f, hp3 = 0.0f, hp5 = 0.0f, hp7 = 0.0f;   // held phasors (M4)
    static bool holding = false;

    const bool f_vac = (flags & 2u) != 0u, f_iac = (flags & 4u) != 0u;
    const bool m_vac = (mask & 4u) != 0u, m_iac = (mask & 8u) != 0u, m_hold = (mask & 16u) != 0u, m_ramp = (mask & 128u) != 0u;
    float Ts_eff = Ts > 1.0e-9f ? Ts : 1.0e-9f;
    float dg = Ts_eff / (t_ramp > Ts_eff ? t_ramp : Ts_eff);
    // ramp gains: 1 while flagged, linear to 0 over t_ramp after clearing (or 0 at once without M7)
    g_vac = f_vac ? 1.0f : (m_ramp ? (g_vac > dg ? g_vac - dg : 0.0f) : 0.0f);
    g_iac = f_iac ? 1.0f : (m_ramp ? (g_iac > dg ? g_iac - dg : 0.0f) : 0.0f);
    // previous-cycle amplitude of V_in (peak-to-peak / 2: a DC bias cancels), cycle = theta wrap
    if (theta_pll < th_prev - 3.0f) { V_amp = 0.5f * (pkp - pkn); pkp = 0.0f; pkn = 0.0f; }
    th_prev = theta_pll;
    if (V_in > pkp) pkp = V_in;
    if (V_in < pkn) pkn = V_in;
    // M2: PLL-reconstructed feed-forward voltage
    float V_used = V_in;
    if (m_vac && g_vac > 0.0f && V_amp > 50.0f) V_used = V_in + g_vac * (V_amp * hls::sin(theta_pll) - V_in);
    // M3: DC compensation of the predictor current
    float i_used = i_L;
    if (m_iac) i_used = i_L - g_iac * amp_iac * 20.0f;
    // M4: harmonic phasors frozen at their pre-flag value while the Iac chain is flagged (and during the ramp)
    bool hold = m_hold && g_iac > 0.0f;
    if (!hold) { hA3 = A3; hA5 = A5; hA7 = A7; hp3 = phi3; hp5 = phi5; hp7 = phi7; holding = false; }
    else if (!holding) { holding = true; }
    float uA3 = hold ? hA3 : A3, uA5 = hold ? hA5 : A5, uA7 = hold ? hA7 : A7;
    float up3 = hold ? hp3 : phi3, up5 = hold ? hp5 : phi5, up7 = hold ? hp7 : phi7;
    mpcc_core(i_used, i_ref, V_used, Ts, L_in, V_o, theta_pll, uA3, uA5, uA7, up3, up5, up7, use_harmonic,
              theta_prev, theta_initialized, D);
    dbg[0] = g_vac; dbg[1] = g_iac; dbg[2] = V_amp; dbg[3] = hold ? 1.0f : 0.0f; dbg[4] = V_used; dbg[5] = i_used;
}
