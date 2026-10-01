cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd); VARIANT_NAME = "MPCC_R"; init_paras; load_system('PV_MEV');
src = sprintf('PV_MEV/600V\nUtlity Grid/120kV programmable');
set_param(src, 'PositiveSequence', '[120e3 0 Fnom+grid_df]', 'VariationEntity', 'Amplitude', 'VariationType', 'Step', 'VariationStep', 'grid_var_step', 'VariationTiming', '[grid_var_t0 5]', 'HarmonicGeneration', 'on', 'HarmonicA', '[5 grid_h5 0 1]', 'HarmonicB', '[7 grid_h7 0 1]', 'Timing', '[grid_var_t0 5]');
for b = {'PV_MEV/EV System/PFC Control/Enabled Subsystem', 'PV_MEV/EV System/PFC Control/Original vs HIL Predict'}, try, set_param(b{1}, 'Commented', 'on'); catch, end, end
PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); fprintf('compile ok\n');
save_system('PV_MEV'); close_system('PV_MEV'); fprintf('saved\n');
