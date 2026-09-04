function build_detector(step)
% BUILD_DETECTOR  Add the EMI-injection detector (IDS) to PV_MEV/EV System/PFC Control.
%
%   build_detector()           build / rebuild the 'EMI Detector' subsystem and save
%   build_detector('inspect')  print the current state
%
% Per grid cycle (20 ms, aligned to multiples of 0.02 s like features.py):
%   200-sample buffers at 10 kHz of the controller-internal signals
%   Vdc_int, Vac_int, Iac_int, Iref, theta_pll, D, Vref and the charger's
%   Vbat_int, Ibat_int, D_dcdc, state, Iref_bat (from the global tag chg_sig)
%   -> emi_features (43 base features, same definitions as
%      EMI_DET_FPGA/src/emi_det/features.py)
%   -> emi_augment  (baseline-relative deviations via a slow EMA state +
%      strategy one-hot -> 92-vector, features.FEATURE_NAMES_V2 order)
%   -> OnnxRunner (det_onnx_file: 92 -> 16 = 5 channel logits, 10 class
%      logits, 1 amplitude; standardization is inside the ONNX)
%   -> emi_decide (sigmoid thresholds det_thr, persistence count, argmax)
% Outputs (Goto tags, logged by run_injection): det_feat (1x92), det_raw
% (1x16), det_chan (1x5 flags), det_class, det_conf, det_amp.
% Parameters (init_paras): det_onnx_file, det_thr (1x5), det_ema_alpha,
% det_persist, variant one-hot det_variant_onehot (1x6).
if nargin < 1, step = 'all'; end
mdir = fileparts(mfilename('fullpath')); cd(mdir); addpath(mdir);
mdl = 'PV_MEV'; load_system(mdl);
ev = [mdl '/EV System']; pc = [ev '/PFC Control']; d = [pc '/EMI Detector'];
if strcmp(step, 'inspect'), inspect(d); close_system(mdl, 0); return; end
% charger signal must be visible inside PFC Control
set_param([ev '/Goto_chg'], 'TagVisibility', 'global');
if getSimulinkBlockHandle(d) ~= -1, delete_block(d); end
add_block('built-in/Subsystem', d, 'Position', [5300 1200 5500 1420]);
delete_lines_in(d);
% ---- sources: internal PFC quantities.  PFC Control's own Goto tags are LOCAL and a From
% inside this nested subsystem silently reads zeros, so dedicated GLOBAL tags det_* are
% branched off the same source lines (plain 'D' would clash with the PV-side MPPT tag).
src = {'V_o', 'V_in', 'i_L', 'Iref', 'theta_pll', 'D'};       % Vdc_int, Vac_int, Iac_int, Iref, theta, duty
newtags = {'det_Vdc', 'det_Vac', 'det_Iac', 'det_Iref', 'det_theta', 'det_D'};
for i = 1:numel(src)
    g = find_system(pc, 'SearchDepth', 1, 'LookUnderMasks', 'all', 'BlockType', 'Goto', 'GotoTag', src{i}); assert(~isempty(g), 'no Goto %s', src{i}); g = g{1};
    nb = sprintf('%s/Goto_%s', pc, newtags{i});
    if getSimulinkBlockHandle(nb) == -1
        lh = get_param(g, 'LineHandles'); sp = get_param(lh.Inport, 'SrcPortHandle'); p = get_param(g, 'Position');
        if strcmp(src{i}, 'Iref')      % the 'Iref' tag carries Prod1 = amplitude*|sin theta|; the detector (and features.py) use the amplitude
            sr = get_param([pc '/Speed Regulator2'], 'PortHandles'); sp = sr.Outport(1);
        end
        add_block('simulink/Signal Routing/Goto', nb, 'GotoTag', newtags{i}, 'TagVisibility', 'global', 'Position', [p(1) p(2) + 40 p(3) + 30 p(4) + 40]);
        add_line(pc, sp, get_param(nb, 'PortHandles').Inport(1), 'autorouting', 'on');
    end
    add_block('simulink/Signal Routing/From', sprintf('%s/From_%d', d, i), 'GotoTag', newtags{i}, 'Position', [30 40 * i, 110 40 * i + 20]);
