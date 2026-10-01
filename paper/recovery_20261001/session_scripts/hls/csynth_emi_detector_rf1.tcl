# Baseline csynth of HLS_PRJ/emi_detector as generated (latency strategy, ReuseFactor 1), Vitis HLS 2022.2
set R <RL4EV>/HLS_PRJ/emi_detector
open_project -reset emi_detector_rf1
set_top emi_detector_axi
set cf [string map [list @R@ $R] {-std=c++17 -I@R@/firmware -I@R@/firmware/nnet_utils -DWEIGHTS_DIR=\"@R@/firmware/weights\"}]
add_files $R/emi_detector_axi.cpp -cflags $cf
add_files $R/firmware/emi_detector.cpp -cflags $cf
add_files -tb $R/tb_emi_detector.cpp -cflags $cf
add_files -tb $R/tb_data
open_solution -reset sol1 -flow_target vivado
set_part xczu7ev-ffvc1156-2-e
create_clock -period 10ns
set_clock_uncertainty 27%
config_export -format ip_catalog
csim_design
csynth_design
exit
