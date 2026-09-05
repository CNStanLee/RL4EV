function build_hil(step)
% BUILD_HIL  Add the detector and estimator HIL paths (TCP to the ZCU104 PS, or to PS_notebook/x86_pl_emulator.py)
% next to the existing MPCC HIL path, each behind its own switch (docs/HIL_TEST_PLAN.md, section 2).
%
%   build_hil()          add the blocks and save
%   build_hil('inspect') print the current state
%
% Paths (all instrumentlib TCP/IP Send / Receive, little-endian single, host HIL_HOST from init_paras):
%   mpcc_r   : PFC Control/HIL TCP Send1 -> 5010 (existing, 14 values; MPCC_R needs 18: + flags, amp_iac, mask, t_ramp),
%              Receive1 <- 5011 (D), selected by Switch3 when ENABLE_HIL
%   detector : EMI Detector/HIL Det Send -> 5020 (2400 values: the 200 x 12 cycle buffer, row-major),
%              HIL Det Receive <- 5021 (21 values: 5 logits, 10 zeros, 5 amplitudes, flags word);
%              the first 20 replace the ONNX Runner output at emi_decide when ENABLE_HIL_DET
%   estimator: One Cycle Model Prediction/HIL Est Send -> 5030 (80 raw samples, before CycleNorm),
%              HIL Est Receive <- 5031 (8 values: enc); replaces the ONNX Runner output when ENABLE_HIL_EST
% The switches are Simulink Switch blocks on Constants (ENABLE_HIL_DET / ENABLE_HIL_EST) so the SIL path is untouched
% when they are 0; run_injection comments the TCP blocks out (like the existing ones) when a switch is 0.
if nargin < 1, step = 'all'; end
mdir = fileparts(mfilename('fullpath')); cd(mdir); addpath(mdir);
mdl = 'PV_MEV'; load_system(mdl);
pc = [mdl '/EV System/PFC Control']; d = [pc '/EMI Detector']; one = [pc '/One  Cycle Model Prediction'];
if strcmp(step, 'inspect'), inspect(pc, d, one); close_system(mdl, 0); return; end

% ---------------------------------------------------------------- detector path
if getSimulinkBlockHandle([d '/HIL Det Send']) == -1
    % buffer (200 x 12) -> reshape to a row of 2400 -> single -> TCP send
    add_block('simulink/Math Operations/Reshape', [d '/hil_flat'], 'OutputDimensionality', 'Row vector (2-D)', 'Position', [420 480 460 500]);
    add_block('simulink/Signal Attributes/Data Type Conversion', [d '/hil_single'], 'OutDataTypeStr', 'single', 'Position', [480 480 520 500]);
    add_block('instrumentlib/TCP/IP Send', [d '/HIL Det Send'], 'Host', 'HIL_HOST', 'Port', '5020', 'ByteOrder', 'little-endian', 'Timeout', '10', 'Priority', '-30', 'Position', [560 470 640 510]);
    add_block('instrumentlib/TCP/IP Receive', [d '/HIL Det Receive'], 'Host', 'HIL_HOST', 'Port', '5021', 'DataSize', '[1, 21]', 'DataType', 'single', 'ByteOrder', 'little-endian', 'Timeout', '10', 'Priority', '30', 'SampleTime', '0.02', 'Position', [560 540 640 580]);
    % the buffer is transposed inside Simulink (Buffer outputs 200 x 12): reshape row-major sample by sample
    add_block('simulink/Math Operations/Math Function', [d '/hil_T'], 'Operator', 'transpose', 'Position', [380 480 400 500]);
    add_line(d, 'Buf/1', 'hil_T/1', 'autorouting', 'on'); add_line(d, 'hil_T/1', 'hil_flat/1'); add_line(d, 'hil_flat/1', 'hil_single/1'); add_line(d, 'hil_single/1', 'HIL Det Send/1');
    % 21 -> first 20 for emi_decide; select between ONNX Runner output and HIL output
    add_block('simulink/Signal Routing/Selector', [d '/hil_sel20'], 'InputPortWidth', '21', 'Indices', '1:20', 'Position', [680 550 720 570]);
    add_line(d, 'HIL Det Receive/1', 'hil_sel20/1');
    add_block('simulink/Sources/Constant', [d '/hil_det_on'], 'Value', 'ENABLE_HIL_DET', 'Position', [680 600 740 620]);
    add_block('simulink/Signal Routing/Switch', [d '/hil_det_sw'], 'Criteria', 'u2 > Threshold', 'Threshold', '0.5', 'Position', [780 500 820 560]);
    delete_line_between(d, 'ONNX Runner', 1, 'emi_decide', 1);
    add_line(d, 'hil_sel20/1', 'hil_det_sw/1', 'autorouting', 'on'); add_line(d, 'hil_det_on/1', 'hil_det_sw/2', 'autorouting', 'on');
    add_line(d, 'ONNX Runner/1', 'hil_det_sw/3', 'autorouting', 'on'); add_line(d, 'hil_det_sw/1', 'emi_decide/1', 'autorouting', 'on');
    % board flag word logged next to the Simulink decision
    add_block('simulink/Signal Routing/Selector', [d '/hil_sel_flags'], 'InputPortWidth', '21', 'Indices', '21', 'Position', [680 640 720 660]);
    add_line(d, 'HIL Det Receive/1', 'hil_sel_flags/1');
    add_block('simulink/Signal Routing/Goto', [d '/Goto_det_hil_flags'], 'GotoTag', 'det_hil_flags', 'TagVisibility', 'global', 'Position', [760 640 860 660]);
    add_line(d, 'hil_sel_flags/1', 'Goto_det_hil_flags/1');
