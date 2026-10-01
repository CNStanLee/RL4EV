cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
copyfile('PV_MEV.slx', 'results/emi/PV_MEV_pre_supp_backup.slx'); copyfile('MyLibrary.slx', 'results/emi/MyLibrary_pre_supp_backup.slx');
VARIANT_NAME = "MPCC_R_B_OR"; INJ = struct('channel', [1 0 0], 'shape', [8 1 1], 'amp', [0.1 0 0], 't_on', 0.7, 'dwell', 0.3); init_paras;
build_supp();
VARIANT_NAME = "MPCC_R_B_OR"; INJ = struct('channel', [1 0 0], 'shape', [8 1 1], 'amp', [0.1 0 0], 't_on', 0.7, 'dwell', 0.3); init_paras; load_system('PV_MEV');
for b = {'PV_MEV/EV System/PFC Control/Enabled Subsystem', 'PV_MEV/EV System/PFC Control/Original vs HIL Predict'}, try, set_param(b{1}, 'Commented', 'on'); catch, end, end
sldiagviewer.diary('<SCRATCH>/matlab/diag_supp.txt'); sldiagviewer.diary('on');
try, PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); fprintf('compile ok\n'); catch ME, fprintf('COMPILE FAILED: %s\n', ME.message); try, PV_MEV([], [], [], 'term'); catch, end, end
sldiagviewer.diary('off'); close_system('PV_MEV', 0);
