#!/bin/bash
# Board power of the controller-only design and of the complete four-kernel design, idle and running (PMBus rails).
#   sudo bash -lc "./measure_power.sh <data_dir> <out.csv> [passes]"      (bash -l: PYNQ environment)
# <data_dir> holds frames.bin / bufs.bin / waves.bin.  Running means the 20 kHz duty loop (pwr_loop) for the
# controller-only design and the three concurrent real-time tasks (run_rt_sched.sh) for the complete design.
set -u
D=${1:?data dir}; OUT=${2:?out csv}; PASSES=${3:-3}
HERE=$(cd "$(dirname "$0")" && pwd); cd "$HERE"
[ -x pwr_loop ] || gcc -O2 -o pwr_loop pwr_loop.c -lm || exit 1
[ -x rt_sched ] || gcc -O2 -pthread -o rt_sched rt_sched.c -lm || exit 1
NF=$(( $(stat -c %s "$D/frames.bin") / 72 ))
for p in $(seq 1 "$PASSES"); do
    python3 -c "from pynq import Overlay; Overlay('hardware/mpcc_hil.bit')" || exit 1
    sleep 5; python3 pmbus_sample.py 20 ctrl_only_idle "$OUT"
    ./pwr_loop "$D/frames.bin" "$NF" 30 & sleep 5; python3 pmbus_sample.py 20 ctrl_only_active "$OUT"; wait
    python3 -c "from pynq import Overlay; Overlay('hardware/mpcc_r.bit')" || exit 1
    sleep 5; python3 pmbus_sample.py 20 full_idle "$OUT"
    ./run_rt_sched.sh "$D" 30 /tmp/power_rt_$p 80 > /tmp/power_rt_$p.log & sleep 5; python3 pmbus_sample.py 20 full_active "$OUT"; wait
    grep -h late /tmp/power_rt_$p.log
done
