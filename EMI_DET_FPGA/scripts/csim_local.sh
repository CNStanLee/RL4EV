#!/bin/sh
# Local C simulation of a HLS_PRJ component without Vitis (zig c++ from the hgq2 env; hls4ml ships ap_types).
#   scripts/csim_local.sh emi_detector | harmonic_estimator
set -e
comp=$1; here=$(cd "$(dirname "$0")/.." && pwd); cd "$here/../HLS_PRJ/$comp"
PY=${PY:-/d/Anaconda/envs/hgq2/python.exe}
case $comp in
  emi_detector) srcs="emi_detector_axi.cpp firmware/emi_detector.cpp tb_emi_detector.cpp" ;;
  harmonic_estimator) srcs="harmonic_estimator_axi.cpp firmware/harmonic_estimator.cpp tb_harmonic_estimator.cpp" ;;
  *) echo "unknown component $comp"; exit 1 ;;
esac
mkdir -p build
"$PY" -m ziglang c++ -std=c++17 -O1 -w -Ifirmware -Ifirmware/nnet_utils -Ifirmware/ap_types -DWEIGHTS_DIR=\"firmware/weights\" $srcs -o build/csim.exe
./build/csim.exe
