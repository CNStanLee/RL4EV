#!/bin/bash
# H0: x86 loopback (emulator on this host) - run_injection with all three TCP paths, HIL_HOST 127.0.0.1
# usage: h0_run.sh "<tests matlab cell or 'P1'>" "<variants cell>" <logname>
set -u
S=$(dirname "$0"); P=<RL4EV>/Simulation/PV_MEV; R=<RL4EV>
source /home/changhong/anaconda3/etc/profile.d/conda.sh; conda activate hgq2
cd $R; python PS_notebook/x86_pl_emulator.py > $S/matlab/logs/emu_$3.log 2>&1 &
EMU=$!; sleep 8
nice -n 10 matlab -batch "cd('$P'); addpath(pwd); run_injection('run', $1, $2, struct('save_iac', false, 'force', true, 'hil', struct('mpcc', 1, 'det', 1, 'est', 1, 'host', '127.0.0.1')));" > $S/matlab/logs/h0_$3.log 2>&1
kill $EMU; wait $EMU 2>/dev/null; echo "h0 $3 done $(date +%T)"
