#!/bin/bash
source /tools/Xilinx/Vivado/2022.2/settings64.sh
cd <RL4EV>/Vivado_PRJ/MPCC_R && nice -n 5 vivado -mode batch -source build_bd.tcl -tclargs <SCRATCH>/ip_repo 1 > <SCRATCH>/hls/vivado_build.log 2>&1
echo "vivado exit $? $(date +%T)"; ls -la out/; grep -i "BUILD_DONE\|WNS\|ERROR" <SCRATCH>/hls/vivado_build.log | tail -5
echo REBUILD_DONE
