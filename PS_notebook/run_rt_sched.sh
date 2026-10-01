#!/bin/bash
# Concurrent three-task timing replay on the ZCU104 (rt_sched.c) under real-time scheduling.
#   sudo ./run_rt_sched.sh <data_dir> <seconds> <out_prefix> [priority]
# <data_dir> holds frames.bin / bufs.bin / waves.bin (make_hil_replay_data.py); the bitstream must be loaded and
# ps_server_mpcc_r.py stopped (both drive the same PL registers).  The script switches the real-time throttle off and
# moves the movable interrupts to core 0 for the run, and restores both afterwards.
set -u
D=${1:?data dir}; SECS=${2:-20}; OUT=${3:-rt_sched_fifo}; PRIO=${4:-80}
HERE=$(cd "$(dirname "$0")" && pwd)
[ -x "$HERE/rt_sched" ] || gcc -O2 -pthread -o "$HERE/rt_sched" "$HERE/rt_sched.c" -lm || exit 1
NF=$(( $(stat -c %s "$D/frames.bin") / 72 )); NB=$(( $(stat -c %s "$D/bufs.bin") / 9600 )); NW=$(( $(stat -c %s "$D/waves.bin") / 320 ))
OLD=$(cat /proc/sys/kernel/sched_rt_runtime_us)
declare -A AFF
for f in /proc/irq/*/smp_affinity; do AFF[$f]=$(cat "$f"); echo 1 > "$f" 2>/dev/null; done
restore() { echo "$OLD" > /proc/sys/kernel/sched_rt_runtime_us; for f in "${!AFF[@]}"; do echo "${AFF[$f]}" > "$f" 2>/dev/null; done; }
trap restore EXIT
echo -1 > /proc/sys/kernel/sched_rt_runtime_us
RT_PRIO=$PRIO "$HERE/rt_sched" "$D/frames.bin" "$NF" "$D/bufs.bin" "$NB" "$D/waves.bin" "$NW" "$SECS" "$OUT"
