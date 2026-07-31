#include "mpcc_hls.h"
#include <hls_math.h>

static float abs_float(float x)
{
    return x >= 0.0f ? x : -x;
}

void mpcc_hls(
    float i_L,
    float i_ref,
    float V_in,
    float Ts,
    float L_in,
    float V_o,
    float theta_pll,
    float A3,
    float A5,
    float A7,
    float phi3,
    float phi5,
    float phi7,
    bool use_harmonic,
    float *D
)
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
#pragma HLS INTERFACE mode=s_axilite port=D             bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return        bundle=control

    static float theta_prev = 0.0f;
    static bool theta_initialized = false;

    if (!theta_initialized) {
        theta_prev = theta_pll;
        theta_initialized = true;
    }

    const float track_gain = 0.35f;
    const float damp_gain  = 0.015f;
    const float lead_steps = 1.0f;

    float L = L_in > 1.0e-9f ? L_in : 1.0e-9f;
    float Ts_eff = Ts > 1.0e-9f ? Ts : 1.0e-9f;

    float abs_Vo = abs_float(V_o);
    float Vo = abs_Vo > 1.0f ? abs_Vo : 1.0f;

    float ui_L = abs_float(i_L);

    /*
     * Prevent division by zero near the AC current zero crossing.
     */
    float ui_L_safe = ui_L > 1.0e-6f ? ui_L : 1.0e-6f;

    float line_sign;

    if (V_in > 0.0f) {
        line_sign = 1.0f;
    } else {
        line_sign = -1.0f;
    }

    float i_ref_signed = line_sign * abs_float(i_ref);

    float plant_gain =
        line_sign * L / (Vo * Ts_eff);

    float D_ff =
        1.0f - abs_float(V_in) / Vo;

    if (use_harmonic) {
        float theta_delta =
            theta_pll - theta_prev;

        float dtheta = hls::atan2(
            hls::sin(theta_delta),
            hls::cos(theta_delta)
        );

        theta_prev = theta_pll;

        float omega_inst =
            dtheta / Ts_eff;

        float theta_ctrl =
            theta_pll
            + omega_inst * Ts_eff * lead_steps;

        float A3_abs = abs_float(A3);
        float A5_abs = abs_float(A5);
        float A7_abs = abs_float(A7);

        const float phase_sign = 1.0f;

        float ih3 = A3_abs * hls::sin(
            3.0f * theta_ctrl + phase_sign * phi3
        );

        float ih5 = A5_abs * hls::sin(
            5.0f * theta_ctrl + phase_sign * phi5
        );

        float ih7 = A7_abs * hls::sin(
            7.0f * theta_ctrl + phase_sign * phi7
        );

        const float k3 = 1.00f;
        const float k5 = 1.08f;
        const float k7 = 1.00f;

        float ih_357 =
            k3 * ih3
            + k5 * ih5
            + k7 * ih7;

        i_ref_signed =
            i_ref_signed - ih_357;
    }

    float i_err =
        i_ref_signed - i_L;

    float D_corr =
        plant_gain * track_gain * i_err;

    float D_damp =
        -line_sign
        * damp_gain
        * (i_L - i_ref_signed)
        / ui_L_safe;

    float D_result =
        D_ff + D_corr + D_damp;

    *D = D_result;
}