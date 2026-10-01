set R <RL4EV>/HLS_PRJ/emi_feat
open_project -reset emi_feat
set_top emi_feat_hls
add_files $R/emi_feat_hls.cpp -cflags "-std=c++14 -I$R"
add_files -tb $R/tb_emi_feat.cpp -cflags "-std=c++14 -I$R"
add_files -tb $R/tb_data
open_solution -reset sol1 -flow_target vivado
set_part xczu7ev-ffvc1156-2-e
create_clock -period 10ns
set_clock_uncertainty 27%
csim_design
csynth_design
exit
