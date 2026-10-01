#!/bin/bash
# mpcc_r IP (i_ref sign fix) -> ip_repo -> Vivado bitstream; logs in <SCRATCH>/hls
source /tools/Xilinx/Vitis_HLS/2022.2/settings64.sh
cd <SCRATCH>/hls && nice -n 10 vitis_hls -f csynth_mpcc_r_fix.tcl > csynth_mpcc_r_fix.log 2>&1
grep -n 'CSim done\|ERROR\|Finished Command csynth\|export_design\|PASS\|FAIL' csynth_mpcc_r_fix.log | tail -6
grep -q "ERROR" csynth_mpcc_r_fix.log && { echo HLS_FAILED; exit 1; }
cd <SCRATCH>/ip_repo && rm -rf csynth_mpcc_r && mkdir csynth_mpcc_r && unzip -o -q csynth_mpcc_r.zip -d csynth_mpcc_r && ls csynth_mpcc_r | head -3
source /tools/Xilinx/Vivado/2022.2/settings64.sh
cd <RL4EV>/Vivado_PRJ/MPCC_R && cp -r out out_pre_ireffix_$(date +%H%M) && nice -n 5 vivado -mode batch -source build_bd.tcl -tclargs <SCRATCH>/ip_repo run_impl=1 > <SCRATCH>/hls/vivado_build.log 2>&1
echo "vivado exit $? $(date +%T)"; ls -la out/; grep -i "timing\|WNS\|ERROR" <SCRATCH>/hls/vivado_build.log | tail -5
echo REBUILD_DONE
