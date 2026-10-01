cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
VARIANT_NAME = "MPCC_R"; init_paras; mdl = 'PV_MEV'; load_system(mdl);
pc = [mdl '/EV System/PFC Control']; d = [pc '/EMI Detector']; one = [pc '/One  Cycle Model Prediction'];
rt = sfroot;
spec = {[pc '/HIL MPCC TCP'], 'hil_mpcc_tcp', 1, 5010, 5011, 'y = yd;'; [d '/HIL Det TCP'], 'hil_det_tcp', 21, 5020, 5021, 'y = single(yd);'; [one '/HIL Est TCP'], 'hil_est_tcp', 8, 5030, 5031, 'y = single(yd);'};
for i = 1:size(spec, 1)
    ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', spec{i, 1}); assert(~isempty(ch), spec{i, 1});
    ch(1).Script = sprintf(['function y = %s(x)\n%%#codegen\n%% HIL round trip over TCP (build_hil.m v2): hil_tcp.m keeps the clients, reads the switch from the base workspace\n' ...
        'coder.extrinsic(''hil_tcp'');\nyd = zeros(1, %d);\nyd = hil_tcp(x, %d, %d, %d);\n%s\n'], spec{i, 2}, spec{i, 3}, spec{i, 3}, spec{i, 4}, spec{i, 5}, spec{i, 6});
    fprintf('updated %s\n', spec{i, 1});
end
% compile check
for b = {'/EV System/PFC Control/Enabled Subsystem', '/EV System/PFC Control/Original vs HIL Predict'}, try, set_param([mdl b{1}], 'Commented', 'on'); catch, end, end
PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); fprintf('compile ok\n');
save_system(mdl); close_system(mdl); fprintf('saved\n');
