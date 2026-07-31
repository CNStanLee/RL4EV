#include <cmath>
#include <iostream>
#include "mpcc_hls.h"

static float abs_sw(float x)
{
    return x >= 0.0f ? x : -x;
}

static void mpcc_reference(
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

    float abs_Vo = abs_sw(V_o);
    float Vo = abs_Vo > 1.0f ? abs_Vo : 1.0f;

    float ui_L = abs_sw(i_L);
    float ui_L_safe = ui_L > 1.0e-6f ? ui_L : 1.0e-6f;

    float line_sign =
        V_in > 0.0f ? 1.0f : -1.0f;

    float i_ref_signed =
        line_sign * abs_sw(i_ref);

    float plant_gain =
        line_sign * L / (Vo * Ts_eff);

    float D_ff =
        1.0f - abs_sw(V_in) / Vo;

    if (use_harmonic) {
        float theta_delta =
            theta_pll - theta_prev;

        float dtheta = std::atan2(
            std::sin(theta_delta),
            std::cos(theta_delta)
        );

        theta_prev = theta_pll;

        float omega_inst =
            dtheta / Ts_eff;

        float theta_ctrl =
            theta_pll
            + omega_inst * Ts_eff * lead_steps;

        float ih3 =
            abs_sw(A3) * std::sin(3.0f * theta_ctrl + phi3);

        float ih5 =
            abs_sw(A5) * std::sin(5.0f * theta_ctrl + phi5);

        float ih7 =
            abs_sw(A7) * std::sin(7.0f * theta_ctrl + phi7);

        float ih_357 =
            ih3 + 1.08f * ih5 + ih7;

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

    *D = D_ff + D_corr + D_damp;
}

int main()
{
    const float PI = 3.14159265358979323846f;

    const float Ts = 50.0e-6f;
    const float L  = 600.0e-6f;
    const float Vo = 400.0f;

    const float A3 = 0.60f;
    const float A5 = 0.30f;
    const float A7 = 0.20f;

    const float phi3 = 0.10f;
    const float phi5 = -0.15f;
    const float phi7 = 0.20f;

    int errors = 0;
    int out_of_range = 0;
    float max_error = 0.0f;

    for (int n = 0; n < 400; n++) {
        float t =
            static_cast<float>(n) * Ts;

        float theta =
            2.0f * PI * 50.0f * t;

        float V_in =
            325.0f * std::sin(theta);

        float i_ref =
            10.0f * std::sin(theta);

        float i_L =
            9.5f * std::sin(theta - 0.01f);

        bool use_harmonic =
            n >= 20;

        float D_hls = 0.0f;
        float D_ref = 0.0f;

        mpcc_hls(
            i_L,
            i_ref,
            V_in,
            Ts,
            L,
            Vo,
            theta,
            A3,
            A5,
            A7,
            phi3,
            phi5,
            phi7,
            use_harmonic,
            &D_hls
        );

        mpcc_reference(
            i_L,
            i_ref,
            V_in,
            Ts,
            L,
            Vo,
            theta,
            A3,
            A5,
            A7,
            phi3,
            phi5,
            phi7,
            use_harmonic,
            &D_ref
        );

        float error =
            abs_sw(D_hls - D_ref);

        if (error > max_error) {
            max_error = error;
        }

        if (!std::isfinite(D_hls)) {
            std::cout
                << "Non-finite output at n="
                << n << "\n";

            errors++;
        }

        if (error > 1.0e-4f) {
            std::cout
                << "Mismatch at n=" << n
                << " HLS=" << D_hls
                << " REF=" << D_ref
                << " ERROR=" << error
                << "\n";

            errors++;
        }

        if (D_hls < 0.0f || D_hls > 1.0f) {
            out_of_range++;
        }

        if ((n % 40) == 0) {
            std::cout
                << "n=" << n
                << " harmonic=" << use_harmonic
                << " theta=" << theta
                << " D_hls=" << D_hls
                << " D_ref=" << D_ref
                << "\n";
        }
    }

    std::cout
        << "Maximum numerical error: "
        << max_error << "\n";

    std::cout
        << "Outputs outside [0,1]: "
        << out_of_range << "\n";

    if (errors == 0) {
        std::cout << "MPCC C SIMULATION PASSED\n";
        return 0;
    }

    std::cout
        << "MPCC C SIMULATION FAILED, errors="
        << errors << "\n";

    return 1;
}