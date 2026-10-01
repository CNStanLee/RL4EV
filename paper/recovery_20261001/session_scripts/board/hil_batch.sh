#!/bin/bash
# Board HIL stages H2..H5 (docs/HIL_TEST_PLAN.md section 3) + H0 x86 loopback, 3 MATLAB processes max.
# slot A: H2 (mpcc path) -> wait for H3 -> H5 (all paths, incl. random seeds 301-303)
# slot B: H3 (detector path, 13 cases)
# slot C: H4 (estimator path) -> H0 (x86 emulator, P1 x MPCC_R)
set -u
S=$(dirname "$0"); P=<RL4EV>/Simulation/PV_MEV; L=$S/matlab/logs
m() { nice -n 10 matlab -batch "cd('$P'); addpath(pwd); $1"; }
O="struct('save_iac', false, 'force', true, 'hil', struct("
H2="run_injection('run', {'E-DC-01b','E-AC-01b','E-AC-02b','E-BAT-02b'}, {'MPCC_D_H1','MPCC_R'}, ${O}'mpcc',1,'det',0,'est',0,'dir','hil_mpcc')));"
H3="run_injection('run', 'all', {'MPCC_D_H1'}, ${O}'mpcc',0,'det',1,'est',0,'dir','hil_det')));"
H4="run_injection('run', {'E-AC-01b','E-DC-01b'}, {'MPCC_D_H1'}, ${O}'mpcc',0,'det',0,'est',1,'dir','hil_est')));"
H5="run_injection('run', 'P1', {'MPCC_R'}, ${O}'mpcc',1,'det',1,'est',1,'dir','hil_full'))); run_injection('dataset', [301 303], {'MPCC_R'}, ${O}'mpcc',1,'det',1,'est',1,'dir','hil_full')));"
H0="run_injection('run', 'P1', {'MPCC_R'}, ${O}'mpcc',1,'det',1,'est',1,'host','127.0.0.1','dir','hil_x86')));"
echo "batch start $(date +%T)"
# H0 (x86) already runs as a separate process; 2 more slots here: B = H3, A = H2 -> H4 -> (wait H3) -> H5
( m "$H3" > $L/h3_det.log 2>&1; echo "H3 done $(date +%T)" ) & PB=$!
( m "$H2" > $L/h2_mpcc.log 2>&1; echo "H2 done $(date +%T)"; m "$H4" > $L/h4_est.log 2>&1; echo "H4 done $(date +%T)"
  while kill -0 $PB 2>/dev/null; do sleep 30; done; m "$H5" > $L/h5_full.log 2>&1; echo "H5 done $(date +%T)" ) & PA=$!
wait $PA $PB
echo "batch done $(date +%T)"
