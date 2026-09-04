#ifndef HARMONIC_ESTIMATOR_H_
#define HARMONIC_ESTIMATOR_H_

#include "ap_fixed.h"
#include "ap_int.h"
#include "hls_stream.h"

#include "defines.h"


// Prototype of top level function for C-synthesis
void harmonic_estimator(
    waveform_t waveform[80*1],
    result_t layer34_out[8]
);

// hls-fpga-machine-learning insert emulator-defines


#endif
