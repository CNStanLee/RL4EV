function build_mitigation(step)
% BUILD_MITIGATION  Detection-conditioned resilient MPCC (MPCC_R, plan step 2).
%
%   build_mitigation()          add the Mitigation block to PFC Control and the
%                               measurement corrections to the Charger Stage, save
%   build_mitigation('inspect') print the current wiring
%
% Base strategy: MPCC_H (= MPCC_D_H1, duty-predicting MPCC with the FFT1 + HGQ2
% fused harmonic estimate).  Everything here is conditional on the EMI detector
% flags (det_chan, 1x5 = Vdc Vac Iac Vbat Ibat) and amplitudes (det_amp, 1x5,
% signed, normalized by 100 V / 40 V / 20 A / 25 V / 8 A); with all flags zero the
% signal path is the identity and the controller equals MPCC_H tick for tick.
%
% Measures (bit k of mitigation_mask, init_paras / config.csv):
%   M0   1  Vdc correction: voltage-loop feedback Vdc_int - dV, dV from the charger
%           (Vbat_int / D_dcdc, valid while the charger regulates and Vbat is not
%           flagged) else from the detector amplitude; Iref floor 0 (no negative reference)
%   M1   2  Iref slew-rate limit while a Vdc flag is up (dVdc/dt through the outer loop)
%   M2   4  Vac feed-forward from the PLL: Vin = V_amp * sin(theta), V_amp from the
%           previous-cycle peak-to-peak / 2 (a DC bias cancels)
%   M3   8  Iac DC compensation: i_L - dI (dI = detector amplitude) into the predictor
%   M4  16  estimator hold: harmonic phasors frozen at their pre-flag value while Iac is flagged
%   M5  32  charger: Vbat_m - dV (keep CC instead of an early CV / stop)
%   M6  64  charger: Ibat_m - dI
%   M7 128  withdrawal: corrections ramp out over t_ramp (3 cycles) after a flag clears
%   M8 256  fusion weight pushed to the HGQ2 estimate while Vac is flagged
% use_detector = 0 disconnects the flags (MPCC_R_OFF); det_force = 1 forces every
% flag on with zero amplitudes (MPCC_R_ON, "always on" ablation).
%
% Signal path changes in PFC Control (see docs/RESILIENT_MPCC_AND_OFFLOAD_PLAN.md):
%   Rate Transition4 (Vdc_int) -> Speed Regulator2/2   becomes  -> Mitigation -> Vdc_fb -> Speed Regulator2/2
%   Speed Regulator2/1 -> Prod1/2                        becomes  -> Mitigation -> Iref_out -> Prod1/2
%   From22 (i_L)  -> D_predict/1, From20 (V_in) -> D_predict/3  go through Mitigation (iL_out, Vin_out)
%   From24/25 (amp_est, phase_est) -> D_predict/8,9      sample-and-hold driven by Mitigation 'hold'
%   'HGQ fusion alpha' -> HGQ FFT-DL Hybrid/5           alpha + g_alpha * (1 - alpha)
if nargin < 1, step = 'all'; end
mdir = fileparts(mfilename('fullpath')); cd(mdir); addpath(mdir);
mdl = 'PV_MEV'; load_system(mdl);
ev = [mdl '/EV System']; pc = [ev '/PFC Control']; mit = [pc '/Mitigation'];
if strcmp(step, 'inspect'), inspect(pc, ev); close_system(mdl, 0); return; end
if strcmp(step, 'fix_loop'), fix_loop(pc, mit); inspect(pc, ev); save_system(mdl); close_system(mdl); fprintf('[build_mitigation] loop fix saved\n'); return; end
if strcmp(step, 'update'), update_code(pc, ev, mit); inspect(pc, ev); save_system(mdl); close_system(mdl); fprintf('[build_mitigation] code update saved\n'); return; end
if strcmp(step, 'update2'), update_code(pc, ev, mit); update_charger_physics(ev); inspect(pc, ev); save_system(mdl); close_system(mdl); fprintf('[build_mitigation] charger physics update saved\n'); return; end

