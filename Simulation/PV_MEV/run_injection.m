function out = run_injection(mode, tests, variants, opts)
% RUN_INJECTION  Sensor-chain injection test bench for PV_MEV
% (docs/EMI_INJECTION_TEST_PLAN.md, sections 6 to 9).
%
%   run_injection('baseline', variants)         B0': 0 -> 0.6 s undisturbed,
%                                               save results/emi/snapshots/<V>.mat
%   run_injection('run', tests, variants, opts) cases from tests.csv, from the
%                                               snapshot (0.6 s) to 1.3 s;
%                                               tests = {'E-DC-01b',...} | 'P1' | 'P2' | 'all'
%   run_injection('merge')                      results/emi/*.csv -> scorecard.csv
%   run_injection('resummarize')                recompute transient metrics (over/under-
%                                               shoot, t_settle, t_rec) from ts/ files
%   run_injection('smoke', [], 'CRPR')          snapshot continuity check (0.6 -> 0.72 s
%                                               from snapshot vs. straight 0 -> 0.72 s)
%   run_injection('baseline', [], V, struct('op','cv'))   CV-segment snapshot (Voc 345 V)
%   run_injection('dataset', [k0 k1], variants, opts)      detector dataset: runs D<k0>..D<k1>
%                                               with randomized injections / benign events
%                                               (seeded by k), results/emi/dataset/, labels.csv
%
% opts: stop_time (override 1.3), force (rerun even if the result exists),
%       tag (suffix for smoke files), op ('cc' | 'cv' operating point).
% One summary row per run -> results/emi/<test>_<variant>.csv; 10 kHz time
% series -> results/emi/ts/<test>_<variant>.csv; 1 MHz Iac -> ..._iac.mat.
% Several MATLAB processes can share the matrix: a run whose summary file
% exists is skipped.
if nargin < 2, tests = []; end
if nargin < 3, variants = []; end
if nargin < 4, opts = struct(); end
opts = defaults(opts, struct('stop_time', 1.3, 'force', false, 'tag', '', 'op', 'cc'));

mdl  = 'PV_MEV';
mdir = fileparts(mfilename('fullpath')); cd(mdir); addpath(mdir);
rdir = fullfile(mdir, 'results', 'emi'); sdir = fullfile(rdir, 'snapshots'); tdir = fullfile(rdir, 'ts');
for d = {rdir, sdir, tdir}, if ~exist(d{1}, 'dir'), mkdir(d{1}); end, end

cfg = readtable(fullfile(mdir, 'config.csv'), 'TextType', 'string');
if isempty(variants), variants = cellstr(cfg.VARIANT_NAME(1:6)'); end
if ischar(variants) || isstring(variants), variants = cellstr(variants); end
T = readtable(fullfile(mdir, 'tests.csv'), 'TextType', 'string');

switch lower(mode)
    case 'baseline'
        for v = 1:numel(variants)
            try, make_snapshot(mdl, string(variants{v}), sdir, rdir, opts);
            catch ME, fprintf(2, '[%s] baseline FAILED: %s\n', variants{v}, getReport(ME, 'extended', 'hyperlinks', 'off')); close_system(mdl, 0); end
        end
        out = [];
    case 'run'
        ids = select_tests(T, tests);
        for i = 1:numel(ids)
            row = T(T.test_id == ids{i}, :);
            for v = 1:numel(variants)
                name = string(variants{v});
                fsum = fullfile(rdir, sprintf('%s_%s.csv', row.test_id, name));
                if exist(fsum, 'file') && ~opts.force, fprintf('[skip] %s\n', fsum); continue; end
                try, run_case(mdl, row, name, opts, rdir, sdir, tdir);
                catch ME
                    fprintf(2, '[%s %s] FAILED: %s\n', row.test_id, name, getReport(ME, 'extended', 'hyperlinks', 'off'));
                    write_failed(fsum, row, name, ME.message); close_system(mdl, 0);
                end
            end
        end
        out = merge_results(rdir);
    case 'merge'
        out = merge_results(rdir);
    case 'resummarize'
        out = resummarize(rdir, tdir);
    case 'dataset'
        out = run_dataset(mdl, tests, variants, opts, rdir, sdir);
    case 'smoke'
        out = smoke(mdl, string(variants{1}), sdir, rdir, opts);
    otherwise
        error('unknown mode %s', mode);
end
end

% =========================================================================
function ids = select_tests(T, tests)
if isempty(tests) || (ischar(tests) && strcmpi(tests, 'all')), ids = cellstr(T.test_id'); return; end
if ischar(tests) || isstring(tests)
    t = string(tests);
    if any(t == ["P1", "P2"]), ids = cellstr(T.test_id(T.priority == t)'); return; end
    ids = cellstr(t);
else
    ids = cellstr(tests);
end
for i = 1:numel(ids)
    if ~any(T.test_id == ids{i}), error('test %s not in tests.csv', ids{i}); end
end
end

function o = defaults(o, d)
f = fieldnames(d);
for i = 1:numel(f), if ~isfield(o, f{i}) || isempty(o.(f{i})), o.(f{i}) = d.(f{i}); end, end
end

function INJ = inj_from_row(row)
ch = containers.Map({'', 'Vdc', 'Vac', 'Iac', 'Vbat', 'Ibat'}, {0, 1, 2, 3, 4, 5});
sh = containers.Map({'', 'step', 'ramp', 'sine', 'tri', 'pulse', 'hall'}, {1, 1, 2, 3, 4, 5, 6});
c2 = ''; s2 = ''; a2 = 0;
if ismember('channel2', row.Properties.VariableNames)
    c2 = string(row.channel2); s2 = string(row.shape2); a2 = row.amp2;
    if ismissing(c2), c2 = ""; end
    if ismissing(s2), s2 = ""; end
    c2 = char(c2); s2 = char(s2);
    if isempty(a2) || isnan(a2), a2 = 0; end
end
INJ = struct('channel', [ch(char(row.channel)) ch(c2)], 'shape', [sh(char(row.shape)) sh(s2)], ...
    'amp', [row.amp a2], 'k', [row.k row.k], 'f', [row.f row.f], 'phase', [row.phase row.phase], ...
    'period', row.period, 'duty', row.duty, 't_on', row.t_on, 'dwell', row.dwell, 'K_hall', row.K_hall);
end

% =========================================================================
function prepare(mdl, name, INJ, op, EVT)
% op: 'cc' (Voc 335 V) or 'cv' (Voc 345 V); EVT: benign-event struct or []
if nargin < 4 || isempty(op), op = 'cc'; end
if nargin < 5, EVT = []; end
CHG_OP = struct(); if strcmpi(op, 'cv'), CHG_OP.Voc = 345; end
assignin('base', 'VARIANT_NAME', name);
assignin('base', 'INJ', INJ);
assignin('base', 'CHG_OP', CHG_OP);
assignin('base', 'EVT', EVT);
evalin('base', 'init_paras');
load_system(mdl);
if ~evalin('base', 'ENABLE_HIL')
    tcp = {'/EV System/PFC Control/Enabled Subsystem', '/EV System/PFC Control/HIL TCP Receive1', ...
           '/EV System/PFC Control/HIL TCP Send1', '/EV System/PFC Control/Original vs HIL Predict'};
    for k = 1:numel(tcp), try, set_param([mdl tcp{k}], 'Commented', 'on'); catch, end, end
end
set_logging(mdl, evalin('base', 'Ts_Power'));
end

function set_logging(mdl, Ts_Power)
ev = [mdl '/EV System']; pc = [ev '/PFC Control']; M = [ev '/Measurements 1'];
d200 = num2str(max(1, round(10e-6 / Ts_Power)));       % 10 us  (100 kHz)
d20  = num2str(max(1, round(1e-6  / Ts_Power)));       % 1 us   (1 MHz)
L = { ...
    [ev '/From16'], 1, 'Vdc_real', d200;  [ev '/From18'], 1, 'Vac_real', d200;  [ev '/From19'], 1, 'Iac_real', d20; ...
    [ev '/inj_ch1'], 1, 'Vdc_int', d200;  [ev '/inj_ch2'], 1, 'Vac_int', d200;  [ev '/inj_ch3'], 1, 'Iac_int', d200; ...
    [ev '/Charger Stage'], 1, 'chg', '';  [ev '/Protection Monitor'], 1, 'trip', ''; ...
    [pc '/Speed Regulator2'], 1, 'Iref', ''; [pc '/Saturation'], 1, 'D', ''; [pc '/PLL'], 2, 'theta', ''; ...
    [pc '/Multiport Switch'], 1, 'amp_est', ''; ...
    M, 1, 'Vdc_mean', d200; M, 2, 'PacPdc', d200; M, 3, 'THD_model', d200; M, 5, 'PF', d200};   % these run at Ts_Power
for i = 1:size(L, 1)
    ph = get_param(L{i, 1}, 'PortHandles'); h = ph.Outport(L{i, 2});
    set_param(h, 'DataLogging', 'on', 'DataLoggingNameMode', 'Custom', 'DataLoggingName', L{i, 3});
    if ~isempty(L{i, 4})
        set_param(h, 'DataLoggingDecimateData', 'on', 'DataLoggingDecimation', L{i, 4});
    end
end
end

% =========================================================================
function make_snapshot(mdl, name, sdir, rdir, opts)
tsnap = 0.6; if nargin > 4 && isfield(opts, 'snap_time') && ~isempty(opts.snap_time), tsnap = opts.snap_time; end
op = 'cc'; if nargin > 4 && isfield(opts, 'op') && ~isempty(opts.op), op = lower(opts.op); end
sfx = ''; if strcmp(op, 'cv'), sfx = '_cv'; end
prepare(mdl, name, struct(), op);
fprintf('[%s%s] baseline 0 -> %g s ...\n', name, sfx, tsnap); t0 = tic;
so = sim(mdl, 'StopTime', num2str(tsnap), 'SaveFinalState', 'on', 'SaveOperatingPoint', 'on', ...
    'FinalStateName', 'xFinal', 'SignalLogging', 'on', 'SignalLoggingName', 'logsout', 'ReturnWorkspaceOutputs', 'on');
wall = toc(t0);
xFinal = so.xFinal; %#ok<NASGU>
save(fullfile(sdir, sprintf('%s%s.mat', name, sfx)), 'xFinal');
% baseline metrics over the last 100 ms
S = extract(so.logsout);
m = metrics_window(S, [tsnap - 0.1, tsnap]);
r = struct('VARIANT_NAME', name, 'Vdc_V', m.Vdc, 'Pac_kW', m.Pac, 'Pdc_kW', m.Pdc, 'PF', m.PF, ...
    'THD50_pct', m.THD50, 'THD_full_pct', m.THD_full, 'I2_pct', m.I2, 'P_charge_kW', m.P_charge, ...
    'Ibat_A', m.Ibat, 'Vbat_V', m.Vbat, 'state', m.state, 'D_dcdc', m.D_dcdc, 'Iref_A', m.Iref, 'trip', m.trip, 'sim_wall_s', wall);
r.op = string(op);
writetable(struct2table(r), fullfile(rdir, sprintf('baseline_%s%s.csv', name, sfx)));
fprintf('[%s%s] snapshot saved (%.0f s): Vdc=%.1f Pdc=%.3f kW Pcharge=%.3f kW Ibat=%.2f A state=%d THD50=%.2f%% trip=%d\n', ...
    name, sfx, wall, m.Vdc, m.Pdc, m.P_charge, m.Ibat, m.state, m.THD50, m.trip);
write_ts(S, fullfile(rdir, 'ts', sprintf('baseline_%s%s', name, sfx)));
close_system(mdl, 0);
end

% =========================================================================
function run_case(mdl, row, name, opts, rdir, sdir, tdir)
INJ = inj_from_row(row);
snap = fullfile(sdir, sprintf('%s.mat', name));
if ~exist(snap, 'file'), error('snapshot missing: %s (run baseline first)', snap); end
s = load(snap); assignin('base', 'xInitial', s.xFinal);
prepare(mdl, name, INJ);
fprintf('[%s %s] 0.6 -> %g s ...\n', row.test_id, name, opts.stop_time); t0 = tic;
so = sim(mdl, 'LoadInitialState', 'on', 'InitialState', 'xInitial', 'StopTime', num2str(opts.stop_time), ...
    'SignalLogging', 'on', 'SignalLoggingName', 'logsout', 'ReturnWorkspaceOutputs', 'on');
wall = toc(t0);
S = extract(so.logsout);
r = summarize(S, row, name, INJ);
r.sim_wall_s = wall; r.status = "OK";
writetable(struct2table(r), fullfile(rdir, sprintf('%s_%s.csv', row.test_id, name)));
write_ts(S, fullfile(tdir, sprintf('%s_%s', row.test_id, name)));
fprintf('[%s %s] done %.0f s: dVdc=%+.1f V I_dc=%+.2f A THD50 %.2f->%.2f%% PF=%.4f Pchg %.2f->%.2f kW trip=%d t_rec=%.0f ms\n', ...
    row.test_id, name, wall, r.dVdc_V, r.I_dc_A, r.THD50_pre_pct, r.THD50_dur_pct, r.PF_dur, r.P_charge_pre_kW, r.P_charge_dur_kW, r.trip, r.t_rec_ms);
close_system(mdl, 0);
end

function write_failed(fsum, row, name, msg)
r = struct('test_id', row.test_id, 'VARIANT_NAME', name, 'status', "FAILED", 'note', string(msg));
writetable(struct2table(r), fsum);
end

% =========================================================================
function T = run_dataset(mdl, krange, variants, opts, rdir, sdir)
% Randomized runs for the EMI-detector dataset (plan phase 2, section 2.3).
% Each run k is fully determined by its seed, so several processes can take
% disjoint k ranges.  Results: results/emi/dataset/<run_id>_<variant>.csv (summary
% row), dataset/ts/<run_id>_<variant>.csv + _iac.mat, dataset/labels/<run_id>.csv.
ddir = fullfile(rdir, 'dataset'); ldir = fullfile(ddir, 'labels'); dts = fullfile(ddir, 'ts');
for d = {ddir, ldir, dts}, if ~exist(d{1}, 'dir'), mkdir(d{1}); end, end
if isempty(krange), krange = [1 1]; end
if isscalar(krange), krange = [1 krange]; end
for k = krange(1):krange(2)
    rng(k, 'twister');
    run_id = sprintf('D%04d', k);
    name = string(variants{randi(numel(variants))});
    focus = ''; if isfield(opts, 'focus') && ~isempty(opts.focus), focus = char(opts.focus); end
    L = sample_labels(run_id, name, sdir, focus);
    fsum = fullfile(ddir, sprintf('%s_%s.csv', run_id, name));
    if exist(fsum, 'file') && ~opts.force, fprintf('[skip] %s\n', fsum); continue; end
    try
        snap = fullfile(sdir, sprintf('%s%s.mat', name, L.snap_sfx));
        s = load(snap); assignin('base', 'xInitial', s.xFinal);
        prepare(mdl, name, L.INJ, L.op, L.EVT);
        % record 0.3 s of recovery after the bias is removed (post window of summarize)
        stopT = max(opts.stop_time, L.INJ.t_on + L.INJ.dwell + 0.30);
        fprintf('[%s %s %s] %s (to %.2f s) ...\n', run_id, name, L.op, L.desc, stopT); t0 = tic;
        so = sim(mdl, 'LoadInitialState', 'on', 'InitialState', 'xInitial', 'StopTime', num2str(stopT), ...
            'SignalLogging', 'on', 'SignalLoggingName', 'logsout', 'ReturnWorkspaceOutputs', 'on');
        wall = toc(t0);
        S = extract(so.logsout);
        r = summarize(S, L.row, name, L.INJ);
        r.sim_wall_s = wall; r.status = "OK";
        writetable(struct2table(r), fsum);
        write_ts(S, fullfile(dts, sprintf('%s_%s', run_id, name)));
        L.lab.status = "OK"; writetable(struct2table(L.lab), fullfile(ldir, [run_id '.csv']));
        fprintf('[%s %s] done %.0f s: THD50 %.2f->%.2f%% Pchg %.2f->%.2f kW trip=%d\n', run_id, name, wall, ...
            r.THD50_pre_pct, r.THD50_dur_pct, r.P_charge_pre_kW, r.P_charge_dur_kW, r.trip);
    catch ME
        fprintf(2, '[%s %s] FAILED: %s\n', run_id, name, getReport(ME, 'extended', 'hyperlinks', 'off'));
        L.lab.status = "FAILED"; writetable(struct2table(L.lab), fullfile(ldir, [run_id '.csv']));
        write_failed(fsum, L.row, name, ME.message); close_system(mdl, 0);
    end
    close_system(mdl, 0);
end
T = merge_labels(ldir, ddir);
end

function L = sample_labels(run_id, name, sdir, focus)
% Draw one dataset run (uses the current rng state).  Amplitude ranges from
% the plan (section 2.3); channel codes 1 Vdc 2 Vac 3 Iac 4 Vbat 5 Ibat.
% focus = 'iac': supplement for the rare classes (single Iac-chain injection,
% shape sine 40 % / hall 40 % / step 20 %, no benign-only runs).
if nargin < 4, focus = ''; end
chn = {'Vdc', 'Vac', 'Iac', 'Vbat', 'Ibat'}; shn = {'step', 'ramp', 'sine', 'tri', 'pulse', 'hall', 'noise'};
u = @() rand();
% operating point: 25 % CV segment when the snapshot exists
op = 'cc'; sfx = '';
if u() < 0.25 && exist(fullfile(sdir, sprintf('%s_cv.mat', name)), 'file'), op = 'cv'; sfx = '_cv'; end
% injection type
x = u(); if x < 0.25, n_inj = 0; elseif x < 0.85, n_inj = 1; else, n_inj = 2; end
if strcmp(focus, 'iac'), n_inj = 1; end
t_on = 0.65 + 0.25 * u(); dwell = 0.10 + 0.20 * u(); if t_on + dwell > 1.25, dwell = 1.25 - t_on; end
INJ = struct('channel', [0 0 0], 'shape', [1 1 1], 'amp', [0 0 0], 'k', [0 0 0], 'f', [50 50 50], 'phase', [0 0 0], ...
    'period', 0.05 + 0.15 * u(), 'duty', 0.3 + 0.4 * u(), 't_on', t_on, 'dwell', dwell, 'K_hall', 20);
used = [];
for j = 1:n_inj
    ch = randi(5); while any(used == ch), ch = randi(5); end, used(end + 1) = ch; %#ok<AGROW>
    x = u(); if x < 0.50, sh = 1; elseif x < 0.65, sh = 2; elseif x < 0.80, sh = 3; elseif x < 0.90, sh = 6; elseif x < 0.95, sh = 5; else, sh = 4; end
    if strcmp(focus, 'iac'), ch = 3; x = u(); if x < 0.4, sh = 3; elseif x < 0.8, sh = 6; else, sh = 1; end, end
    if sh == 6 && ch ~= 3, sh = 1; end                       % hall model only on the Iac chain
    switch ch
        case 1, a = 20 + 100 * u();  case 2, a = 5 + 35 * u();  case 3, a = 1 + 19 * u();
        case 4, a = 2 + 23 * u();    case 5, a = 1 + 7 * u();
    end
    if u() < 0.4, a = -a; end
    if ch == 3 && sh == 3, a = abs(a); end
    INJ.channel(j) = ch; INJ.shape(j) = sh; INJ.amp(j) = a;
    INJ.k(j) = abs(a) / (0.05 + 0.25 * u());
    if sh == 3, INJ.f(j) = 50; INJ.phase(j) = 360 * u(); end
    if sh == 6, INJ.f(j) = 100 * (1 + 9 * (u() < 0.3)); end   % 100 Hz (70 %) or 1 kHz
end
% measurement noise slot (30 %): benign
noise_ch = 0; noise_amp = 0;
if u() < 0.30
    noise_ch = randi(3); noise_amp = [2 + 3 * u(), 3 + 7 * u(), 0.5 + 1.5 * u()]; noise_amp = noise_amp(noise_ch);
    INJ.channel(3) = noise_ch; INJ.shape(3) = 7; INJ.amp(3) = noise_amp;
end
% benign transients
EVT = struct('chg_t', 0, 'chg_I', 20, 'vref_t', 0, 'vref_dV', 0);
if u() < 0.30, EVT.chg_t = 0.65 + 0.45 * u(); c = [5 10 15 20]; EVT.chg_I = c(randi(4)); end
if u() < 0.20, EVT.vref_t = 0.65 + 0.45 * u(); EVT.vref_dV = (10 + 20 * u()) * sign(u() - 0.5); end
% row for summarize() and the label record
c2 = ""; s2 = ""; a2 = 0;
if n_inj == 2, c2 = string(chn{INJ.channel(2)}); s2 = string(shn{INJ.shape(2)}); a2 = INJ.amp(2); end
c1 = ""; s1 = ""; if n_inj >= 1, c1 = string(chn{INJ.channel(1)}); s1 = string(shn{INJ.shape(1)}); end
row = table(string(run_id), c1, s1, INJ.amp(1), INJ.k(1), INJ.f(1), INJ.phase(1), INJ.period, INJ.duty, t_on, dwell, 20, c2, s2, a2, "D", ...
    'VariableNames', {'test_id', 'channel', 'shape', 'amp', 'k', 'f', 'phase', 'period', 'duty', 't_on', 'dwell', 'K_hall', 'channel2', 'shape2', 'amp2', 'priority'});
lab = struct('run_id', string(run_id), 'VARIANT_NAME', name, 'op', string(op), 'n_inj', n_inj, ...
    'channel1', c1, 'shape1', s1, 'amp1', INJ.amp(1), 'k1', INJ.k(1), 'f1', INJ.f(1), 'phase1', INJ.phase(1), ...
    'channel2', c2, 'shape2', s2, 'amp2', a2, 'k2', INJ.k(2), 'f2', INJ.f(2), 'phase2', INJ.phase(2), ...
    'period', INJ.period, 'duty', INJ.duty, 't_on', t_on, 'dwell', dwell, ...
    'noise_ch', string(ifelse(noise_ch > 0, chn, noise_ch)), 'noise_amp', noise_amp, ...
    'chg_t', EVT.chg_t, 'chg_I', EVT.chg_I, 'vref_t', EVT.vref_t, 'vref_dV', EVT.vref_dV, 'status', "PENDING");
desc = sprintf('inj=%d', n_inj);
for j = 1:n_inj, desc = sprintf('%s %s/%s/%+.1f', desc, chn{INJ.channel(j)}, shn{INJ.shape(j)}, INJ.amp(j)); end
if noise_ch > 0, desc = sprintf('%s noise(%s %.1f)', desc, chn{noise_ch}, noise_amp); end
if EVT.chg_t > 0, desc = sprintf('%s chg->%gA@%.2f', desc, EVT.chg_I, EVT.chg_t); end
if EVT.vref_t > 0, desc = sprintf('%s vref%+.0fV@%.2f', desc, EVT.vref_dV, EVT.vref_t); end
L = struct('INJ', INJ, 'EVT', EVT, 'op', op, 'snap_sfx', sfx, 'row', row, 'lab', lab, 'desc', desc);
end

function s = ifelse(c, names, idx)
if c, s = names{idx}; else, s = ''; end
end

function T = merge_labels(ldir, ddir)
f = dir(fullfile(ldir, 'D*.csv')); T = table();
for i = 1:numel(f)
    Ti = readtable(fullfile(ldir, f(i).name), 'TextType', 'string'); T = outerjoin_rows(T, Ti);
end
if ~isempty(T), T = sortrows(T, 'run_id'); writetable(T, fullfile(ddir, 'labels.csv')); end
end

% =========================================================================
function S = extract(L)
% logsout -> struct of [t, x] per signal (x may be a matrix)
S = struct();
for i = 1:L.numElements
    e = L.getElement(i); v = e.Values;
    x = squeeze(v.Data); if size(x, 1) ~= numel(v.Time), x = x.'; end
    S.(e.Name) = struct('t', v.Time, 'x', double(x));
end
end

function write_ts(S, base)
% 10 kHz resampled table of the main signals + 1 MHz Iac in a .mat
t = (ceil(S.Vdc_real.t(1)*1e4):floor(S.Vdc_real.t(end)*1e4))' / 1e4;
rs = @(n, c) resample_prev(S.(n).t, S.(n).x(:, c), t);
Tb = table(t, rs('Vdc_real', 1), rs('Vdc_int', 1), rs('Vac_real', 1), rs('Vac_int', 1), rs('Iac_real', 1), rs('Iac_int', 1), ...
    rs('chg', 1), rs('chg', 3), rs('chg', 2), rs('chg', 4), rs('Iref', 1), rs('theta', 1), rs('D', 1), rs('chg', 5), rs('chg', 6), ...
    rs('chg', 7), rs('chg', 8), rs('PacPdc', 1), rs('PacPdc', 2), rs('PF', 1), rs('trip', 1), ...
    'VariableNames', {'t', 'Vdc_real', 'Vdc_int', 'Vac_real', 'Vac_int', 'Iac_real', 'Iac_int', 'Vbat_real', 'Vbat_int', ...
    'Ibat_real', 'Ibat_int', 'Iref', 'theta_pll', 'D', 'D_dcdc', 'state', 'Iref_bat', 'P_charge', 'Pac', 'Pdc', 'PF', 'trip'});
if isfield(S, 'amp_est') && size(S.amp_est.x, 2) >= 3
    for h = 1:3, Tb.(sprintf('amp_est_%d', 2*h+1)) = rs('amp_est', h); end
end
writetable(Tb, [base '.csv']);
t_iac = S.Iac_real.t; Iac = single(S.Iac_real.x); %#ok<NASGU>
save([base '_iac.mat'], 't_iac', 'Iac');
end

function y = resample_prev(ts, xs, t)
if numel(ts) < 2, y = repmat(xs(1), numel(t), 1); return; end
[ts, iu] = unique(ts, 'last'); xs = xs(iu);
y = interp1(ts, xs, t, 'previous', 'extrap');
end

% =========================================================================
function m = metrics_window(S, w)
in = @(n) S.(n).t >= w(1) & S.(n).t <= w(2);
if ~any(in('Iac_real')) || ~any(in('chg'))          % window outside the record -> all NaN
    for f = {'Vdc','Pac','Pdc','PF','Iref','D','Vbat','Ibat','D_dcdc','P_charge','state','trip','THD50','THD_full','Iac_rms','I2','I_dc','I_peak','e_I_rms','Vdc_max','Vdc_min'}
        m.(f{1}) = NaN;
    end
    return;
end
mw = @(n, c) mean(S.(n).x(in(n), c));
m.Vdc  = mw('Vdc_real', 1);
m.Pac  = mw('PacPdc', 1); m.Pdc = mw('PacPdc', 2); m.PF = mw('PF', 1);
m.Iref = mw('Iref', 1);  m.D = mw('D', 1);
m.Vbat = mw('chg', 1); m.Ibat = mw('chg', 2); m.D_dcdc = mw('chg', 5); m.P_charge = mw('chg', 8) / 1e3;
st = S.chg.x(in('chg'), 6); m.state = st(end);
tr = S.trip.x(in('trip'), :); m.trip = tr(end, 1);
ia = in('Iac_real'); [m.THD50, m.THD_full, m.Iac_rms, m.I2, m.I_dc] = offline_thd(S.Iac_real.t(ia), S.Iac_real.x(ia, 1), 50);
m.I_peak = max(abs(S.Iac_real.x(ia, 1)));
% tracking error Iref*|sin theta| - |Iac|
ti = S.Iac_real.t(ia);
iref = interp1(S.Iref.t, S.Iref.x(:, 1), ti, 'previous', 'extrap');
th   = interp1(S.theta.t, S.theta.x(:, 1), ti, 'linear', 'extrap');
m.e_I_rms = rms(iref .* abs(sin(th)) - abs(S.Iac_real.x(ia, 1)));
m.Vdc_max = max(S.Vdc_real.x(in('Vdc_real'), 1)); m.Vdc_min = min(S.Vdc_real.x(in('Vdc_real'), 1));
end

function r = summarize(S, row, name, INJ)
t_on = INJ.t_on; t_off = INJ.t_on + INJ.dwell;
wpre = [t_on - 0.10, t_on]; wdur = [t_off - 0.15, t_off]; wpost = [t_off + 0.20, t_off + 0.30];
pre = metrics_window(S, wpre); dur = metrics_window(S, wdur); post = metrics_window(S, wpost);
r.test_id = row.test_id; r.VARIANT_NAME = name; r.priority = row.priority;
r.channel = row.channel; r.shape = row.shape; r.amp = row.amp; r.k = row.k; r.f = row.f; r.phase = row.phase;
r.channel2 = string(row.channel2); if ismissing(r.channel2), r.channel2 = ""; end
r.amp2 = INJ.amp(2); r.t_on = t_on; r.dwell = INJ.dwell;
% measurement error self-check (internal - real) in the dwell window
chan = {'Vdc', 'Vac', 'Iac', 'Vbat', 'Ibat'};
for c = 1:5
    switch c
        case {1, 2, 3}, ti = S.([chan{c} '_int']); tr = S.([chan{c} '_real']);
                        d = ti.x(:, 1) - interp1(tr.t, tr.x(:, 1), ti.t, 'previous', 'extrap'); tt = ti.t;
        case 4, d = S.chg.x(:, 3) - S.chg.x(:, 1); tt = S.chg.t;
        case 5, d = S.chg.x(:, 4) - S.chg.x(:, 2); tt = S.chg.t;
    end
    r.(sprintf('e_meas_%s', chan{c})) = mean(d(tt >= wdur(1) & tt <= wdur(2)));
end
r.dVdc_V = dur.Vdc - 400;
r.Vdc_pre_V = pre.Vdc; r.Vdc_dur_V = dur.Vdc; r.Vdc_post_V = post.Vdc;
on = metrics_window(S, [t_on, t_on + 0.10]);
r.e_I_rms_A = dur.e_I_rms; r.I_dc_A = dur.I_dc; r.I_peak_A = dur.I_peak; r.I_peak_on_A = on.I_peak;
r.I2_pre_pct = pre.I2; r.I2_dur_pct = dur.I2;
r.THD50_pre_pct = pre.THD50; r.THD50_dur_pct = dur.THD50; r.THD50_post_pct = post.THD50;
r.THD_full_pre_pct = pre.THD_full; r.THD_full_dur_pct = dur.THD_full; r.THD_full_post_pct = post.THD_full;
r.PF_pre = pre.PF; r.PF_dur = dur.PF; r.PF_post = post.PF;
r.Pac_dur_kW = dur.Pac; r.Pdc_dur_kW = dur.Pdc;
r.P_charge_pre_kW = pre.P_charge; r.P_charge_dur_kW = dur.P_charge; r.P_charge_post_kW = post.P_charge;
r.power_retention_pct = 100 * dur.P_charge / pre.P_charge;
r.Ibat_dur_A = dur.Ibat; r.Vbat_dur_V = dur.Vbat; r.Iref_pre_A = pre.Iref; r.Iref_dur_A = dur.Iref;
r.D_dcdc_dur = dur.D_dcdc; r.state_dur = dur.state; r.state_post = post.state;
% CC/CV switch time
st = S.chg.x(:, 6); ts = S.chg.t; k = find(ts > t_on & [false; diff(st) ~= 0], 1);
if isempty(k), r.t_switch_ms = NaN; else, r.t_switch_ms = 1e3 * (ts(k) - t_on); end
% protection
tr = S.trip.x(end, :); r.trip = tr(1);
if tr(1) > 0, r.t_trip_ms = 1e3 * (tr(2) - t_on); else, r.t_trip_ms = NaN; end
% transient metrics (shared with 'resummarize')
tm = transient_metrics(S.Vdc_real.t, S.Vdc_real.x(:, 1), S.chg.t, S.chg.x(:, 8) / 1e3, S.Iac_real.t, S.Iac_real.x(:, 1), ...
    t_on, t_off, pre.Vdc, dur.Vdc, pre.P_charge, pre.THD50);
f = fieldnames(tm); for i = 1:numel(f), r.(f{i}) = tm.(f{i}); end
end

function tm = transient_metrics(tV, Vdc, tP, P, tI, Iac, t_on, t_off, Vdc_pre, Vdc_dur, P_pre, THD_pre)
% Over/undershoot relative to the nearer plateau, on the raw signal (so the
% 100 Hz ripple is included); settling / recovery on a 20 ms moving mean so
% the ripple does not defeat the +-1 % band.
% Vdc_over_on: max(Vdc, first 100 ms after t_on)  - max(Vdc_pre, Vdc_dur)
% Vdc_under_on: min(...)                          - min(Vdc_pre, Vdc_dur)
% Vdc_over_off / Vdc_under_off: same after t_off, plateaus Vdc_dur and 400 V
mV = movmean(Vdc, max(1, round(0.02 / median(diff(tV)))));
mP = movmean(P,   max(1, round(0.02 / median(diff(tP)))));
w = tV >= t_on & tV <= t_on + 0.10;
tm.Vdc_over_on_V = max(Vdc(w)) - max(Vdc_pre, Vdc_dur);  tm.Vdc_under_on_V = min(Vdc(w)) - min(Vdc_pre, Vdc_dur);
w = tV >= t_off & tV <= t_off + 0.10;
tm.Vdc_over_off_V = max(Vdc(w)) - max(Vdc_dur, 400);     tm.Vdc_under_off_V = min(Vdc(w)) - min(Vdc_dur, 400);
% settling after injection start: |mean20ms(Vdc) - Vdc_dur| < 1 % of 400 V.
% The centred moving mean must not look past t_off (next step) or into the
% truncated window at the record end (half a ripple cycle), hence the 10 ms guards.
tm.t_settle_ms = 1e3 * last_violation(tV, abs(mV - Vdc_dur) >= 4, [t_on, t_off - 0.01]);
% recovery after injection end: Vdc +-1 %, P_charge +-1 % of pre, THD50 (per cycle) <= pre + 0.5 pp
tv = last_violation(tV, abs(mV - 400) >= 4, [t_off, tV(end) - 0.01]);
tp = last_violation(tP, abs(mP - P_pre) >= 0.01 * max(P_pre, 0.1), [t_off, tP(end) - 0.01]);
[tc, thd_c] = thd_per_cycle(tI, Iac, t_off, tI(end));
tt = last_violation(tc, thd_c > THD_pre + 0.5, [t_off, tI(end)]);
tm.t_rec_Vdc_ms = 1e3 * tv; tm.t_rec_P_ms = 1e3 * tp; tm.t_rec_THD_ms = 1e3 * tt;
tm.t_rec_ms = 1e3 * max([tv, tp, tt]);
end

% -------------------------------------------------------------------------
function T = resummarize(rdir, tdir)
% Recompute the transient metrics of every existing summary row from the
% saved 10 kHz time series + 1 MHz Iac, then rebuild the scorecard.
f = dir(fullfile(rdir, 'E-*.csv'));
for i = 1:numel(f)
    fs = fullfile(rdir, f(i).name); R = readtable(fs, 'TextType', 'string');
    if ~ismember('status', R.Properties.VariableNames) || R.status(1) ~= "OK", continue; end
    base = fullfile(tdir, erase(f(i).name, '.csv'));
    if ~exist([base '.csv'], 'file') || ~exist([base '_iac.mat'], 'file'), continue; end
    X = readtable([base '.csv']); M = load([base '_iac.mat']);
    tm = transient_metrics(X.t, X.Vdc_real, X.t, X.P_charge / 1e3, M.t_iac, double(M.Iac), R.t_on, R.t_on + R.dwell, ...
        R.Vdc_pre_V, R.Vdc_dur_V, R.P_charge_pre_kW, R.THD50_pre_pct);
    fn = fieldnames(tm); for k = 1:numel(fn), R.(fn{k}) = tm.(fn{k}); end
    writetable(R, fs); fprintf('[resummarize] %s  t_rec=%.0f ms\n', f(i).name, R.t_rec_ms);
end
T = merge_results(rdir);
end

function tau = last_violation(t, bad, w)
% seconds after w(1) of the last sample violating the criterion within w; 0 if none
m = t >= w(1) & t <= w(2); tm = t(m); bm = bad(m);
k = find(bm, 1, 'last');
if isempty(k), tau = 0; else, tau = tm(k) - w(1); end
end

function [tc, thd] = thd_per_cycle(t, x, t0, t1)
n = floor((t1 - t0) * 50); tc = zeros(n, 1); thd = zeros(n, 1);
for i = 1:n
    a = t0 + (i - 1) / 50; b = a + 1 / 50; m = t >= a & t < b;
    thd(i) = offline_thd(t(m), x(m), 50); tc(i) = b;
end
end

% -------------------------------------------------------------------------
function [thd50, thdfull, irms, i2, idc] = offline_thd(t, x, nh)
% FFT over an integer number of 50 Hz cycles at (nearly) uniform sampling.
x = double(x(:)); t = t(:);
fsr = 1 / median(diff(t));
ncyc = max(1, floor((t(end) - t(1)) * 50 + 1e-6));
n = round(ncyc * fsr / 50); n = min(n, numel(x));
x = x(end - n + 1:end);
idc = mean(x); x = x - idc;
X = abs(fft(x)) / n; X = X(1:floor(n / 2));
df = fsr / n; k1 = round(50 / df);
A1 = X(k1 + 1);
harm = 0;
for h = 2:nh
    k = round(h * 50 / df); if k + 1 <= numel(X), harm = harm + X(k + 1)^2; end
end
thd50   = 100 * sqrt(harm) / A1;
allpow  = sum(X(2:end).^2) - A1^2;
thdfull = 100 * sqrt(max(allpow, 0)) / A1;
irms    = sqrt(mean(x.^2));
k2 = round(100 / df); i2 = 100 * X(k2 + 1) / A1;
end

% =========================================================================
function T = merge_results(rdir)
f = dir(fullfile(rdir, 'E-*.csv'));
T = table();
for i = 1:numel(f)
    Ti = readtable(fullfile(rdir, f(i).name), 'TextType', 'string');
    if ~ismember('status', Ti.Properties.VariableNames) || Ti.status ~= "OK", Ti = Ti(:, {'test_id', 'VARIANT_NAME', 'status'}); end
    T = outerjoin_rows(T, Ti);
end
if isempty(T), return; end
T = sortrows(T, {'test_id', 'VARIANT_NAME'});
writetable(T, fullfile(rdir, 'scorecard.csv'));
cols = intersect({'test_id', 'VARIANT_NAME', 'dVdc_V', 'Vdc_under_on_V', 'I_dc_A', 'I_peak_A', 'THD50_pre_pct', 'THD50_dur_pct', ...
    'PF_dur', 'P_charge_dur_kW', 'power_retention_pct', 'trip', 't_trip_ms', 't_rec_ms', 'status'}, T.Properties.VariableNames, 'stable');
disp(T(:, cols));
end

function T = outerjoin_rows(T, Ti)
if isempty(T), T = Ti; return; end
a = setdiff(Ti.Properties.VariableNames, T.Properties.VariableNames);
b = setdiff(T.Properties.VariableNames, Ti.Properties.VariableNames);
for k = 1:numel(a), T.(a{k}) = repmat(missing_like(Ti.(a{k})), height(T), 1); end
for k = 1:numel(b), Ti.(b{k}) = repmat(missing_like(T.(b{k})), height(Ti), 1); end
T = [T; Ti(:, T.Properties.VariableNames)];
end
function v = missing_like(c)
if isnumeric(c), v = NaN; elseif isstring(c), v = string(missing); else, v = {''}; end
end

% =========================================================================
function out = smoke(mdl, name, sdir, rdir, opts)
% Continuity check of the ModelOperatingPoint restart: straight run 0 -> t1
% vs. snapshot run 0.6 -> t1, compared on 0.6 -> t1 (undisturbed).
t1 = 0.72;
snap = fullfile(sdir, sprintf('%s.mat', name));
if ~exist(snap, 'file'), make_snapshot(mdl, name, sdir, rdir); end
s = load(snap); assignin('base', 'xInitial', s.xFinal);
prepare(mdl, name, struct());
fprintf('[smoke] restart 0.6 -> %g s\n', t1); t0 = tic;
so1 = sim(mdl, 'LoadInitialState', 'on', 'InitialState', 'xInitial', 'StopTime', num2str(t1), ...
    'SignalLogging', 'on', 'SignalLoggingName', 'logsout', 'ReturnWorkspaceOutputs', 'on');
fprintf('[smoke] restart took %.0f s\n', toc(t0));
S1 = extract(so1.logsout); close_system(mdl, 0);
prepare(mdl, name, struct());
fprintf('[smoke] straight 0 -> %g s\n', t1); t0 = tic;
so2 = sim(mdl, 'StopTime', num2str(t1), 'SignalLogging', 'on', 'SignalLoggingName', 'logsout', 'ReturnWorkspaceOutputs', 'on');
fprintf('[smoke] straight took %.0f s\n', toc(t0));
S2 = extract(so2.logsout); close_system(mdl, 0);
t = (0.6005:1e-4:t1 - 1e-4)';
out = struct();
for n = {'Vdc_real', 'Iac_real', 'Iref', 'chg'}
    c = 1; if strcmp(n{1}, 'chg'), c = 2; end
    a = interp1(S1.(n{1}).t, S1.(n{1}).x(:, c), t, 'previous'); b = interp1(S2.(n{1}).t, S2.(n{1}).x(:, c), t, 'previous');
    out.(n{1}) = struct('rms_diff', rms(a - b), 'max_diff', max(abs(a - b)), 'rms_ref', rms(b));
    fprintf('[smoke] %-9s rms diff %.4g  max diff %.4g  (rms %.4g)\n', n{1}, out.(n{1}).rms_diff, out.(n{1}).max_diff, out.(n{1}).rms_ref);
end
write_ts(S1, fullfile(rdir, 'ts', ['smoke_restart_' char(name) opts.tag]));
write_ts(S2, fullfile(rdir, 'ts', ['smoke_straight_' char(name) opts.tag]));
end