end
add_block('simulink/Signal Routing/From', [d '/From_vref'], 'GotoTag', 'Vref_det', 'Position', [30 320 110 340]);
add_block('simulink/Signal Routing/From', [d '/From_chg'], 'GotoTag', 'chg_sig', 'Position', [30 360 110 380]);
% Vref: PFC Control inport 1 -> Goto Vref_det (added at PFC Control level)
if getSimulinkBlockHandle([pc '/Goto_vref_det']) == -1
    add_block('simulink/Signal Routing/Goto', [pc '/Goto_vref_det'], 'GotoTag', 'Vref_det', 'TagVisibility', 'global', 'Position', [430 380 520 400]);
    add_line(pc, 'Vref/1', 'Goto_vref_det/1', 'autorouting', 'on');
end
% ---- 10 kHz sampling + 200-sample non-overlapping buffers (one grid cycle)
n_sig = 7;
mux = [d '/Mux_sig']; add_block('simulink/Signal Routing/Mux', mux, 'Inputs', '7', 'Position', [160 30 165 400]);
for i = 1:6, add_line(d, sprintf('From_%d/1', i), sprintf('Mux_sig/%d', i)); end
add_line(d, 'From_vref/1', 'Mux_sig/7');
% charger vector: pick Vbat_int(3) Ibat_int(4) D_dcdc(5) state(6) Iref_bat(7)
add_block('simulink/Signal Routing/Selector', [d '/Sel_chg'], 'InputPortWidth', '9', 'Indices', '[3 4 5 6 7]', 'Position', [120 355 140 385]);
add_line(d, 'From_chg/1', 'Sel_chg/1');
add_block('simulink/Signal Routing/Mux', [d '/Mux_all'], 'Inputs', '2', 'Position', [200 30 205 400]);
add_line(d, 'Mux_sig/1', 'Mux_all/1'); add_line(d, 'Sel_chg/1', 'Mux_all/2');
add_block('simulink/Discrete/Zero-Order Hold', [d '/ZOH'], 'SampleTime', '1e-4', 'Position', [240 200 280 230]);
add_line(d, 'Mux_all/1', 'ZOH/1');
add_block('dspbuff3/Buffer', [d '/Buf'], 'N', '200', 'V', '0', 'ic', '0', 'Position', [320 195 370 235]);
add_line(d, 'ZOH/1', 'Buf/1');
% ---- feature extraction (43), augmentation (92), ONNX, decision
add_block('simulink/User-Defined Functions/MATLAB Function', [d '/emi_features'], 'Position', [420 180 520 250]);
set_mlfcn([d '/emi_features'], features_code(), {'X', '[200 12]'; 'f', '[1 43]'});
add_block('simulink/Discrete/Unit Delay', [d '/ema'], 'SampleTime', '0.02', 'InitialCondition', 'zeros(1,44)', 'Position', [420 300 460 330]);
add_block('simulink/Sources/Constant', [d '/onehot'], 'Value', 'det_variant_onehot', 'Position', [420 360 500 380]);
add_block('simulink/Sources/Constant', [d '/alpha'], 'Value', 'det_ema_alpha', 'Position', [420 400 500 420]);
add_block('simulink/User-Defined Functions/MATLAB Function', [d '/emi_augment'], 'Position', [580 180 680 300]);
set_mlfcn([d '/emi_augment'], augment_code(), {'f', '[1 43]'; 'st', '[1 44]'; 'onehot', '[1 6]'; 'alpha', '1'; 'x', '[1 43]'; 'stn', '[1 44]'});
add_line(d, 'Buf/1', 'emi_features/1');
add_line(d, 'emi_features/1', 'emi_augment/1'); add_line(d, 'ema/1', 'emi_augment/2'); add_line(d, 'onehot/1', 'emi_augment/3'); add_line(d, 'alpha/1', 'emi_augment/4');
add_line(d, 'emi_augment/2', 'ema/1');
add_block('simulink/Signal Attributes/Data Type Conversion', [d '/to_single'], 'OutDataTypeStr', 'single', 'Position', [720 200 760 230]);
add_line(d, 'emi_augment/1', 'to_single/1');
add_block('simulink/User-Defined Functions/MATLAB System', [d '/ONNX Runner'], 'System', 'OnnxRunner', 'Position', [800 190 880 240]);
set_param([d '/ONNX Runner'], 'ModelFile', 'D:/Prj/RL4EV/EMI_DET_FPGA/artifacts/detector.onnx', 'NumIn', '43', 'NumOut', '16', 'SampleTime', '0.02');   % literal path: System block text params are not evaluated
add_line(d, 'to_single/1', 'ONNX Runner/1');
add_block('simulink/Sources/Constant', [d '/thr'], 'Value', 'det_thr', 'Position', [800 280 880 300]);
add_block('simulink/Sources/Constant', [d '/persist'], 'Value', 'det_persist', 'Position', [800 320 880 340]);
add_block('simulink/Discrete/Unit Delay', [d '/cnt'], 'SampleTime', '0.02', 'InitialCondition', 'zeros(1,5)', 'Position', [800 360 840 390]);
add_block('simulink/User-Defined Functions/MATLAB Function', [d '/emi_decide'], 'Position', [940 180 1040 320]);
set_mlfcn([d '/emi_decide'], decide_code(), {'raw', '[1 16]'; 'thr', '[1 5]'; 'persist', '1'; 'cnt', '[1 5]'; 'chan', '[1 5]'; 'cls', '1'; 'conf', '1'; 'amp', '1'; 'cntn', '[1 5]'});
add_line(d, 'ONNX Runner/1', 'emi_decide/1'); add_line(d, 'thr/1', 'emi_decide/2'); add_line(d, 'persist/1', 'emi_decide/3'); add_line(d, 'cnt/1', 'emi_decide/4');
add_line(d, 'emi_decide/5', 'cnt/1');
% ---- outputs
outs = {'emi_augment/1', 'det_feat'; 'ONNX Runner/1', 'det_raw'; 'emi_decide/1', 'det_chan'; 'emi_decide/2', 'det_class'; 'emi_decide/3', 'det_conf'; 'emi_decide/4', 'det_amp'};
for i = 1:size(outs, 1)
    g = sprintf('%s/Goto_%s', d, outs{i, 2});
    add_block('simulink/Signal Routing/Goto', g, 'GotoTag', outs{i, 2}, 'TagVisibility', 'global', 'Position', [1100 150 + 40 * i, 1200 170 + 40 * i]);
    add_line(d, outs{i, 1}, sprintf('Goto_%s/1', outs{i, 2}), 'autorouting', 'on');
