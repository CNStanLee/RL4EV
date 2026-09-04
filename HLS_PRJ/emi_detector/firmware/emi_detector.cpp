#include <iostream>

#include "emi_detector.h"
#include "parameters.h"


void emi_detector(
    features_t features[43],
    result_t layer9_out[5]
) {

    // hls-fpga-machine-learning insert IO
    #pragma HLS ARRAY_RESHAPE variable=features complete dim=0
    #pragma HLS ARRAY_PARTITION variable=layer9_out complete dim=0
    #pragma HLS INTERFACE ap_vld port=features,layer9_out 
    #pragma HLS PIPELINE

    // hls-fpga-machine-learning insert load weights
#ifndef __SYNTHESIS__
    static bool loaded_weights = false;
    if (!loaded_weights) {
        nnet::load_weights_from_txt<dense0_weight_t, 2752>(w3, "w3.txt");
        nnet::load_weights_from_txt<dense0_bias_t, 64>(b3, "b3.txt");
        nnet::load_weights_from_txt<dense1_weight_t, 4096>(w6, "w6.txt");
        nnet::load_weights_from_txt<dense1_bias_t, 64>(b6, "b6.txt");
        nnet::load_weights_from_txt<chan_weight_t, 320>(w9, "w9.txt");
        nnet::load_weights_from_txt<chan_bias_t, 5>(b9, "b9.txt");
        loaded_weights = true;    }
#endif
    // ****************************************
    // NETWORK INSTANTIATION
    // ****************************************

    // hls-fpga-machine-learning insert layers

    dense0_t layer3_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer3_out complete dim=0

    dense0_relu_t layer4_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer4_out complete dim=0

    dense1_t layer6_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer6_out complete dim=0

    dense1_relu_t layer7_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer7_out complete dim=0

    nnet::dense<features_t, dense0_t, config3>(features, layer3_out, w3, b3); // dense0

    nnet::relu<dense0_t, dense0_relu_t, relu_config4>(layer3_out, layer4_out); // dense0_relu

    nnet::dense<dense0_relu_t, dense1_t, config6>(layer4_out, layer6_out, w6, b6); // dense1

    nnet::relu<dense1_t, dense1_relu_t, relu_config7>(layer6_out, layer7_out); // dense1_relu

    nnet::dense<dense1_relu_t, result_t, config9>(layer7_out, layer9_out, w9, b9); // chan

}

