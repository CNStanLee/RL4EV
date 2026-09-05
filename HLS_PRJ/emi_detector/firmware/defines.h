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
typedef ap_fixed<12,5,AP_RND,AP_SAT,0> features_t;
typedef ap_fixed<23,9> dense0_accum_t;
typedef ap_fixed<17,9> dense0_t;
typedef ap_fixed<9,2> dense0_weight_t;
typedef ap_fixed<15,1> dense0_bias_t;
typedef ap_uint<1> layer3_index;
typedef ap_ufixed<11,4,AP_RND,AP_SAT,0> dense0_relu_t;
typedef ap_fixed<18,8> dense0_relu_table_t;
typedef ap_fixed<25,9> dense1_accum_t;
typedef ap_fixed<17,9> dense1_t;
typedef ap_fixed<9,2> dense1_weight_t;
typedef ap_fixed<16,0> dense1_bias_t;
typedef ap_uint<1> layer6_index;
typedef ap_ufixed<11,4,AP_RND,AP_SAT,0> dense1_relu_t;
typedef ap_fixed<18,8> dense1_relu_table_t;
typedef ap_fixed<25,10> head_accum_t;
typedef ap_fixed<25,10> result_t;
typedef ap_fixed<10,3> head_weight_t;
typedef ap_fixed<15,0> head_bias_t;
typedef ap_uint<1> layer9_index;

// hls-fpga-machine-learning insert emulator-defines


#endif
