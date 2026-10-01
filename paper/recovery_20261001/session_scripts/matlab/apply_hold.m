% Tick-hold injection (review-2 point 6): after D_predict, a MATLAB Function holds the previous duty on control ticks that the
% measured concurrent schedule marked late; the mask is the base-workspace variable HOLDMASK ([t hold] at Ts_Control, zeros by default).
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
mdl = 'PV_MEV'; load_system(mdl); pc = [mdl '/EV System/PFC Control'];
if getSimulinkBlockHandle([pc '/tick_hold']) ~= -1, error('tick_hold already present'); end
lh = get_param([pc '/D_predict'], 'LineHandles'); l = lh.Outport(1);
dstb = get_param(l, 'DstBlockHandle'); dstp = get_param(l, 'DstPortHandle'); srcp = get_param(l, 'SrcPortHandle');
dst_names = arrayfun(@(h) get_param(h, 'Name'), dstb, 'UniformOutput', false); fprintf('[hold] D_predict/1 feeds: %s\n', strjoin(dst_names, ', '));
dstport_num = arrayfun(@(h) get_param(h, 'PortNumber'), dstp);
delete_line(l);
pos = get_param([pc '/D_predict'], 'Position');
add_block('simulink/User-Defined Functions/MATLAB Function', [pc '/tick_hold'], 'Position', [pos(3)+40 pos(2) pos(3)+110 pos(2)+40]);
add_block('simulink/Sources/From Workspace', [pc '/hold_mask'], 'VariableName', 'HOLDMASK', 'SampleTime', 'Ts_Control', 'Interpolate', 'off', 'OutputAfterFinalValue', 'Holding final value', 'Position', [pos(3)+40 pos(2)+60 pos(3)+110 pos(2)+80]);
rt = sfroot; ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [pc '/tick_hold']); ch = ch(1);
ch.Script = sprintf(['function Dout = tick_hold(D, hold)\n%%#codegen\n%% hold the previous duty on ticks the measured PS schedule marked late (review-2 point 6)\n' ...
    'persistent Dprev init\nif isempty(init), Dprev = 0; init = 1; end\nif hold > 0.5, Dout = Dprev; else, Dout = D; end\nDprev = Dout;\n']);
add_line(pc, 'D_predict/1', 'tick_hold/1', 'autorouting', 'on'); add_line(pc, 'hold_mask/1', 'tick_hold/2', 'autorouting', 'on');
for i = 1:numel(dstb), add_line(pc, 'tick_hold/1', sprintf('%s/%d', dst_names{i}, dstport_num(i)), 'autorouting', 'on'); end
save_system(mdl); close_system(mdl, 0); fprintf('[hold] PV_MEV saved\n');
VARIANT_NAME = 'MPCC_R'; init_paras; mdl = 'PV_MEV';
try, PV_MEV([], [], [], 'compile'); PV_MEV([], [], [], 'term'); fprintf('compile ok\n'); catch ME, fprintf('COMPILE FAILED: %s\n', ME.message); try, PV_MEV([], [], [], 'term'); catch, end, end
