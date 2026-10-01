#!/bin/bash
S=$(dirname "$0")
nice -n 10 matlab -batch "cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd); run_injection('run', 'P1', {'MPCC_R'}, struct('save_iac', false, 'force', true, 'hil', struct('mpcc',1,'det',1,'est',1,'dir','hil_full'))); run_injection('dataset', [301 303], {'MPCC_R'}, struct('save_iac', false, 'force', true, 'hil', struct('mpcc',1,'det',1,'est',1,'dir','hil_full')));" > \<SCRATCH>/matlab/logs/h5_full.log 2>&1
echo "H5 done $(date +%T)" >> \<SCRATCH>/matlab/logs/h5_full.log
