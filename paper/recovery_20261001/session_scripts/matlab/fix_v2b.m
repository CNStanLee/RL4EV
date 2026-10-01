cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
VARIANT_NAME = "MPCC_R"; init_paras; mdl = 'PV_MEV'; load_system(mdl);
pc = [mdl '/EV System/PFC Control']; d = [pc '/EMI Detector']; one = [pc '/One  Cycle Model Prediction'];
rt = sfroot;
spec = {[pc '/HIL MPCC TCP'], 'hil_mpcc_tcp', 1, 5010, 5011, 'double'; [d '/HIL Det TCP'], 'hil_det_tcp', 21, 5020, 5021, 'single'; [one '/HIL Est TCP'], 'hil_est_tcp', 8, 5030, 5031, 'single'};
for b = {'/EV System/PFC Control/Enabled Subsystem', '/EV System/PFC Control/Original vs HIL Predict'}, try, set_param([mdl b{1}], 'Commented', 'on'); catch, end, end
function ok = try_compile()
    try, PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); ok = true;
    catch ME, ok = false; r = getReport(ME, 'extended', 'hyperlinks', 'off'); i = strfind(r, 'Caused by'); if isempty(i), i = 1; end; fprintf('%s\n', r(i(1):min(end, i(1) + 900))); try, PV_MEV([], [], [], 'term'); catch, end
    end
end
% attempt A: double then cast, inherited types
for i = 1:size(spec, 1)
    ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', spec{i, 1}); ch = ch(1);
    if strcmp(spec{i, 6}, 'single'), cast = 'y = single(yd);'; else, cast = 'y = yd;'; end
    ch.Script = sprintf(['function y = %s(x)\n%%#codegen\ncoder.extrinsic(''hil_tcp'');\nyd = zeros(1, %d);\nyd = hil_tcp(x, %d, %d, %d);\n%s\n'], spec{i, 2}, spec{i, 3}, spec{i, 3}, spec{i, 4}, spec{i, 5}, cast);
end
fprintf('--- attempt A\n'); okA = try_compile(); fprintf('A ok=%d\n', okA);
if ~okA
    % attempt B: explicit output type and size on the chart data, input converted to double inside
    for i = 1:size(spec, 1)
        ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', spec{i, 1}); ch = ch(1);
        ch.Script = sprintf(['function y = %s(x)\n%%#codegen\ncoder.extrinsic(''hil_tcp'');\nxd = double(x);\nyd = zeros(1, %d);\nyd = hil_tcp(xd, %d, %d, %d);\ny = cast(yd, ''%s'');\n'], spec{i, 2}, spec{i, 3}, spec{i, 3}, spec{i, 4}, spec{i, 5}, spec{i, 6});
        dy = ch.find('-isa', 'Stateflow.Data', 'Name', 'y'); dy(1).DataType = spec{i, 6}; dy(1).Props.Array.Size = sprintf('[1 %d]', spec{i, 3});
    end
    fprintf('--- attempt B\n'); okB = try_compile(); fprintf('B ok=%d\n', okB);
    if ~okB, close_system(mdl, 0); error('both attempts failed'); end
end
save_system(mdl); close_system(mdl); fprintf('saved\n');