end
% ---------------------------------------------------------------- estimator path (raw window before CycleNorm -> enc)
if getSimulinkBlockHandle([one '/HIL Est Send']) == -1
    cn = [one '/MATLAB Function'];                                  % CycleNorm(x) -> [x_norm, A]; its input is the raw 80-sample window
    ph = get_param(cn, 'PortHandles'); l = get_param(ph.Inport(1), 'Line'); sp = get_param(l, 'SrcPortHandle');
    add_block('simulink/Signal Attributes/Data Type Conversion', [one '/hil_single'], 'OutDataTypeStr', 'single', 'Position', [100 400 140 420]);
    add_block('simulink/Math Operations/Reshape', [one '/hil_row'], 'OutputDimensionality', 'Row vector (2-D)', 'Position', [160 400 200 420]);
    add_block('instrumentlib/TCP/IP Send', [one '/HIL Est Send'], 'Host', 'HIL_HOST', 'Port', '5030', 'ByteOrder', 'little-endian', 'Timeout', '10', 'Priority', '-30', 'Position', [240 390 320 430]);
    add_block('instrumentlib/TCP/IP Receive', [one '/HIL Est Receive'], 'Host', 'HIL_HOST', 'Port', '5031', 'DataSize', '[1, 8]', 'DataType', 'single', 'ByteOrder', 'little-endian', 'Timeout', '10', 'Priority', '30', 'SampleTime', '1/(mm_fund_freq*mm_points_per_cycle)', 'Position', [240 460 320 500]);
    add_line(one, sp, get_param([one '/hil_single'], 'PortHandles').Inport(1), 'autorouting', 'on');
    add_line(one, 'hil_single/1', 'hil_row/1'); add_line(one, 'hil_row/1', 'HIL Est Send/1');
    add_block('simulink/Sources/Constant', [one '/hil_est_on'], 'Value', 'ENABLE_HIL_EST', 'Position', [240 530 300 550]);
    add_block('simulink/Signal Routing/Switch', [one '/hil_est_sw'], 'Criteria', 'u2 > Threshold', 'Threshold', '0.5', 'Position', [380 440 420 500]);
    delete_line_between(one, 'ONNX Runner', 1, 'Data Type Conversion1', 1);
    add_line(one, 'HIL Est Receive/1', 'hil_est_sw/1', 'autorouting', 'on'); add_line(one, 'hil_est_on/1', 'hil_est_sw/2', 'autorouting', 'on');
    add_line(one, 'ONNX Runner/1', 'hil_est_sw/3', 'autorouting', 'on'); add_line(one, 'hil_est_sw/1', 'Data Type Conversion1/1', 'autorouting', 'on');
