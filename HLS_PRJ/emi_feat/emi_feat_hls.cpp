#include "emi_feat_hls.h"
#include <hls_math.h>

// cos / sin tables for the Goertzel-style projections at k = 1, 2, 3 cycles per window (n = 200)
#include "trig_tables.h"

static float fmaxf_(float a, float b) { return a > b ? a : b; }
static float fminf_(float a, float b) { return a < b ? a : b; }
static float fabsf_(float a) { return a >= 0.0f ? a : -a; }

void emi_feat_hls(const float buf[EF_N * EF_C], unsigned int reset, float feat[EF_NF]) {
#pragma HLS INTERFACE mode=s_axilite port=buf   bundle=control
#pragma HLS INTERFACE mode=s_axilite port=reset bundle=control
#pragma HLS INTERFACE mode=s_axilite port=feat  bundle=control
#pragma HLS INTERFACE mode=s_axilite port=return bundle=control
    static float prev[36];
    static bool have_prev = false;
    if (reset) have_prev = false;

    // ---- pass 1: sums, extrema, projections (one pipelined loop over the 200 samples)
    float s_vac = 0, s_iac = 0, s_iac2 = 0, s_vdc = 0, s_vr = 0, s_iref = 0, s_d = 0, s_dff = 0;
    float s_vbat = 0, s_ibat = 0, s_ddc = 0, s_st = 0, s_irb = 0, s_pac = 0, s_pchg = 0, s_negiref = 0;
    float vac_c1 = 0, vac_s1 = 0, iac_c1 = 0, iac_s1 = 0, iac_c2 = 0, iac_s2 = 0, iac_c3 = 0, iac_s3 = 0;
    float vdc_c1 = 0, vdc_s1 = 0, vdc_c2 = 0, vdc_s2 = 0;
    float iac_max = -1e30f, iac_min = 1e30f, vdc_max = -1e30f, vdc_min = 1e30f, iref_min = 1e30f, iref_max = -1e30f;
    float vbat_max = -1e30f, vbat_min = 1e30f, ibat_max = -1e30f, ibat_min = 1e30f;
    float s_ref = 0, s_ref2 = 0, s_iacref = 0, s_abserr2 = 0;
    float d_pos = 0, d_neg = 0; int n_pos = 0, n_neg = 0;
P1: for (int i = 0; i < EF_N; ++i) {
#pragma HLS PIPELINE II=1
        const float *r = buf + i * EF_C;
        float vdc = r[0], vac = r[1], iac = r[2], iref = r[3], th = r[4], d = r[5], vr = r[6];
        float vbat = r[7], ibat = r[8], ddc = r[9], st = r[10], irb = r[11];
        float sth = hls::sinf(th);
        float ref = iref * fabsf_(sth) * (sth > 0 ? 1.0f : (sth < 0 ? -1.0f : 0.0f));   // signed reference shape
        s_vac += vac; s_iac += iac; s_iac2 += iac * iac; s_vdc += vdc; s_vr += vr; s_iref += iref; s_d += d;
        s_dff += 1.0f - fabsf_(vac) / fmaxf_(vdc, 50.0f);
        s_vbat += vbat; s_ibat += ibat; s_ddc += ddc; s_st += st; s_irb += irb;
        s_pac += vac * iac; s_pchg += vbat * ibat; s_negiref += (iref < 0) ? 1.0f : 0.0f;
        vac_c1 += vac * COS1[i]; vac_s1 += vac * SIN1[i];
        iac_c1 += iac * COS1[i]; iac_s1 += iac * SIN1[i]; iac_c2 += iac * COS2[i]; iac_s2 += iac * SIN2[i]; iac_c3 += iac * COS3[i]; iac_s3 += iac * SIN3[i];
        vdc_c1 += vdc * COS1[i]; vdc_s1 += vdc * SIN1[i]; vdc_c2 += vdc * COS2[i]; vdc_s2 += vdc * SIN2[i];
        iac_max = fmaxf_(iac_max, iac); iac_min = fminf_(iac_min, iac); vdc_max = fmaxf_(vdc_max, vdc); vdc_min = fminf_(vdc_min, vdc);
        iref_min = fminf_(iref_min, iref); iref_max = fmaxf_(iref_max, iref);
        vbat_max = fmaxf_(vbat_max, vbat); vbat_min = fminf_(vbat_min, vbat); ibat_max = fmaxf_(ibat_max, ibat); ibat_min = fminf_(ibat_min, ibat);
        s_ref += ref; s_ref2 += ref * ref; s_iacref += iac * ref;
        float ae = fabsf_(iac) - fabsf_(ref); s_abserr2 += ae * ae;
        if (sth > 0) { d_pos += d; ++n_pos; } else if (sth < 0) { d_neg += d; ++n_neg; }
    }
    const float n = (float)EF_N, inv_n = 1.0f / n, two_n = 2.0f / n;
    float vac_mean = s_vac * inv_n, iac_mean = s_iac * inv_n, vdc_mean = s_vdc * inv_n;
    float vac_amp = two_n * hls::hypotf(vac_c1, vac_s1);
    float h1 = two_n * hls::hypotf(iac_c1, iac_s1), h2 = two_n * hls::hypotf(iac_c2, iac_s2), h3 = two_n * hls::hypotf(iac_c3, iac_s3);
    float iac_rms = hls::sqrtf(s_iac2 * inv_n);
    // Pearson correlation between iac and ref (population statistics, as np.corrcoef)
    float ref_mean = s_ref * inv_n;
    float var_i = s_iac2 * inv_n - iac_mean * iac_mean, var_r = s_ref2 * inv_n - ref_mean * ref_mean;
    float cov = s_iacref * inv_n - iac_mean * ref_mean;
    float cc = 0.0f;
    if (var_r > 1e-12f && var_i > 1e-12f) cc = cov / hls::sqrtf(var_i * var_r);
    float ref_err = hls::sqrtf(s_abserr2 * inv_n) / fmaxf_(iac_rms, 1e-3f);
    float ph_i = hls::atan2f(-iac_s1, iac_c1), ph_v = hls::atan2f(-vac_s1, vac_c1);
    float dphi = ph_i - ph_v; dphi = hls::atan2f(hls::sinf(dphi), hls::cosf(dphi));
    float vdc_rip = vdc_max - vdc_min, vdc_err = vdc_mean - s_vr * inv_n;
    float p_ac = s_pac * inv_n, p_chg = s_pchg * inv_n, p_ratio = p_chg / fmaxf_(p_ac, 50.0f);
    float vbm = s_vbat * inv_n, ddm = s_ddc * inv_n;
    float row[36];
#pragma HLS ARRAY_PARTITION variable=row complete
    row[0] = vac_mean; row[1] = vac_amp; row[2] = vac_mean / fmaxf_(vac_amp, 1.0f);
    row[3] = iac_mean; row[4] = iac_rms; row[5] = iac_max; row[6] = iac_min; row[7] = iac_max + iac_min;
    row[8] = h2 / fmaxf_(h1, 1e-3f); row[9] = h3 / fmaxf_(h1, 1e-3f); row[10] = h1;
    row[11] = cc; row[12] = ref_err; row[13] = iac_mean / fmaxf_(h1, 1e-3f); row[14] = dphi;
    row[15] = vdc_mean; row[16] = vdc_rip; row[17] = vdc_err;
    row[18] = s_iref * inv_n; row[19] = iref_min; row[20] = iref_max; row[21] = s_negiref * inv_n; row[22] = s_d * inv_n; row[23] = (s_d - s_dff) * inv_n;
    row[24] = vbm; row[25] = s_ibat * inv_n; row[26] = ddm; row[27] = s_st * inv_n; row[28] = s_irb * inv_n; row[29] = vbat_max - vbat_min; row[30] = ibat_max - ibat_min;
    row[31] = p_ac; row[32] = p_chg; row[33] = p_ratio;
    row[34] = ddm * vdc_mean / fmaxf_(vbm, 50.0f) - 1.0f; row[35] = vbm - ddm * vdc_mean;
    float dl[7];
    if (!have_prev) {
        for (int k = 0; k < 7; ++k) dl[k] = 0.0f;
    } else {
        dl[0] = row[15] - prev[15]; dl[1] = row[18] - prev[18]; dl[2] = row[4] - prev[4]; dl[3] = row[3] - prev[3];
        dl[4] = row[24] - prev[24]; dl[5] = row[25] - prev[25]; dl[6] = row[33] - prev[33];
    }
    for (int k = 0; k < 36; ++k) prev[k] = row[k];
    have_prev = true;
    // v3 extras: bus 50 Hz ripple, its ratio to the 100 Hz ripple, its phase vs Vac, duty half-cycle asymmetry, pad
    float vh1 = two_n * hls::hypotf(vdc_c1, vdc_s1), vh2 = two_n * hls::hypotf(vdc_c2, vdc_s2);
    float vph = hls::atan2f(-vdc_s1, vdc_c1) - ph_v; vph = hls::atan2f(hls::sinf(vph), hls::cosf(vph));
    float dp = n_pos ? d_pos / (float)n_pos : 0.0f, dn = n_neg ? d_neg / (float)n_neg : 0.0f;
    for (int k = 0; k < 36; ++k) feat[k] = row[k];
    for (int k = 0; k < 7; ++k) feat[36 + k] = dl[k];
    feat[43] = vh1; feat[44] = vh1 / fmaxf_(vh2, 0.1f); feat[45] = vph; feat[46] = dp - dn; feat[47] = 0.0f;
}
