cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
VARIANT_NAME = "MPCC_R"; init_paras; load_system('PV_MEV');
function set_scripts(mode)
    pc = 'PV_MEV/EV System/PFC Control'; d = [pc '/EMI Detector']; one = [pc '/One  Cycle Model Prediction'];
    spec = {[pc '/HIL MPCC TCP'], 'hil_mpcc_tcp', 1, 5010, 5011, 'double'; [d '/HIL Det TCP'], 'hil_det_tcp', 21, 5020, 5021, 'single'; [one '/HIL Est TCP'], 'hil_est_tcp', 8, 5030, 5031, 'single'};
    rt = sfroot;
    for i = 1:size(spec, 1)
        ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', spec{i, 1}); ch = ch(1);
        ch.Script = sprintf(['function y = %s(x)\n%%#codegen\ncoder.extrinsic(''hil_tcp'');\nxd = double(x);\nyd = zeros(1, %d);\nyd = hil_tcp(xd, %d, %d, %d);\ny = cast(yd, ''%s'');\n'], spec{i, 2}, spec{i, 3}, spec{i, 3}, spec{i, 4}, spec{i, 5}, spec{i, 6});
        dy = ch.find('-isa', 'Stateflow.Data', 'Name', 'y');
        if mode == 2, dy(1).DataType = spec{i, 6}; dy(1).Props.Array.Size = sprintf('[1 %d]', spec{i, 3}); else, dy(1).DataType = 'Inherit: Same as Simulink'; dy(1).Props.Array.Size = '-1'; end
    end
end
function ok = try_compile(tag)
    for b = {'PV_MEV/EV System/PFC Control/Enabled Subsystem', 'PV_MEV/EV System/PFC Control/Original vs HIL Predict'}, try, set_param(b{1}, 'Commented', 'on'); catch, end, end
    f = sprintf('<SCRATCH>/matlab/diag_%s.txt', tag);
    sldiagviewer.diary(f); sldiagviewer.diary('on');
    try, PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); ok = true;
    catch, ok = false; try, PV_MEV([], [], [], 'term'); catch, end
    end
    sldiagviewer.diary('off');
end
set_scripts(2); okB = try_compile('B'); fprintf('B ok=%d\n', okB);
if okB
    try, save_system('PV_MEV'); fprintf('saved\n'); catch ME, fprintf('SAVE FAILED: %s\n', ME.message); end
    try, close_system('PV_MEV', 0); catch, end
else
    close_system('PV_MEV', 0); fprintf('NOT saved\n');
end