end
% ---------------------------------------------------------------- MPCC_R frame: 14 -> 18 values on the existing send block
snd = [pc '/HIL TCP Send1'];
if getSimulinkBlockHandle([pc '/hil_mpcc_ext']) == -1 && getSimulinkBlockHandle(snd) ~= -1
    ph = get_param(snd, 'PortHandles'); l = get_param(ph.Inport(1), 'Line'); sp = get_param(l, 'SrcPortHandle'); delete_line(l);
    add_block('simulink/Signal Routing/Mux', [pc '/hil_mpcc_ext'], 'Inputs', '5', 'Position', [5000 2000 5005 2100]);
    add_block('simulink/Signal Routing/From', [pc '/From_hil_flags'], 'GotoTag', 'det_chan', 'Position', [4880 2020 4960 2040]);
    add_block('simulink/User-Defined Functions/MATLAB Function', [pc '/hil_flagword'], 'Position', [4900 2050 4960 2080]);
    set_mlfcn([pc '/hil_flagword'], sprintf('function w = flagword(c)\n%%#codegen\nw = single(c(1) + 2*c(2) + 4*c(3) + 8*c(4) + 16*c(5));\n'), {'c', '[1 5]'; 'w', '1'});
    add_block('simulink/Signal Routing/From', [pc '/From_hil_amp'], 'GotoTag', 'det_amp', 'Position', [4880 2090 4960 2110]);
    add_block('simulink/Signal Routing/Selector', [pc '/hil_amp3'], 'InputPortWidth', '5', 'Indices', '3', 'Position', [4970 2090 4990 2110]);
    add_block('simulink/Sources/Constant', [pc '/hil_mask'], 'Value', 'single(mitigation_mask)', 'Position', [4880 2120 4960 2140]);
    add_block('simulink/Sources/Constant', [pc '/hil_tramp'], 'Value', 'single(mit_t_ramp)', 'Position', [4880 2150 4960 2170]);
    add_line(pc, sp, get_param([pc '/hil_mpcc_ext'], 'PortHandles').Inport(1), 'autorouting', 'on');
    add_line(pc, 'From_hil_flags/1', 'hil_flagword/1'); add_line(pc, 'hil_flagword/1', 'hil_mpcc_ext/2', 'autorouting', 'on');
    add_line(pc, 'From_hil_amp/1', 'hil_amp3/1'); add_line(pc, 'hil_amp3/1', 'hil_mpcc_ext/3', 'autorouting', 'on');
    add_line(pc, 'hil_mask/1', 'hil_mpcc_ext/4', 'autorouting', 'on'); add_line(pc, 'hil_tramp/1', 'hil_mpcc_ext/5', 'autorouting', 'on');
    add_line(pc, 'hil_mpcc_ext/1', 'HIL TCP Send1/1', 'autorouting', 'on');
    set_param(snd, 'Host', 'HIL_HOST'); set_param([pc '/HIL TCP Receive1'], 'Host', 'HIL_HOST');
end
inspect(pc, d, one);
save_system(mdl); close_system(mdl);
fprintf('[build_hil] PV_MEV saved\n');
end

% =========================================================================
function inspect(pc, d, one)
for b = {[pc '/HIL TCP Send1'], [pc '/hil_mpcc_ext'], [d '/HIL Det Send'], [d '/HIL Det Receive'], [d '/hil_det_sw'], [one '/HIL Est Send'], [one '/HIL Est Receive'], [one '/hil_est_sw']}
    if getSimulinkBlockHandle(b{1}) == -1, fprintf('   (missing) %s\n', b{1}); else, fprintf('   [%s] %s\n', get_param(b{1}, 'BlockType'), b{1}); end
end
end

function delete_line_between(sys, srcb, srcp, dstb, dstp)
ph = get_param([sys '/' dstb], 'PortHandles'); l = get_param(ph.Inport(dstp), 'Line');
assert(l ~= -1, 'no line into %s/%d', dstb, dstp);
sp = get_param(l, 'SrcPortHandle');
assert(strcmp(get_param(get_param(sp, 'Parent'), 'Name'), srcb) && get_param(sp, 'PortNumber') == srcp, 'unexpected source of %s/%d', dstb, dstp);
delete_line(sys, sp, ph.Inport(dstp));
end

function set_mlfcn(blk, code, sizes)
rt = sfroot; ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', blk);
if isempty(ch), error('MATLAB Function chart not found: %s', blk); end
ch = ch(1); ch.Script = code;
if nargin > 2
    for i = 1:size(sizes, 1)
        dd = ch.find('-isa', 'Stateflow.Data', 'Name', sizes{i, 1});
        if ~isempty(dd), dd(1).Props.Array.Size = sizes{i, 2}; dd(1).DataType = 'Inherit: Same as Simulink'; end
    end
end
end