% ---------------------------------------------------------------- PFC Control
if getSimulinkBlockHandle(mit) ~= -1, error('Mitigation already present; remove it first'); end
add_block('simulink/User-Defined Functions/MATLAB Function', mit, 'Position', [5300 1500 5480 1760]);
set_mlfcn(mit, mitigation_code(), {'flags', '[1 5]'; 'amps', '[1 5]'; 'Vdc', '1'; 'Vac', '1'; 'th', '1'; 'iL', '1'; 'Iref', '1'; ...
    'chg', '[1 9]'; 'mask', '1'; 'use_det', '1'; 'force', '1'; 'Ts', '1'; 't_ramp', '1'; ...
    'Vdc_fb', '1'; 'Iref_out', '1'; 'Vin_out', '1'; 'iL_out', '1'; 'hold', '1'; 'g_alpha', '1'; 'dbg', '[1 6]'});
% inputs: detector flags / amplitudes (20 ms) and charger vector (Ts_chg) through rate transitions
srcs = {'det_chan', 'RT_mit_flags', 1; 'det_amp', 'RT_mit_amps', 2; 'chg_sig', 'RT_mit_chg', 8};
for i = 1:size(srcs, 1)
    f = sprintf('%s/From_%s', pc, srcs{i, 2});
    add_block('simulink/Signal Routing/From', f, 'GotoTag', srcs{i, 1}, 'Position', [5100 1500 + 40 * i, 5180 1520 + 40 * i]);
    r = sprintf('%s/%s', pc, srcs{i, 2});
    add_block('simulink/Signal Attributes/Rate Transition', r, 'OutPortSampleTime', 'Ts_Control', 'Position', [5210 1500 + 40 * i, 5250 1520 + 40 * i]);
    add_line(pc, sprintf('From_%s/1', srcs{i, 2}), sprintf('%s/1', srcs{i, 2}));
    add_line(pc, sprintf('%s/1', srcs{i, 2}), sprintf('Mitigation/%d', srcs{i, 3}), 'autorouting', 'on');
end
consts = {'mit_mask', 'mitigation_mask', 9; 'mit_use', 'use_detector', 10; 'mit_force', 'det_force', 11; 'mit_Ts', 'Ts_Control', 12; 'mit_tramp', 'mit_t_ramp', 13};
for i = 1:size(consts, 1)
    add_block('simulink/Sources/Constant', sprintf('%s/%s', pc, consts{i, 1}), 'Value', consts{i, 2}, 'Position', [5100 1700 + 30 * i, 5180 1720 + 30 * i]);
    add_line(pc, sprintf('%s/1', consts{i, 1}), sprintf('Mitigation/%d', consts{i, 3}), 'autorouting', 'on');
end
% Vdc_int: Rate Transition4 -> Speed Regulator2/2  =>  RT4 -> Mitigation/3, Mitigation/1 -> SR2/2
rewire(pc, 'Rate Transition4', 1, 'Speed Regulator2', 2, 'Mitigation', 3, 'Mitigation', 1);
% Iref amplitude: Speed Regulator2/1 -> Prod1/2  =>  SR2/1 -> Mitigation/7, Mitigation/2 -> Prod1/2
rewire(pc, 'Speed Regulator2', 1, 'Prod1', 2, 'Mitigation', 7, 'Mitigation', 2);
% i_L into the predictor: From22 -> D_predict/1  =>  From22 -> Mitigation/6, Mitigation/4 -> D_predict/1
rewire(pc, 'From22', 1, 'D_predict', 1, 'Mitigation', 6, 'Mitigation', 4);
% V_in into the predictor: From20 -> D_predict/3  =>  From20 -> Mitigation/4, Mitigation/3 -> D_predict/3
rewire(pc, 'From20', 1, 'D_predict', 3, 'Mitigation', 4, 'Mitigation', 3);
% theta into Mitigation/5 (From26 already feeds D_predict/7; add a second From)
add_block('simulink/Signal Routing/From', [pc '/From_mit_theta'], 'GotoTag', 'theta_pll', 'Position', [5100 1660 5180 1680]);
add_line(pc, 'From_mit_theta/1', 'Mitigation/5', 'autorouting', 'on');
% estimator sample-and-hold on amp_est / phase_est (dimension-agnostic: Switch + Unit Delay)
sh = {'From24', 8, 'hold_amp'; 'From25', 9, 'hold_phase'};
for i = 1:2
    sw = sprintf('%s/%s', pc, sh{i, 3}); ud = sprintf('%s/%s_z', pc, sh{i, 3});
    add_block('simulink/Signal Routing/Switch', sw, 'Criteria', 'u2 > Threshold', 'Threshold', '0.5', 'Position', [5560 1500 + 80 * i, 5600 1540 + 80 * i]);
    add_block('simulink/Discrete/Unit Delay', ud, 'SampleTime', 'Ts_Control', 'InitialCondition', '0', 'Position', [5620 1560 + 80 * i, 5660 1580 + 80 * i]);
    % From -> D_predict/k  =>  From -> Switch/3 (pass), Switch/1 <- Unit Delay (held), Switch/2 <- hold, Switch -> D_predict/k
    rewire(pc, sh{i, 1}, 1, 'D_predict', sh{i, 2}, sh{i, 3}, 3, sh{i, 3}, 1);
    add_line(pc, sprintf('%s/1', sh{i, 3}), sprintf('%s_z/1', sh{i, 3}), 'autorouting', 'on');
    add_line(pc, sprintf('%s_z/1', sh{i, 3}), sprintf('%s/1', sh{i, 3}), 'autorouting', 'on');
    add_line(pc, 'Mitigation/5', sprintf('%s/2', sh{i, 3}), 'autorouting', 'on');
