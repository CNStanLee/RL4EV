set R <RL4EV>/HLS_PRJ
open_project -reset mpcc_r
set_top mpcc_r_hls
add_files $R/mpcc_r/mpcc_r_hls.cpp -cflags "-std=c++14 -I$R/mpcc_r"
add_files -tb $R/mpcc_r/tb_mpcc_r.cpp -cflags "-std=c++14 -I$R/mpcc_r -I$R/mpcc"
add_files -tb $R/mpcc/mpcc_hls.cpp -cflags "-std=c++14 -I$R/mpcc"
open_solution -reset sol1 -flow_target vivado
set_part xczu7ev-ffvc1156-2-e
create_clock -period 10ns
set_clock_uncertainty 27%
csim_design
csynth_design
exit
