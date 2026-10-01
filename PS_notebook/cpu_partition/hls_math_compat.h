// host build: map the hls_math namespace onto libm so the synthesised C++ runs unchanged on a CPU
#pragma once
#include <cmath>
namespace hls { using ::sinf; using ::cosf; using ::sqrtf; using ::hypotf; using ::atan2f; using ::fabsf; using ::expf; using ::logf; using ::fmaxf; using ::fminf; using ::floorf; using ::roundf;
                using ::sin; using ::cos; using ::sqrt; using ::hypot; using ::atan2; using ::fabs; using ::exp; using ::log; using ::fmax; using ::fmin; using ::floor; using ::round; }