end
% fusion weight: alpha_out = alpha + g_alpha * (1 - alpha)
hb = [pc '/HGQ FFT-DL Hybrid'];
delete_line_between(pc, 'HGQ fusion alpha', 1, hb, 5);
add_block('simulink/Sources/Constant', [pc '/mit_one'], 'Value', '1', 'Position', [5560 1720 5600 1740]);
add_block('simulink/Math Operations/Sum', [pc '/mit_1ma'], 'Inputs', '+-', 'Position', [5620 1715 5650 1745]);
add_block('simulink/Math Operations/Product', [pc '/mit_ga'], 'Position', [5680 1715 5710 1745]);
add_block('simulink/Math Operations/Sum', [pc '/mit_alpha'], 'Inputs', '++', 'Position', [5740 1715 5770 1745]);
add_line(pc, 'mit_one/1', 'mit_1ma/1'); add_line(pc, 'HGQ fusion alpha/1', 'mit_1ma/2', 'autorouting', 'on');
add_line(pc, 'mit_1ma/1', 'mit_ga/1'); add_line(pc, 'Mitigation/6', 'mit_ga/2', 'autorouting', 'on');
add_line(pc, 'HGQ fusion alpha/1', 'mit_alpha/1', 'autorouting', 'on'); add_line(pc, 'mit_ga/1', 'mit_alpha/2');
add_line(pc, 'mit_alpha/1', 'HGQ FFT-DL Hybrid/5', 'autorouting', 'on');
% debug vector -> global Goto (logged by run_injection as mit_*)
add_block('simulink/Signal Routing/Goto', [pc '/Goto_mit_dbg'], 'GotoTag', 'mit_dbg', 'TagVisibility', 'global', 'Position', [5560 1800 5660 1820]);
add_line(pc, 'Mitigation/7', 'Goto_mit_dbg/1', 'autorouting', 'on');

% ---------------------------------------------------------------- Charger Stage (M5, M6)
chg = [ev '/Charger Stage'];
set_param(chg, 'LinkStatus', 'none');                          % break the library link, keep the contents
cc = [chg '/chg_corr'];
add_block('simulink/User-Defined Functions/MATLAB Function', cc, 'Position', [600 560 700 640]);
set_mlfcn(cc, charger_code(), {'Vbat_m', '1'; 'Ibat_m', '1'; 'flags', '[1 5]'; 'amps', '[1 5]'; 'mask', '1'; 'use_det', '1'; 'force', '1'; 'Ts', '1'; 't_ramp', '1'; 'Vbat_c', '1'; 'Ibat_c', '1'});
for i = 1:2
    tags = {'det_chan', 'det_amp'};
    add_block('simulink/Signal Routing/From', sprintf('%s/From_det%d', chg, i), 'GotoTag', tags{i}, 'Position', [480 560 + 40 * i, 540 580 + 40 * i]);
    add_block('simulink/Signal Attributes/Rate Transition', sprintf('%s/RT_det%d', chg, i), 'OutPortSampleTime', 'Ts_chg', 'Position', [555 560 + 40 * i, 585 580 + 40 * i]);
    add_line(chg, sprintf('From_det%d/1', i), sprintf('RT_det%d/1', i)); add_line(chg, sprintf('RT_det%d/1', i), sprintf('chg_corr/%d', 2 + i), 'autorouting', 'on');
