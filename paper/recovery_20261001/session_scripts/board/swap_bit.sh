#!/bin/bash
# install the i_ref-fixed bitstream on the board, rerun the H1 self-test, restart the PS server
S=$(dirname "$0")
BX_TIMEOUT=900 python3 $S/bx.py 'sudo -S pkill -f "[p]s_server_mpcc_r"; sleep 2; cd /home/xilinx/mpcc_r/PS_notebook/hardware && cp mpcc_r.bit mpcc_r_ireffix_old.bit && cp mpcc_r.hwh mpcc_r_ireffix_old.hwh && mv mpcc_r_new.bit mpcc_r.bit && mv mpcc_r_new.hwh mpcc_r.hwh && md5sum mpcc_r.bit && cd .. && sudo -S bash -lc "python3 -u board_selftest_mpcc_r.py --n 200 > /home/xilinx/mpcc_r/selftest_h1_ireffix.log 2>&1; grep -v Unsupported /home/xilinx/mpcc_r/selftest_h1_ireffix.log; nohup python3 -u ps_server_mpcc_r.py --log /home/xilinx/mpcc_r/logs > /home/xilinx/mpcc_r/logs/server.log 2>&1 &"; sleep 15; ss -ltn | grep -c "50[123][01]"' 2>&1 | grep -v "^xilinx@\|sudo\]"
