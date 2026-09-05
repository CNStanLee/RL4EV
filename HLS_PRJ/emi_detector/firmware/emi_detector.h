#ifndef EMI_DETECTOR_H_
#define EMI_DETECTOR_H_

#include "ap_fixed.h"
#include "ap_int.h"
#include "hls_stream.h"

#include "defines.h"


// Prototype of top level function for C-synthesis
void emi_detector(
    features_t features[48],
    result_t layer9_out[10]
);

// hls-fpga-machine-learning insert emulator-defines


#endif