end
cst = {'cc_mask', 'mitigation_mask', 5; 'cc_use', 'use_detector', 6; 'cc_force', 'det_force', 7; 'cc_Ts', 'Ts_chg', 8; 'cc_tramp', 'mit_t_ramp', 9};
for i = 1:size(cst, 1)
    add_block('simulink/Sources/Constant', sprintf('%s/%s', chg, cst{i, 1}), 'Value', cst{i, 2}, 'Position', [480 660 + 30 * i, 540 680 + 30 * i]);
    add_line(chg, sprintf('%s/1', cst{i, 1}), sprintf('chg_corr/%d', cst{i, 3}), 'autorouting', 'on');
end
rewire(chg, 'inj_Vbat', 1, 'ctrl', 1, 'chg_corr', 1, 'chg_corr', 1);
rewire(chg, 'inj_Ibat', 1, 'ctrl', 2, 'chg_corr', 2, 'chg_corr', 2);
fix_loop(pc, mit);
inspect(pc, ev);
save_system(mdl); close_system(mdl);
fprintf('[build_mitigation] PV_MEV saved\n');
end

% =========================================================================
function update_code(pc, ev, mit)
% Re-set the MATLAB Function scripts (mitigation_code / iref_code / charger_code) and add the arming inputs:
% simulation time (Digital Clock) and det_t_arm.  The detector is trained on the settled plant only; during the
% 0 -> 0.6 s start-up it raises spurious flags (Vdc / Ibat on most cycles) which, without arming, corrupt the
% MPCC_R operating-point snapshot (bus 388 V, Iref 85 A, THD 6.8 % instead of 400 V / 46.5 A / 2.8 %).
set_mlfcn(mit, mitigation_code(), {'tnow', '1'; 't_arm', '1'});
if getSimulinkBlockHandle([pc '/mit_clock']) == -1
    add_block('simulink/Sources/Digital Clock', [pc '/mit_clock'], 'SampleTime', 'Ts_Control', 'Position', [5100 1850 5180 1870]);
    add_block('simulink/Sources/Constant', [pc '/mit_tarm'], 'Value', 'det_t_arm', 'Position', [5100 1890 5180 1910]);
    add_line(pc, 'mit_clock/1', 'Mitigation/14', 'autorouting', 'on');
    add_line(pc, 'mit_tarm/1', 'Mitigation/15', 'autorouting', 'on');
end
mi = [pc '/Mitigation Iref'];
if getSimulinkBlockHandle(mi) ~= -1, set_mlfcn(mi, iref_code()); end
chg = [ev '/Charger Stage']; cc = [chg '/chg_corr'];
set_mlfcn(cc, charger_code(), {'tnow', '1'; 't_arm', '1'});
if getSimulinkBlockHandle([chg '/cc_clock']) == -1
    add_block('simulink/Sources/Digital Clock', [chg '/cc_clock'], 'SampleTime', 'Ts_chg', 'Position', [480 850 540 870]);
    add_block('simulink/Sources/Constant', [chg '/cc_tarm'], 'Value', 'det_t_arm', 'Position', [480 890 540 910]);
    add_line(chg, 'cc_clock/1', 'chg_corr/10', 'autorouting', 'on');
    add_line(chg, 'cc_tarm/1', 'chg_corr/11', 'autorouting', 'on');
end
end

function update_charger_physics(ev)
% M5 from physics instead of the detector amplitude head: in the averaged buck Vbat = D_dcdc * Vdc in steady state,
% so a Vbat-chain bias reads as Vbat_m - D_dcdc * Vdc.  chg_corr gets the charger's Vdc input and the previous
% duty (Unit Delay on ctrl/1 to avoid an algebraic loop through the CC/CV controller).
chg = [ev '/Charger Stage']; cc = [chg '/chg_corr'];
set_mlfcn(cc, charger_code(), {'Vdc', '1'; 'D_prev', '1'});
if getSimulinkBlockHandle([chg '/cc_Dz']) == -1
    add_block('simulink/Discrete/Unit Delay', [chg '/cc_Dz'], 'SampleTime', 'Ts_chg', 'InitialCondition', '0', 'Position', [480 930 520 950]);
    add_line(chg, 'ctrl/1', 'cc_Dz/1', 'autorouting', 'on');
    add_line(chg, 'RTin/1', 'chg_corr/12', 'autorouting', 'on');
    add_line(chg, 'cc_Dz/1', 'chg_corr/13', 'autorouting', 'on');