end
inspect(d);
save_system(mdl); close_system(mdl);
fprintf('[build_detector] PV_MEV saved\n');
end

% =========================================================================
function inspect(d)
if getSimulinkBlockHandle(d) == -1, fprintf('no EMI Detector subsystem\n'); return; end
b = find_system(d, 'SearchDepth', 1);
for i = 2:numel(b), fprintf('   [%s] %s\n', get_param(b{i}, 'BlockType'), get_param(b{i}, 'Name')); end
end

function delete_lines_in(p)
l = find_system(p, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'line');
for k = 1:numel(l), try, delete_line(l(k)); catch, end, end
b = find_system(p, 'SearchDepth', 1); b = b(~strcmp(b, p));
for k = 1:numel(b), try, delete_block(b{k}); catch, end, end
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

% -------------------------------------------------------------------------
function s = features_code()
% Mirror of EMI_DET_FPGA/src/emi_det/features.py::cycle_features (43 base
% features).  X is the 200 x 12 buffer of one cycle at 10 kHz:
%  1 Vdc_int 2 Vac_int 3 Iac_int 4 Iref 5 theta 6 D 7 Vref 8 Vbat_int 9 Ibat_int 10 D_dcdc 11 state 12 Iref_bat
s = sprintf(['function f = emi_features(X)\n' ...
'%%#codegen\n' ...
'persistent prev\n' ...
'if isempty(prev), prev = zeros(1, 36); end\n' ...
'n = size(X, 1);\n' ...
'vdc = X(:,1); vac = X(:,2); iac = X(:,3); iref = X(:,4); th = X(:,5); d = X(:,6); vr = X(:,7);\n' ...
'vbat = X(:,8); ibat = X(:,9); ddc = X(:,10); st = X(:,11); irb = X(:,12);\n' ...
'k = (0:n-1)'';\n' ...
'w1 = 2*pi/n; c1 = cos(w1*k); s1 = sin(w1*k); c2 = cos(2*w1*k); s2 = sin(2*w1*k); c3 = cos(3*w1*k); s3 = sin(3*w1*k);\n' ...
'vac_amp = 2/n*hypot(vac''*c1, vac''*s1); vac_mean = mean(vac);\n' ...
'h1 = 2/n*hypot(iac''*c1, iac''*s1); h2 = 2/n*hypot(iac''*c2, iac''*s2); h3 = 2/n*hypot(iac''*c3, iac''*s3);\n' ...
'iac_mean = mean(iac); iac_rms = sqrt(mean(iac.^2)); pos = max(iac); neg = min(iac);\n' ...
'ref = iref .* abs(sin(th)) .* sign(sin(th));\n' ...
'if std(ref) > 1e-6 && std(iac) > 1e-6, cc = sum((iac-mean(iac)).*(ref-mean(ref))) / (n*std(iac,1)*std(ref,1)); else, cc = 0; end\n' ...
'ref_err = sqrt(mean((abs(iac) - abs(ref)).^2)) / max(iac_rms, 1e-3);\n' ...
'ph_i = atan2(-(iac''*s1), iac''*c1); ph_v = atan2(-(vac''*s1), vac''*c1); dphi = angle(exp(1i*(ph_i - ph_v)));\n' ...
'vdc_mean = mean(vdc); vdc_rip = max(vdc) - min(vdc); vdc_err = vdc_mean - mean(vr);\n' ...
'd_ff = 1 - abs(vac) ./ max(vdc, 50);\n' ...
'p_ac = mean(vac.*iac); p_chg = mean(vbat.*ibat); p_ratio = p_chg / max(p_ac, 50);\n' ...
'vbm = mean(vbat); ddm = mean(ddc);\n' ...
'row = [vac_mean, vac_amp, vac_mean/max(vac_amp,1), iac_mean, iac_rms, pos, neg, pos+neg, h2/max(h1,1e-3), h3/max(h1,1e-3), h1, ...\n' ...
'       cc, ref_err, iac_mean/max(h1,1e-3), dphi, vdc_mean, vdc_rip, vdc_err, mean(iref), min(iref), max(iref), mean(iref < 0), mean(d), mean(d) - mean(d_ff), ...\n' ...
'       vbm, mean(ibat), ddm, mean(st), mean(irb), max(vbat)-min(vbat), max(ibat)-min(ibat), p_ac, p_chg, p_ratio, ...\n' ...
'       ddm*vdc_mean/max(vbm,50) - 1, vbm - ddm*vdc_mean];\n' ...
'if all(prev == 0)\n' ...
'    dl = zeros(1, 7);\n' ...
'else\n' ...
'    dl = [row(16)-prev(16), row(19)-prev(19), row(5)-prev(5), row(4)-prev(4), row(25)-prev(25), row(26)-prev(26), row(34)-prev(34)];\n' ...
'end\n' ...
'prev = row;\n' ...
'f = [row, dl];\n']);
end

