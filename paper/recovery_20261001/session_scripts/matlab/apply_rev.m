cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
copyfile('PV_MEV.slx', 'results/emi/PV_MEV_pre_rev_backup.slx');
VARIANT_NAME = "MPCC_R_OR1"; init_paras; build_supp('bumpless');
VARIANT_NAME = "MPCC_R_OR1"; init_paras; build_supp('mismatch');
VARIANT_NAME = "MPCC_R_OR1"; MM = struct('chg_eff', 0.95); init_paras; load_system('PV_MEV');
for b = {'PV_MEV/EV System/PFC Control/Enabled Subsystem', 'PV_MEV/EV System/PFC Control/Original vs HIL Predict'}, try, set_param(b{1}, 'Commented', 'on'); catch, end, end
try, PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); fprintf('compile ok\n'); catch ME, fprintf('COMPILE FAILED: %s\n', ME.message); try, PV_MEV([], [], [], 'term'); catch, end, end
close_system('PV_MEV', 0);
