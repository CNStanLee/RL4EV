cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
VARIANT_NAME = "MPCC_R"; init_paras; build_supp('grid');
VARIANT_NAME = "MPCC_R"; init_paras; load_system('PV_MEV');
for b = {'PV_MEV/EV System/PFC Control/Enabled Subsystem', 'PV_MEV/EV System/PFC Control/Original vs HIL Predict'}, try, set_param(b{1}, 'Commented', 'on'); catch, end, end
try, PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); fprintf('compile ok\n'); catch ME, fprintf('COMPILE FAILED: %s\n', ME.message); try, PV_MEV([], [], [], 'term'); catch, end, end
close_system('PV_MEV', 0);
