#ifndef NNET_INSTR_GEN_H_
#define NNET_INSTR_GEN_H_

#include "nnet_conv1d_latency.h"
#include "nnet_helpers.h"

#include "hls_stream.h"
#include "nnet_common.h"
#include "nnet_function_stubs.h"
#include "nnet_mult.h"

namespace nnet {

template <class data_T, class res_T, typename CONFIG_T> class PointwiseConv1D {
  public:
    static void pointwise_conv(data_T data[CONFIG_T::in_width * CONFIG_T::n_chan],
                               res_T res[CONFIG_T::out_width * CONFIG_T::n_filt],
                               typename CONFIG_T::weight_t weights[CONFIG_T::n_chan * CONFIG_T::n_filt],
                               typename CONFIG_T::bias_t biases[CONFIG_T::n_filt]) {
        // To be implemented in subclasses
    }
};

// hls4ml insert code

template<typename input_t, typename output_t>
void bls_block_1_dense_1_iq(input_t *inp, output_t *out) {
    #pragma HLS INLINE

    out[0] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[0]);
    out[1] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[1]);
    out[2] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[2]);
    out[3] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[3]);
    out[4] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[4]);
    out[5] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[5]);
    out[6] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[6]);
    out[7] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[7]);
    out[8] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[8]);
    out[9] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[9]);
    out[10] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[10]);
    out[11] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[11]);
    out[12] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[12]);
    out[13] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[13]);
    out[14] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[14]);
    out[15] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[15]);
    out[16] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[16]);
    out[17] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[17]);
    out[18] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[18]);
    out[19] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[19]);
    out[20] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[20]);
    out[21] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[21]);
    out[22] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[22]);
    out[23] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[23]);
    out[24] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[24]);
    out[25] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[25]);
    out[26] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[26]);
    out[27] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[27]);
    out[28] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[28]);
    out[29] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[29]);
    out[30] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[30]);
    out[31] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[31]);
    out[32] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[32]);
    out[33] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[33]);
    out[34] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[34]);
    out[35] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[35]);
    out[36] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[36]);
    out[37] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[37]);
    out[38] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[38]);
    out[39] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[39]);
    out[40] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[40]);
    out[41] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[41]);
    out[42] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[42]);
    out[43] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[43]);
    out[44] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[44]);
    out[45] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[45]);
    out[46] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[46]);
    out[47] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[47]);
    out[48] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[48]);
    out[49] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[49]);
    out[50] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[50]);
    out[51] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[51]);
    out[52] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[52]);
    out[53] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[53]);
    out[54] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[54]);
    out[55] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[55]);
    out[56] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[56]);
    out[57] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[57]);
    out[58] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[58]);
    out[59] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[59]);
    out[60] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[60]);
    out[61] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[61]);
    out[62] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[62]);
    out[63] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[63]);
}

template<typename input_t, typename output_t>
void quantizer(input_t *inp, output_t *out) {
    #pragma HLS INLINE

    out[0] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[0]);
    out[1] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[1]);
    out[2] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[2]);
    out[3] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[3]);
    out[4] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[4]);
    out[5] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[5]);
    out[6] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[6]);
    out[7] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[7]);
    out[8] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[8]);
    out[9] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[9]);
    out[10] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[10]);
    out[11] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[11]);
    out[12] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[12]);
    out[13] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[13]);
    out[14] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[14]);
    out[15] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[15]);
    out[16] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[16]);
    out[17] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[17]);
    out[18] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[18]);
    out[19] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[19]);
    out[20] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[20]);
    out[21] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[21]);
    out[22] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[22]);
    out[23] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[23]);
    out[24] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[24]);
    out[25] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[25]);
    out[26] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[26]);
    out[27] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[27]);
    out[28] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[28]);
    out[29] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[29]);
    out[30] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[30]);
    out[31] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[31]);
    out[32] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[32]);
    out[33] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[33]);
    out[34] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[34]);
    out[35] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[35]);
    out[36] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[36]);
    out[37] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[37]);
    out[38] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[38]);
    out[39] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[39]);
    out[40] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[40]);
    out[41] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[41]);
    out[42] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[42]);
    out[43] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[43]);
    out[44] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[44]);
    out[45] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[45]);
    out[46] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[46]);
    out[47] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[47]);
    out[48] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[48]);
    out[49] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[49]);
    out[50] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[50]);
    out[51] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[51]);
    out[52] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[52]);
    out[53] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[53]);
    out[54] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[54]);
    out[55] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[55]);
    out[56] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[56]);
    out[57] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[57]);
    out[58] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[58]);
    out[59] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[59]);
    out[60] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[60]);
    out[61] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[61]);
    out[62] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[62]);
    out[63] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[63]);
}

