#ifndef PARAMETERS_H_
#define PARAMETERS_H_

#include "ap_fixed.h"
#include "ap_int.h"

#include "nnet_utils/nnet_code_gen.h"
#include "nnet_utils/nnet_helpers.h"
// hls-fpga-machine-learning insert includes
#include "nnet_utils/nnet_activation.h"
#include "nnet_utils/nnet_activation_stream.h"
#include "nnet_utils/nnet_dense.h"
#include "nnet_utils/nnet_dense_compressed.h"
#include "nnet_utils/nnet_dense_stream.h"
#include "nnet_utils/nnet_merge.h"
#include "nnet_utils/nnet_merge_stream.h"

// hls-fpga-machine-learning insert weights
#include "weights/w4.h"
#include "weights/b4.h"
#include "weights/w7.h"
#include "weights/b7.h"
#include "weights/w10.h"
#include "weights/b10.h"
#include "weights/w16.h"
#include "weights/b16.h"
#include "weights/w19.h"
#include "weights/b19.h"
#include "weights/w25.h"
#include "weights/b25.h"
#include "weights/w28.h"
#include "weights/b28.h"
#include "weights/w34.h"
#include "weights/b34.h"


// hls-fpga-machine-learning insert layer-config
// bls_input_dense
struct config4 : nnet::dense_config {
    static const unsigned n_in = 80;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 80;
    static const unsigned n_zeros = 193;
    static const unsigned n_nonzeros = 4927;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_input_dense_accum_t accum_t;
    typedef bls_input_dense_bias_t bias_t;
    typedef bls_input_dense_weight_t weight_t;
    typedef layer4_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_input_dense_relu
struct relu_config5 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 262144;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_input_dense_relu_table_t table_t;
};

// bls_block_1_dense_1
struct config7 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 138;
    static const unsigned n_nonzeros = 3958;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_block_1_dense_1_accum_t accum_t;
    typedef bls_block_1_dense_1_bias_t bias_t;
    typedef bls_block_1_dense_1_weight_t weight_t;
    typedef layer7_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_block_1_dense_1_relu
struct relu_config8 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 131072;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_block_1_dense_1_relu_table_t table_t;
};

// bls_block_1_dense_2
struct config10 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 136;
    static const unsigned n_nonzeros = 3960;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_block_1_dense_2_accum_t accum_t;
    typedef bls_block_1_dense_2_bias_t bias_t;
    typedef bls_block_1_dense_2_weight_t weight_t;
    typedef layer10_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_block_1_dense_2_relu
struct relu_config11 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 131072;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_block_1_dense_2_relu_table_t table_t;
};

// bls_block_1_skip
struct config14 : nnet::merge_config {
    static const unsigned n_elem = 64;
    static const unsigned n_elem1 = 64;
    static const unsigned n_elem2 = 64;
    static const unsigned reuse_factor = 1;
};

// bls_block_2_dense_1
struct config16 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 144;
    static const unsigned n_nonzeros = 3952;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_block_2_dense_1_accum_t accum_t;
    typedef bls_block_2_dense_1_bias_t bias_t;
    typedef bls_block_2_dense_1_weight_t weight_t;
    typedef layer16_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_block_2_dense_1_relu
struct relu_config17 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 131072;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_block_2_dense_1_relu_table_t table_t;
};

// bls_block_2_dense_2
struct config19 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 139;
    static const unsigned n_nonzeros = 3957;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_block_2_dense_2_accum_t accum_t;
    typedef bls_block_2_dense_2_bias_t bias_t;
    typedef bls_block_2_dense_2_weight_t weight_t;
    typedef layer19_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_block_2_dense_2_relu
struct relu_config20 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 131072;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_block_2_dense_2_relu_table_t table_t;
};

// bls_block_2_skip
struct config23 : nnet::merge_config {
    static const unsigned n_elem = 64;
    static const unsigned n_elem1 = 64;
    static const unsigned n_elem2 = 64;
    static const unsigned reuse_factor = 1;
};

// bls_block_3_dense_1
struct config25 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 144;
    static const unsigned n_nonzeros = 3952;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_block_3_dense_1_accum_t accum_t;
    typedef bls_block_3_dense_1_bias_t bias_t;
    typedef bls_block_3_dense_1_weight_t weight_t;
    typedef layer25_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_block_3_dense_1_relu
struct relu_config26 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 131072;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_block_3_dense_1_relu_table_t table_t;
};

// bls_block_3_dense_2
struct config28 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 64;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 158;
    static const unsigned n_nonzeros = 3938;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef bls_block_3_dense_2_accum_t accum_t;
    typedef bls_block_3_dense_2_bias_t bias_t;
    typedef bls_block_3_dense_2_weight_t weight_t;
    typedef layer28_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};

// bls_block_3_dense_2_relu
struct relu_config29 : nnet::activ_config {
    static const unsigned n_in = 64;
    static const unsigned table_size = 131072;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned reuse_factor = 64;
    typedef bls_block_3_dense_2_relu_table_t table_t;
};

// bls_block_3_skip
struct config32 : nnet::merge_config {
    static const unsigned n_elem = 64;
    static const unsigned n_elem1 = 64;
    static const unsigned n_elem2 = 64;
    static const unsigned reuse_factor = 1;
};

// complex_phasors
struct config34 : nnet::dense_config {
    static const unsigned n_in = 64;
    static const unsigned n_out = 8;
    static const unsigned io_type = nnet::io_parallel;
    static const unsigned strategy = nnet::resource;
    static const unsigned reuse_factor = 64;
    static const unsigned n_zeros = 118;
    static const unsigned n_nonzeros = 394;
    static const unsigned multiplier_limit = DIV_ROUNDUP(n_in * n_out, reuse_factor) - n_zeros / reuse_factor;
    static const bool store_weights_in_bram = false;
    typedef complex_phasors_accum_t accum_t;
    typedef complex_phasors_bias_t bias_t;
    typedef complex_phasors_weight_t weight_t;
    typedef layer34_index index_t;
    template<class data_T, class res_T, class CONFIG_T>
    using kernel = nnet::DenseResource_rf_leq_nin<data_T, res_T, CONFIG_T>;
    template<class x_T, class y_T>
    using product = nnet::product::mult<x_T, y_T>;
};



#endif