end
end

function fix_loop(pc, mit)
% The Iref path (Speed Regulator2 -> Mitigation -> Prod1) and the Vdc path (Rate Transition4 -> Mitigation ->
% Speed Regulator2) share one MATLAB Function block, which Simulink treats as direct feedthrough on every input:
% an algebraic loop through the voltage regulator.  Move the Iref limiting into its own block 'Mitigation Iref'
% (fed by the ramp gain g_vdc from Mitigation's dbg output) and feed Mitigation input 7 a constant 0.
mi = [pc '/Mitigation Iref'];
if getSimulinkBlockHandle(mi) ~= -1, return; end
delete_line_between(pc, 'Speed Regulator2', 1, 'Mitigation', 7);
delete_line_between(pc, 'Mitigation', 2, 'Prod1', 2);
add_block('simulink/Sources/Constant', [pc '/mit_zero'], 'Value', '0', 'Position', [5100 1780 5180 1800]);
add_line(pc, 'mit_zero/1', 'Mitigation/7', 'autorouting', 'on');
add_block('simulink/User-Defined Functions/MATLAB Function', mi, 'Position', [5560 1860 5700 1960]);
set_mlfcn(mi, iref_code(), {'Iref', '1'; 'dbg', '[1 6]'; 'mask', '1'; 'Ts', '1'; 'Iref_out', '1'});
add_line(pc, 'Speed Regulator2/1', 'Mitigation Iref/1', 'autorouting', 'on');
add_line(pc, 'Mitigation/7', 'Mitigation Iref/2', 'autorouting', 'on');
add_line(pc, 'mit_mask/1', 'Mitigation Iref/3', 'autorouting', 'on');
add_line(pc, 'mit_Ts/1', 'Mitigation Iref/4', 'autorouting', 'on');
add_line(pc, 'Mitigation Iref/1', 'Prod1/2', 'autorouting', 'on');
set_mlfcn(mit, mitigation_code());          % Iref no longer used inside Mitigation (output 2 = 0)
end

function s = iref_code()
s = sprintf([ ...
'function Iref_out = mitigation_iref(Iref, dbg, mask, Ts)\n' ...
'%%#codegen\n' ...
'%% M0: no negative reference while the Vdc chain is flagged; M1: slew-rate limit (200 A/s) while flagged.\n' ...
'%% g_vdc = dbg(1) is the ramped Vdc-chain gain of the Mitigation block (build_mitigation.m).\n' ...
'persistent Iref_prev init\n' ...
'if isempty(init), Iref_prev = 0; init = 1; end\n' ...
'g1 = dbg(1);\n' ...
'Iref_out = Iref;\n' ...
'if bitand(uint32(mask), uint32(1)) > 0 && g1 > 0, Iref_out = max(Iref_out, 0); end\n' ...
'if bitand(uint32(mask), uint32(2)) > 0 && g1 > 0\n' ...
'    dmax = 200 * Ts;\n' ...
'    Iref_out = min(max(Iref_out, Iref_prev - dmax), Iref_prev + dmax);\n' ...
'end\n' ...
'Iref_prev = Iref_out;\n']);
end

% =========================================================================
function rewire(sys, srcb, srcp, dstb, dstp, newdstb, newdstp, newsrcb, newsrcp)
% replace the line srcb/srcp -> dstb/dstp by srcb/srcp -> newdstb/newdstp and newsrcb/newsrcp -> dstb/dstp
delete_line_between(sys, srcb, srcp, dstb, dstp);
add_line(sys, sprintf('%s/%d', srcb, srcp), sprintf('%s/%d', newdstb, newdstp), 'autorouting', 'on');
add_line(sys, sprintf('%s/%d', newsrcb, newsrcp), sprintf('%s/%d', dstb, dstp), 'autorouting', 'on');
end

function delete_line_between(sys, srcb, srcp, dstb, dstp)
if ~startsWith(dstb, sys), dstb = [sys '/' dstb]; end
if ~startsWith(srcb, sys), srcb = [sys '/' srcb]; end
ph = get_param(dstb, 'PortHandles'); l = get_param(ph.Inport(dstp), 'Line');
assert(l ~= -1, 'no line into %s/%d', dstb, dstp);
sb = get_param(l, 'SrcBlockHandle'); sp = get_param(l, 'SrcPortHandle');
assert(strcmp(getfullname(sb), srcb) && get_param(sp, 'PortNumber') == srcp, 'unexpected source of %s/%d: %s', dstb, dstp, getfullname(sb));
% the line may be a branch: delete only the segment to this destination
delete_line(sys, sp, ph.Inport(dstp));
end

function inspect(pc, ev)
for b = {[pc '/Mitigation'], [ev '/Charger Stage/chg_corr']}
    if getSimulinkBlockHandle(b{1}) == -1, fprintf('   (missing) %s\n', b{1}); continue; end
    ph = get_param(b{1}, 'PortHandles');
    fprintf('   %s: %d in, %d out\n', b{1}, numel(ph.Inport), numel(ph.Outport));
    for k = 1:numel(ph.Inport)
        l = get_param(ph.Inport(k), 'Line'); nm = '-';
        if l ~= -1, sb = get_param(l, 'SrcBlockHandle'); if sb ~= -1, nm = get_param(sb, 'Name'); end, end
        fprintf('      in %2d <- %s\n', k, nm);
    end
    for k = 1:numel(ph.Outport)
        l = get_param(ph.Outport(k), 'Line'); nm = '-';
        if l ~= -1, db = get_param(l, 'DstBlockHandle'); if all(db ~= -1), nm = strjoin(arrayfun(@(h) get_param(h, 'Name'), db, 'UniformOutput', false), ', '); end, end
        fprintf('      out %2d -> %s\n', k, nm);
    end
end
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

% =========================================================================
function s = mitigation_code()
s = sprintf([ ...
'function [Vdc_fb, Iref_out, Vin_out, iL_out, hold, g_alpha, dbg] = mitigation(flags, amps, Vdc, Vac, th, iL, Iref, chg, mask, use_det, force, Ts, t_ramp, tnow, t_arm)\n' ...
'%%#codegen\n' ...
'%% Detection-conditioned signal corrections for MPCC_R (build_mitigation.m).  Runs at Ts_Control.\n' ...
'%% flags/amps: detector channel flags and signed normalized amplitudes (Vdc Vac Iac Vbat Ibat)\n' ...
'%% chg = [Vbat_real Ibat_real Vbat_int Ibat_int D_dcdc state Iref_bat P_charge Idc]\n' ...
'persistent g dVf Iref_prev pkp pkn Vamp th_prev init\n' ...
'if isempty(init), g = zeros(1, 5); dVf = 0; Iref_prev = 0; pkp = 0; pkn = 0; Vamp = 0; th_prev = 0; init = 1; end\n' ...
'M = @(k) bitand(uint32(mask), uint32(2^k)) > 0;\n' ...
'f = flags .* (use_det > 0);\n' ...
'if force > 0, f = ones(1, 5); end\n' ...
'if tnow < t_arm, f = zeros(1, 5); end          %% detector armed only after start-up (det_t_arm)\n' ...
'if f(1) > 0.5, f(4) = 0; f(5) = 0; end         %% priority: a Vdc-chain flag explains the charger-side symptoms (Vbat / Ibat flags are consequences)\n' ...
'%% --- channel gains: Vdc immediate (a measurement correction must track the bias, not ramp), the rest ramp out over t_ramp (M7)\n' ...
'for c = 1:5\n' ...
'    if f(c) > 0.5, g(c) = 1;\n' ...
'    elseif M(7) && c ~= 1, g(c) = max(0, g(c) - Ts / max(t_ramp, Ts));\n' ...
'    else, g(c) = 0; end\n' ...
'end\n' ...
'%% --- Vdc chain: bias estimate dV = Vdc_int - Vdc_true\n' ...
'Vbat_i = chg(3); Ibat_i = chg(4); Ddc = chg(5);\n' ...
'dV_det = amps(1) * 100;\n' ...
'phys_ok = (Ddc > 0.3) && (Ddc < 0.98) && (Ibat_i > 1);\n' ...
'if phys_ok\n' ...
'    dV = Vdc - Vbat_i / Ddc;                    %% charger duty tells the true bus: Vbat = D_dcdc * Vdc_true\n' ...
'else\n' ...
'    dV = dV_det;\n' ...
'end\n' ...
'dV = min(max(dV, -120), 120);\n' ...
'if g(1) > 0, dVf = dVf + (Ts / 0.005) * (dV - dVf); else, dVf = 0; end\n' ...
'Vdc_fb = Vdc;\n' ...
'if M(0), Vdc_fb = Vdc - g(1) * dVf; end\n' ...
'%% --- Iref amplitude limits (M0 floor, M1 slew) live in the separate block ''Mitigation Iref'' (algebraic loop)\n' ...
'Iref_out = 0 * Iref + Iref_prev * 0;\n' ...
'%% --- Vac chain: PLL-reconstructed feed-forward voltage (peak-to-peak / 2 of the previous cycle)\n' ...
'if th < th_prev - 3                          %% wrap: new cycle\n' ...
'    Vamp = 0.5 * (pkp - pkn); pkp = 0; pkn = 0;\n' ...
'end\n' ...
'th_prev = th; pkp = max(pkp, Vac); pkn = min(pkn, Vac);\n' ...
'Vin_out = Vac;\n' ...
'if M(2) && g(2) > 0 && Vamp > 50, Vin_out = Vac + g(2) * (Vamp * sin(th) - Vac); end\n' ...
'%% --- Iac chain: DC compensation of the predictor current, estimator hold\n' ...
'iL_out = iL;\n' ...
'if M(3), iL_out = iL - g(3) * amps(3) * 20; end\n' ...
'hold = 0;\n' ...
'if M(4) && g(3) > 0, hold = 1; end\n' ...
'%% --- fusion weight towards the HGQ2 estimate while Vac is flagged\n' ...
'g_alpha = 0;\n' ...
'if M(8), g_alpha = g(2); end\n' ...
'dbg = [g(1), dVf, double(phys_ok), Vamp, g(3), hold];\n']);
end

function s = charger_code()
s = sprintf([ ...
'function [Vbat_c, Ibat_c] = chg_corr(Vbat_m, Ibat_m, flags, amps, mask, use_det, force, Ts, t_ramp, tnow, t_arm, Vdc, D_prev)\n' ...
'%%#codegen\n' ...
'%% M5 / M6: remove the detected Vbat / Ibat measurement bias before the CC/CV controller (build_mitigation.m)\n' ...
'persistent g dVf init\n' ...
'if isempty(init), g = zeros(1, 2); dVf = 0; init = 1; end\n' ...
'f = flags(4:5) .* (use_det > 0);\n' ...
'if force > 0, f = ones(1, 2); end\n' ...
'if tnow < t_arm || flags(1) > 0.5, f = zeros(1, 2); end   %% armed after start-up; a Vdc-chain flag overrides the charger-side flags\n' ...
'ramp = bitand(uint32(mask), uint32(128)) > 0;\n' ...
'for c = 1:2\n' ...
'    if f(c) > 0.5, g(c) = 1;\n' ...
'    elseif ramp, g(c) = max(0, g(c) - Ts / max(t_ramp, Ts));\n' ...
'    else, g(c) = 0; end\n' ...
'end\n' ...
'Vbat_c = Vbat_m; Ibat_c = Ibat_m;\n' ...
'phys_ok = (D_prev > 0.3) && (D_prev < 0.98) && (Ibat_m > 1) && (Vdc > 250);\n' ...
'if phys_ok, dV = Vbat_m - D_prev * Vdc; else, dV = amps(4) * 25; end   %% buck: Vbat = D * Vdc while regulating; detector amplitude as fallback\n' ...
'dV = min(max(dV, -60), 60);\n' ...
'if g(1) > 0, dVf = dVf + (Ts / 0.002) * (dV - dVf); else, dVf = 0; end\n' ...
'if bitand(uint32(mask), uint32(32)) > 0, Vbat_c = Vbat_m - g(1) * dVf; end\n' ...
'if bitand(uint32(mask), uint32(64)) > 0, Ibat_c = Ibat_m - g(2) * amps(5) * 8; end\n']);
end
