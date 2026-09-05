#include <iostream>

#include "harmonic_estimator.h"
#include "parameters.h"


void harmonic_estimator(
    waveform_t waveform[80*1],
    result_t layer34_out[8]
) {

    // hls-fpga-machine-learning insert IO
    #pragma HLS ARRAY_RESHAPE variable=waveform complete dim=0
    #pragma HLS ARRAY_PARTITION variable=layer34_out complete dim=0
    #pragma HLS INTERFACE ap_vld port=waveform,layer34_out 
    // #pragma HLS DATAFLOW  (removed by hls4ml_sweep.py --no-dataflow: sequential layers, no element FIFOs)

    // hls-fpga-machine-learning insert load weights
#ifndef __SYNTHESIS__
    static bool loaded_weights = false;
    if (!loaded_weights) {
        nnet::load_weights_from_txt<bls_input_dense_weight_t, 5120>(w4, "w4.txt");
        nnet::load_weights_from_txt<bls_input_dense_bias_t, 64>(b4, "b4.txt");
        nnet::load_weights_from_txt<bls_block_1_dense_1_weight_t, 4096>(w7, "w7.txt");
        nnet::load_weights_from_txt<bls_block_1_dense_1_bias_t, 64>(b7, "b7.txt");
        nnet::load_weights_from_txt<bls_block_1_dense_2_weight_t, 4096>(w10, "w10.txt");
        nnet::load_weights_from_txt<bls_block_1_dense_2_bias_t, 64>(b10, "b10.txt");
        nnet::load_weights_from_txt<bls_block_2_dense_1_weight_t, 4096>(w16, "w16.txt");
        nnet::load_weights_from_txt<bls_block_2_dense_1_bias_t, 64>(b16, "b16.txt");
        nnet::load_weights_from_txt<bls_block_2_dense_2_weight_t, 4096>(w19, "w19.txt");
        nnet::load_weights_from_txt<bls_block_2_dense_2_bias_t, 64>(b19, "b19.txt");
        nnet::load_weights_from_txt<bls_block_3_dense_1_weight_t, 4096>(w25, "w25.txt");
        nnet::load_weights_from_txt<bls_block_3_dense_1_bias_t, 64>(b25, "b25.txt");
        nnet::load_weights_from_txt<bls_block_3_dense_2_weight_t, 4096>(w28, "w28.txt");
        nnet::load_weights_from_txt<bls_block_3_dense_2_bias_t, 64>(b28, "b28.txt");
        nnet::load_weights_from_txt<complex_phasors_weight_t, 512>(w34, "w34.txt");
        nnet::load_weights_from_txt<complex_phasors_bias_t, 8>(b34, "b34.txt");
        loaded_weights = true;    }
#endif
    // ****************************************
    // NETWORK INSTANTIATION
    // ****************************************

    // hls-fpga-machine-learning insert layers

    auto& layer2_out = waveform;
    bls_input_dense_t layer4_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer4_out complete dim=0

    bls_input_dense_relu_t layer5_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer5_out complete dim=0

    bls_block_1_dense_1_iq_t layer6_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer6_out complete dim=0

    bls_block_1_dense_1_t layer7_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer7_out complete dim=0

    bls_block_1_dense_1_relu_t layer8_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer8_out complete dim=0

    bls_block_1_dense_2_t layer10_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer10_out complete dim=0

    bls_block_1_dense_2_relu_t layer11_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer11_out complete dim=0

    quantizer_t layer12_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer12_out complete dim=0

    bls_block_1_skip_t layer14_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer14_out complete dim=0

    bls_block_2_dense_1_iq_t layer15_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer15_out complete dim=0

    bls_block_2_dense_1_t layer16_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer16_out complete dim=0

    bls_block_2_dense_1_relu_t layer17_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer17_out complete dim=0

    bls_block_2_dense_2_t layer19_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer19_out complete dim=0

    bls_block_2_dense_2_relu_t layer20_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer20_out complete dim=0

    quantizer_2_t layer21_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer21_out complete dim=0

    bls_block_2_skip_t layer23_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer23_out complete dim=0

    bls_block_3_dense_1_iq_t layer24_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer24_out complete dim=0

    bls_block_3_dense_1_t layer25_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer25_out complete dim=0

    bls_block_3_dense_1_relu_t layer26_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer26_out complete dim=0

    bls_block_3_dense_2_t layer28_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer28_out complete dim=0

    bls_block_3_dense_2_relu_t layer29_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer29_out complete dim=0

    quantizer_4_t layer30_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer30_out complete dim=0

    bls_block_3_skip_t layer32_out[64];
    #pragma HLS ARRAY_PARTITION variable=layer32_out complete dim=0

    nnet::dense<waveform_t, bls_input_dense_t, config4>(layer2_out, layer4_out, w4, b4); // bls_input_dense

    nnet::relu<bls_input_dense_t, bls_input_dense_relu_t, relu_config5>(layer4_out, layer5_out); // bls_input_dense_relu

    nnet::bls_block_1_dense_1_iq<bls_input_dense_relu_t, bls_block_1_dense_1_iq_t>(layer5_out, layer6_out); // bls_block_1_dense_1_iq

    nnet::dense<bls_block_1_dense_1_iq_t, bls_block_1_dense_1_t, config7>(layer6_out, layer7_out, w7, b7); // bls_block_1_dense_1

    nnet::relu<bls_block_1_dense_1_t, bls_block_1_dense_1_relu_t, relu_config8>(layer7_out, layer8_out); // bls_block_1_dense_1_relu

    nnet::dense<bls_block_1_dense_1_relu_t, bls_block_1_dense_2_t, config10>(layer8_out, layer10_out, w10, b10); // bls_block_1_dense_2

    nnet::relu<bls_block_1_dense_2_t, bls_block_1_dense_2_relu_t, relu_config11>(layer10_out, layer11_out); // bls_block_1_dense_2_relu

    nnet::quantizer<bls_input_dense_relu_t, quantizer_t>(layer5_out, layer12_out); // quantizer

    nnet::add<quantizer_t, bls_block_1_dense_2_relu_t, bls_block_1_skip_t, config14>(layer12_out, layer11_out, layer14_out); // bls_block_1_skip

    nnet::bls_block_2_dense_1_iq<bls_block_1_skip_t, bls_block_2_dense_1_iq_t>(layer14_out, layer15_out); // bls_block_2_dense_1_iq

    nnet::dense<bls_block_2_dense_1_iq_t, bls_block_2_dense_1_t, config16>(layer15_out, layer16_out, w16, b16); // bls_block_2_dense_1

    nnet::relu<bls_block_2_dense_1_t, bls_block_2_dense_1_relu_t, relu_config17>(layer16_out, layer17_out); // bls_block_2_dense_1_relu

    nnet::dense<bls_block_2_dense_1_relu_t, bls_block_2_dense_2_t, config19>(layer17_out, layer19_out, w19, b19); // bls_block_2_dense_2

    nnet::relu<bls_block_2_dense_2_t, bls_block_2_dense_2_relu_t, relu_config20>(layer19_out, layer20_out); // bls_block_2_dense_2_relu

    nnet::quantizer_2<bls_block_1_skip_t, quantizer_2_t>(layer14_out, layer21_out); // quantizer_2

    nnet::add<quantizer_2_t, bls_block_2_dense_2_relu_t, bls_block_2_skip_t, config23>(layer21_out, layer20_out, layer23_out); // bls_block_2_skip

    nnet::bls_block_3_dense_1_iq<bls_block_2_skip_t, bls_block_3_dense_1_iq_t>(layer23_out, layer24_out); // bls_block_3_dense_1_iq

    nnet::dense<bls_block_3_dense_1_iq_t, bls_block_3_dense_1_t, config25>(layer24_out, layer25_out, w25, b25); // bls_block_3_dense_1

    nnet::relu<bls_block_3_dense_1_t, bls_block_3_dense_1_relu_t, relu_config26>(layer25_out, layer26_out); // bls_block_3_dense_1_relu

    nnet::dense<bls_block_3_dense_1_relu_t, bls_block_3_dense_2_t, config28>(layer26_out, layer28_out, w28, b28); // bls_block_3_dense_2

    nnet::relu<bls_block_3_dense_2_t, bls_block_3_dense_2_relu_t, relu_config29>(layer28_out, layer29_out); // bls_block_3_dense_2_relu

    nnet::quantizer_4<bls_block_2_skip_t, quantizer_4_t>(layer23_out, layer30_out); // quantizer_4

    nnet::add<quantizer_4_t, bls_block_3_dense_2_relu_t, bls_block_3_skip_t, config32>(layer30_out, layer29_out, layer32_out); // bls_block_3_skip

    nnet::dense<bls_block_3_skip_t, result_t, config34>(layer32_out, layer34_out, w34, b34); // complex_phasors

}