template<typename input_t, typename output_t>
void bls_block_2_dense_1_iq(input_t *inp, output_t *out) {
    #pragma HLS INLINE

    out[0] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[0]);
    out[1] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[1]);
    out[2] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[2]);
    out[3] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[3]);
    out[4] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[4]);
    out[5] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[5]);
    out[6] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[6]);
    out[7] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[7]);
    out[8] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[8]);
    out[9] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[9]);
    out[10] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[10]);
    out[11] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[11]);
    out[12] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[12]);
    out[13] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[13]);
    out[14] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[14]);
    out[15] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[15]);
    out[16] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[16]);
    out[17] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[17]);
    out[18] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[18]);
    out[19] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[19]);
    out[20] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[20]);
    out[21] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[21]);
    out[22] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[22]);
    out[23] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[23]);
    out[24] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[24]);
    out[25] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[25]);
    out[26] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[26]);
    out[27] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[27]);
    out[28] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[28]);
    out[29] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[29]);
    out[30] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[30]);
    out[31] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[31]);
    out[32] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[32]);
    out[33] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[33]);
    out[34] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[34]);
    out[35] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[35]);
    out[36] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[36]);
    out[37] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[37]);
    out[38] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[38]);
    out[39] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[39]);
    out[40] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[40]);
    out[41] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[41]);
    out[42] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[42]);
    out[43] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[43]);
    out[44] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[44]);
    out[45] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[45]);
    out[46] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[46]);
    out[47] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[47]);
    out[48] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[48]);
    out[49] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[49]);
    out[50] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[50]);
    out[51] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[51]);
    out[52] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[52]);
    out[53] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[53]);
    out[54] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[54]);
    out[55] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[55]);
    out[56] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[56]);
    out[57] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[57]);
    out[58] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[58]);
    out[59] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[59]);
    out[60] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[60]);
    out[61] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[61]);
    out[62] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[62]);
    out[63] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[63]);
}

template<typename input_t, typename output_t>
void quantizer_2(input_t *inp, output_t *out) {
    #pragma HLS INLINE

    out[0] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[0]);
    out[1] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[1]);
    out[2] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[2]);
    out[3] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[3]);
    out[4] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[4]);
    out[5] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[5]);
    out[6] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[6]);
    out[7] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[7]);
    out[8] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[8]);
    out[9] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[9]);
    out[10] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[10]);
    out[11] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[11]);
    out[12] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[12]);
    out[13] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[13]);
    out[14] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[14]);
    out[15] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[15]);
    out[16] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[16]);
    out[17] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[17]);
    out[18] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[18]);
    out[19] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[19]);
    out[20] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[20]);
    out[21] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[21]);
    out[22] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[22]);
    out[23] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[23]);
    out[24] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[24]);
    out[25] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[25]);
    out[26] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[26]);
    out[27] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[27]);
    out[28] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[28]);
    out[29] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[29]);
    out[30] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[30]);
    out[31] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[31]);
    out[32] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[32]);
    out[33] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[33]);
    out[34] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[34]);
    out[35] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[35]);
    out[36] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[36]);
    out[37] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[37]);
    out[38] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[38]);
    out[39] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[39]);
    out[40] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[40]);
    out[41] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[41]);
    out[42] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[42]);
    out[43] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[43]);
    out[44] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[44]);
    out[45] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[45]);
    out[46] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[46]);
    out[47] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[47]);
    out[48] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[48]);
    out[49] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[49]);
    out[50] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[50]);
    out[51] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[51]);
    out[52] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[52]);
    out[53] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[53]);
    out[54] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[54]);
    out[55] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[55]);
    out[56] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[56]);
    out[57] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[57]);
    out[58] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[58]);
    out[59] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[59]);
    out[60] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[60]);
    out[61] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[61]);
    out[62] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[62]);
    out[63] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[63]);
}

