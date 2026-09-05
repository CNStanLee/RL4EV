#ifndef DEFINES_H_
#define DEFINES_H_

#include "ap_fixed.h"
#include "ap_int.h"
#include "nnet_utils/nnet_types.h"
#include <array>
#include <cstddef>
#include <cstdio>
#include <tuple>
#include <tuple>


// hls-fpga-machine-learning insert numbers

// hls-fpga-machine-learning insert layer-precision
typedef ap_fixed<8,3,AP_RND,AP_SAT,0> waveform_t;
typedef ap_fixed<18,7> bls_input_dense_accum_t;
typedef ap_fixed<13,7> bls_input_dense_t;
typedef ap_fixed<7,1> bls_input_dense_weight_t;
typedef ap_fixed<7,1> bls_input_dense_bias_t;
typedef ap_uint<1> layer4_index;
typedef ap_ufixed<12,6> bls_input_dense_relu_t;
typedef ap_fixed<18,8> bls_input_dense_relu_table_t;
typedef ap_ufixed<7,2> bls_block_1_dense_1_iq_t;
typedef ap_fixed<17,6> bls_block_1_dense_1_accum_t;
typedef ap_fixed<12,6> bls_block_1_dense_1_t;
typedef ap_fixed<7,1> bls_block_1_dense_1_weight_t;
typedef ap_fixed<7,1> bls_block_1_dense_1_bias_t;
typedef ap_uint<1> layer7_index;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_1_dense_1_relu_t;
typedef ap_fixed<18,8> bls_block_1_dense_1_relu_table_t;
typedef ap_fixed<17,6> bls_block_1_dense_2_accum_t;
typedef ap_fixed<12,6> bls_block_1_dense_2_t;
typedef ap_fixed<7,1> bls_block_1_dense_2_weight_t;
typedef ap_fixed<7,1> bls_block_1_dense_2_bias_t;
typedef ap_uint<1> layer10_index;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_1_dense_2_relu_t;
typedef ap_fixed<18,8> bls_block_1_dense_2_relu_table_t;
typedef ap_ufixed<7,2> quantizer_t;
typedef ap_ufixed<8,3> bls_block_1_skip_t;
typedef ap_ufixed<7,2> bls_block_2_dense_1_iq_t;
typedef ap_fixed<17,6> bls_block_2_dense_1_accum_t;
typedef ap_fixed<12,6> bls_block_2_dense_1_t;
typedef ap_fixed<7,1> bls_block_2_dense_1_weight_t;
typedef ap_fixed<7,1> bls_block_2_dense_1_bias_t;
typedef ap_uint<1> layer16_index;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_2_dense_1_relu_t;
typedef ap_fixed<18,8> bls_block_2_dense_1_relu_table_t;
typedef ap_fixed<17,6> bls_block_2_dense_2_accum_t;
typedef ap_fixed<12,6> bls_block_2_dense_2_t;
typedef ap_fixed<7,1> bls_block_2_dense_2_weight_t;
typedef ap_fixed<7,1> bls_block_2_dense_2_bias_t;
typedef ap_uint<1> layer19_index;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_2_dense_2_relu_t;
typedef ap_fixed<18,8> bls_block_2_dense_2_relu_table_t;
typedef ap_ufixed<7,2> quantizer_2_t;
typedef ap_ufixed<8,3> bls_block_2_skip_t;
typedef ap_ufixed<7,2> bls_block_3_dense_1_iq_t;
typedef ap_fixed<17,6> bls_block_3_dense_1_accum_t;
typedef ap_fixed<12,6> bls_block_3_dense_1_t;
typedef ap_fixed<7,1> bls_block_3_dense_1_weight_t;
typedef ap_fixed<7,1> bls_block_3_dense_1_bias_t;
typedef ap_uint<1> layer25_index;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_3_dense_1_relu_t;
typedef ap_fixed<18,8> bls_block_3_dense_1_relu_table_t;
typedef ap_fixed<17,6> bls_block_3_dense_2_accum_t;
typedef ap_fixed<12,6> bls_block_3_dense_2_t;
typedef ap_fixed<7,1> bls_block_3_dense_2_weight_t;
typedef ap_fixed<7,1> bls_block_3_dense_2_bias_t;
typedef ap_uint<1> layer28_index;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_3_dense_2_relu_t;
typedef ap_fixed<18,8> bls_block_3_dense_2_relu_table_t;
typedef ap_ufixed<7,2> quantizer_4_t;
typedef ap_ufixed<7,2,AP_RND,AP_SAT,0> bls_block_3_skip_t;
typedef ap_fixed<15,4> complex_phasors_accum_t;
typedef ap_fixed<8,3,AP_RND,AP_SAT,0> result_t;
typedef ap_fixed<7,1> complex_phasors_weight_t;
typedef ap_fixed<7,1> complex_phasors_bias_t;
typedef ap_uint<1> layer34_index;

// hls-fpga-machine-learning insert emulator-defines


#endif
