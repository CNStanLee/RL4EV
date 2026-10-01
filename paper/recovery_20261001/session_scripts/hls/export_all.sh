#!/bin/bash
# regenerate the detector firmware at RF 43, rebuild the component, then csim+csynth+export all four IPs
source /home/changhong/anaconda3/etc/profile.d/conda.sh; conda activate hgq2; source /tools/Xilinx/Vitis_HLS/2022.2/settings64.sh; export KERAS_BACKEND=torch
cd <RL4EV>/EMI_DET_FPGA
nice -n 10 python scripts/hls4ml_sweep.py detector --rf 43 --no-dataflow --no-synth --out <SCRATCH>/sweep --tag _final43 --firmware runs/det_v5/fpga/firmware
nice -n 10 python scripts/make_board_components.py --only detector --detector-firmware runs/det_v5/fpga/firmware
cd <SCRATCH>/hls
for t in csynth_emi_detector_v5 csynth_estimator_v2 csynth_mpcc_r csynth_emi_feat; do
  sed '/^exit/d' $t.tcl > ${t}_exp.tcl
  echo "export_design -format ip_catalog -output <SCRATCH>/ip_repo/$t.zip" >> ${t}_exp.tcl; echo "exit" >> ${t}_exp.tcl
  nice -n 10 vitis_hls -f ${t}_exp.tcl > ${t}_exp.log 2>&1
  grep -n 'CSim done\|ERROR\|Finished Command csynth\|export_design' ${t}_exp.log | tail -3
done
cd <SCRATCH>/ip_repo && for z in *.zip; do d=${z%.zip}; mkdir -p $d && unzip -o -q $z -d $d; done; ls <SCRATCH>/ip_repo
echo EXPORT_DONE