template<typename input_t, typename output_t>
void bls_block_3_dense_1_iq(input_t *inp, output_t *out) {
    #pragma HLS INLINE

    out[0] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[0]);
    out[1] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[1]);
    out[2] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[2]);
    out[3] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[3]);
    out[4] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[4]);
    out[5] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[5]);
    out[6] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[6]);
    out[7] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[7]);
    out[8] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[8]);
    out[9] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[9]);
    out[10] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[10]);
    out[11] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[11]);
    out[12] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[12]);
    out[13] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[13]);
    out[14] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[14]);
    out[15] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[15]);
    out[16] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[16]);
    out[17] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[17]);
    out[18] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[18]);
    out[19] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[19]);
    out[20] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[20]);
    out[21] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[21]);
    out[22] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[22]);
    out[23] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[23]);
    out[24] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[24]);
    out[25] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[25]);
    out[26] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[26]);
    out[27] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[27]);
    out[28] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[28]);
    out[29] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[29]);
    out[30] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[30]);
    out[31] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[31]);
    out[32] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[32]);
    out[33] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[33]);
    out[34] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[34]);
    out[35] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[35]);
    out[36] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[36]);
    out[37] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[37]);
    out[38] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[38]);
    out[39] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[39]);
    out[40] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[40]);
    out[41] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[41]);
    out[42] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[42]);
    out[43] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[43]);
    out[44] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[44]);
    out[45] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[45]);
    out[46] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[46]);
    out[47] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[47]);
    out[48] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[48]);
    out[49] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[49]);
    out[50] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[50]);
    out[51] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[51]);
    out[52] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[52]);
    out[53] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[53]);
    out[54] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[54]);
    out[55] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[55]);
    out[56] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[56]);
    out[57] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[57]);
    out[58] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[58]);
    out[59] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[59]);
    out[60] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[60]);
    out[61] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[61]);
    out[62] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[62]);
    out[63] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[63]);
}

template<typename input_t, typename output_t>
void quantizer_4(input_t *inp, output_t *out) {
    #pragma HLS INLINE

    out[0] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[0]);
    out[1] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[1]);
    out[2] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[2]);
    out[3] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[3]);
    out[4] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[4]);
    out[5] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[5]);
    out[6] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[6]);
    out[7] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[7]);
    out[8] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[8]);
    out[9] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[9]);
    out[10] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[10]);
    out[11] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[11]);
    out[12] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[12]);
    out[13] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[13]);
    out[14] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[14]);
    out[15] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[15]);
    out[16] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[16]);
    out[17] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[17]);
    out[18] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[18]);
    out[19] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[19]);
    out[20] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[20]);
    out[21] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[21]);
    out[22] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[22]);
    out[23] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[23]);
    out[24] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[24]);
    out[25] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[25]);
    out[26] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[26]);
    out[27] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[27]);
    out[28] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[28]);
    out[29] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[29]);
    out[30] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[30]);
    out[31] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[31]);
    out[32] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[32]);
    out[33] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[33]);
    out[34] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[34]);
    out[35] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[35]);
    out[36] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[36]);
    out[37] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[37]);
    out[38] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[38]);
    out[39] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[39]);
    out[40] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[40]);
    out[41] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[41]);
    out[42] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[42]);
    out[43] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[43]);
    out[44] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[44]);
    out[45] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[45]);
    out[46] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[46]);
    out[47] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[47]);
    out[48] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[48]);
    out[49] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[49]);
    out[50] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[50]);
    out[51] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[51]);
    out[52] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[52]);
    out[53] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[53]);
    out[54] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[54]);
    out[55] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[55]);
    out[56] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[56]);
    out[57] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[57]);
    out[58] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[58]);
    out[59] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[59]);
    out[60] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[60]);
    out[61] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[61]);
    out[62] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[62]);
    out[63] = ap_ufixed<7,2,AP_RND,AP_SAT>(inp[63]);
}

} // namespace nnet

#endif