function s = augment_code()
% features.py::baseline_relative (EMA over previous cycles, 3-cycle warm-up) + variant one-hot
s = sprintf(['function [x, stn] = emi_augment(f, st, onehot, alpha)\n' ...
'%%#codegen\n' ...
'%% st = [ema(1:43), n_cycles_seen]\n' ...
'ema = st(1:43); cnt = st(44);\n' ...
'warm = 3;\n' ...
'if cnt < warm\n' ...
'    ema = (ema*cnt + f) / (cnt + 1);      %% running mean of the warm-up cycles\n' ...
'    dev = zeros(1, 43);\n' ...
'else\n' ...
'    dev = f - ema;\n' ...
'    ema = (1 - alpha)*ema + alpha*f;\n' ...
'end\n' ...
'stn = [ema, cnt + 1];\n' ...
'x = f;   %% 43 base features only (baseline-relative block and one-hot did not help); dev / onehot kept for later\n']);
end

function s = decide_code()
s = sprintf(['function [chan, cls, conf, amp, cntn] = emi_decide(raw, thr, persist, cnt)\n' ...
'%%#codegen\n' ...
'%% raw = [5 channel logits, 10 class logits, 1 amplitude]\n' ...
'pc = 1 ./ (1 + exp(-raw(1:5)));\n' ...
'hit = double(pc >= thr);\n' ...
'cntn = (cnt + 1) .* hit;                 %% consecutive cycles above threshold\n' ...
'chan = double(cntn >= persist);\n' ...
'z = raw(6:15); z = z - max(z); p = exp(z) / sum(exp(z));\n' ...
'[conf, i] = max(p); cls = i - 1;         %% 0 none .. 9 multi (features.CLASSES order)\n' ...
'amp = raw(16);\n']);
end
