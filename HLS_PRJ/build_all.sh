#!/bin/bash
# Build the HLS IPs with Vitis HLS 2022.2 (Tcl flow).
#   ./build_all.sh                         # csim + csynth + export for all five components
#   HLS_STEPS=csim ./build_all.sh          # C simulation only
#   ./build_all.sh mpcc_r emi_feat         # selected components
# Set XILINX_HLS_SETTINGS if Vitis HLS is not installed under /tools/Xilinx.
set -e
here=$(cd "$(dirname "$0")" && pwd)
: "${XILINX_HLS_SETTINGS:=/tools/Xilinx/Vitis_HLS/2022.2/settings64.sh}"
command -v vitis_hls >/dev/null 2>&1 || . "$XILINX_HLS_SETTINGS"
steps=${HLS_STEPS:-"csim csynth export"}
[ $# -gt 0 ] && comps="$*" || comps="mpcc mpcc_r emi_feat emi_detector harmonic_estimator"
cd "$here"
for c in $comps; do
    echo "=== $c: $steps"
    HLS_COMPONENT=$c HLS_STEPS="$steps" vitis_hls -f build_hls.tcl -l "$c/vitis_hls_$c.log"
done
