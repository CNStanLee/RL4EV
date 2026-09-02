function results = run_benchmark(variants, opts)
% RUN_BENCHMARK  Simulate PV_MEV for controller variants listed in config.csv
% and collect steady-state / transient metrics of the EV charger (EV System).
%
%   run_benchmark()                      all variants in config.csv
%   run_benchmark({'CRPR','MPCC_D'})     subset
%   run_benchmark('merge')               only merge results/*.csv into
%                                        results/benchmark_results.csv
%   run_benchmark(v, struct('stop_time',0.05))   override simu_time (smoke test)
%
% Per-variant rows are written to results/<VARIANT>.csv so several MATLAB
% processes can run different subsets in parallel; the merged table is
% results/benchmark_results.csv.  The model file is never saved.
%
% Metrics (window = last 100 ms = 5 fundamental cycles, after the 0.4 s load step):
%   Vdc_V, Vdc_ripple_pct, Pdc_kW, Pac_kW, eff_pct, PF  (from Measurements 1)
%   THD_model_pct   THD block inside Measurements 1 (sampled at Ts_Control,
%                   so it is NOT comparable across different Fc)
%   THD50_pct       offline FFT of Iac sampled at 1 MHz, harmonics 2..50 (<=2.5 kHz)
%   THD_full_pct    offline, all non-fundamental content up to 500 kHz
%   Iac_rms_A, Iref_A (voltage-loop output), D_mean
%   Vdc_min_step_V  minimum Vdc after the 0.4 s load step
%   t_settle_ms     time after 0.4 s until |Vdc-400| < 1 % and stays there
%   sim_wall_s      wall-clock time of the run
if nargin < 1 || isempty(variants), variants = []; end
if nargin < 2, opts = struct(); end
if ~isfield(opts,'stop_time'), opts.stop_time = []; end

mdl  = 'PV_MEV';
mdir = fileparts(mfilename('fullpath'));
rdir = fullfile(mdir, 'results');
if ~exist(rdir,'dir'), mkdir(rdir); end
cd(mdir); addpath(mdir);

if ischar(variants) && strcmpi(variants,'merge')
    results = merge_results(rdir); return;
end
cfg = readtable(fullfile(mdir,'config.csv'),'TextType','string');
if isempty(variants), variants = cellstr(cfg.VARIANT_NAME'); end
if ischar(variants) || isstring(variants), variants = cellstr(variants); end

for v = 1:numel(variants)
    name = string(variants{v});
    try
        run_one(mdl, name, cfg, opts, rdir);
    catch ME
        fprintf(2,'[%s] FAILED: %s\n', name, ME.message);
        close_system(mdl, 0);
    end
end
results = merge_results(rdir);
end

% -------------------------------------------------------------------------
function run_one(mdl, name, cfg, opts, rdir)
row = cfg(cfg.VARIANT_NAME == name, :);
if height(row) ~= 1, error('variant %s not in config.csv', name); end
assignin('base','VARIANT_NAME', name);
evalin('base','init_paras');                      % same as the model InitFcn
stopT = evalin('base','simu_time');
if ~isempty(opts.stop_time), stopT = opts.stop_time; end
enable_hil = evalin('base','ENABLE_HIL');
Ts_Power   = evalin('base','Ts_Power');

load_system(mdl);
if ~enable_hil
    % TCP/IP blocks need an external server; disable them in memory only.
    tcp = {'/EV System/PFC Control/Enabled Subsystem', '/EV System/PFC Control/HIL TCP Receive1', ...
           '/EV System/PFC Control/HIL TCP Send1', '/EV System/PFC Control/Original vs HIL Predict'};
    for k = 1:numel(tcp)
        try, set_param([mdl tcp{k}], 'Commented', 'on'); catch, end
    end
end
% --- signal logging
M = [mdl '/EV System/Measurements 1'];
ph = get_param(M,'PortHandles');
lognames = {'Vdc','PacPdc','THD','Ripple','PF'};
for p = 1:5
    set_param(ph.Outport(p),'DataLogging','on','DataLoggingNameMode','Custom','DataLoggingName',lognames{p});
end
q = get_param([mdl '/EV System/PFC Control/Speed Regulator2'],'PortHandles');
set_param(q.Outport(1),'DataLogging','on','DataLoggingNameMode','Custom','DataLoggingName','Iref');
q = get_param([mdl '/EV System/PFC Control/Saturation'],'PortHandles');
set_param(q.Outport(1),'DataLogging','on','DataLoggingNameMode','Custom','DataLoggingName','D');
% Iac at Ts_Power, decimated to 1 MHz for the offline THD
dec = max(1, round(1e-6 / Ts_Power));
q = get_param([M '/Iac'],'PortHandles');
set_param(q.Outport(1),'DataLogging','on','DataLoggingNameMode','Custom','DataLoggingName','Iac', ...
    'DataLoggingDecimateData','on','DataLoggingDecimation',num2str(dec));

fprintf('[%s] simulating %g s ...\n', name, stopT); t0 = tic;
so = sim(mdl,'StopTime',num2str(stopT),'SignalLogging','on','SignalLoggingName','logsout', ...
         'ReturnWorkspaceOutputs','on');
wall = toc(so_tic(t0));
L = so.logsout;
get_sig = @(n) L.get(n).Values;

% --- window: last 100 ms
Tw = 0.1;
Vdc  = get_sig('Vdc');     w = Vdc.Time >= Vdc.Time(end) - Tw;
Pp   = get_sig('PacPdc');  wp = Pp.Time >= Pp.Time(end) - Tw;  Pp_d = squeeze(Pp.Data); if size(Pp_d,1)~=numel(Pp.Time), Pp_d = Pp_d'; end
THDm = get_sig('THD');     Rip = get_sig('Ripple');  PF = get_sig('PF');
Iref = get_sig('Iref');    wi = Iref.Time >= Iref.Time(end) - Tw;
D    = get_sig('D');       wd = D.Time >= D.Time(end) - Tw;
Iac  = get_sig('Iac');     wa = Iac.Time >= Iac.Time(end) - Tw;

r.VARIANT_NAME   = name;
r.Fc_Hz          = row.Fc;
r.use_d_predict  = row.use_d_predict;  r.use_p_predict = row.use_p_predict;
r.use_harmonic   = row.use_harmonic;   r.estimation_src = row.estimation_src;
r.stop_time_s    = stopT;
r.Vdc_V          = mean(Vdc.Data(w));
r.Vdc_ripple_pct = mean(Rip.Data(Rip.Time >= Rip.Time(end)-Tw));
r.Pac_kW         = mean(Pp_d(wp,1));
r.Pdc_kW         = mean(Pp_d(wp,2));
r.eff_pct        = 100 * r.Pdc_kW / r.Pac_kW;
r.PF             = mean(PF.Data(PF.Time >= PF.Time(end)-Tw));
r.THD_model_pct  = mean(THDm.Data(THDm.Time >= THDm.Time(end)-Tw));
[r.THD50_pct, r.THD_full_pct, r.Iac_rms_A] = offline_thd(Iac.Time(wa), double(Iac.Data(wa)), 50);
r.Iref_A         = mean(Iref.Data(wi));
r.D_mean         = mean(D.Data(wd));
% --- load-step transient (step at 0.4 s)
ts = Vdc.Time; vd = Vdc.Data;
if stopT > 0.5
    m = ts >= 0.4 & ts <= 0.5;  r.Vdc_min_step_V = min(vd(m));
    ok = abs(vd - 400) < 4 & ts >= 0.4;                % within 1 %
    bad = find(ts >= 0.4 & ~ok, 1, 'last');
    if isempty(bad), r.t_settle_ms = 0; else, r.t_settle_ms = 1e3*(ts(bad) - 0.4); end
else
    r.Vdc_min_step_V = NaN; r.t_settle_ms = NaN;
end
r.sim_wall_s = wall;
T = struct2table(r);
writetable(T, fullfile(rdir, sprintf('%s.csv', name)));
fprintf('[%s] done in %.0f s: Vdc=%.1f V Pdc=%.3f kW Pac=%.3f kW THD50=%.2f%% THD_full=%.2f%% (model THD %.2f%%)\n', ...
    name, wall, r.Vdc_V, r.Pdc_kW, r.Pac_kW, r.THD50_pct, r.THD_full_pct, r.THD_model_pct);
close_system(mdl, 0);
end

function t = so_tic(t0), t = t0; end

% -------------------------------------------------------------------------
function [thd50, thdfull, irms] = offline_thd(t, x, nh)
% FFT over an integer number of 50 Hz cycles at (nearly) uniform sampling.
fsr = 1/median(diff(t));
ncyc = floor((t(end)-t(1)) * 50);
n = round(ncyc * fsr / 50);
x = x(end-n+1:end); x = x - mean(x);
X = abs(fft(x .* hann_flat(n))) / n; X = X(1:floor(n/2));
df = fsr / n;  k1 = round(50/df);
A1 = X(k1+1);
harm = 0;
for h = 2:nh
    k = round(h*50/df); if k+1 <= numel(X), harm = harm + X(k+1)^2; end
end
thd50   = 100*sqrt(harm)/A1;
allpow  = sum(X(2:end).^2) - A1^2;
thdfull = 100*sqrt(max(allpow,0))/A1;
irms    = sqrt(mean(x.^2));
end
function w = hann_flat(n), w = ones(n,1); end   % rectangular: integer cycles -> no leakage

% -------------------------------------------------------------------------
function T = merge_results(rdir)
f = dir(fullfile(rdir,'*.csv')); f = f(~strcmp({f.name},'benchmark_results.csv'));
T = table();
for i = 1:numel(f)
    Ti = readtable(fullfile(rdir,f(i).name),'TextType','string');
    T = [T; Ti]; %#ok<AGROW>
end
if isempty(T), return; end
[~,ord] = sortrows([T.use_p_predict T.use_d_predict T.use_harmonic T.estimation_src]);
T = T(ord,:);
writetable(T, fullfile(rdir,'benchmark_results.csv'));
disp(T(:, {'VARIANT_NAME','Fc_Hz','Vdc_V','Pdc_kW','Pac_kW','eff_pct','PF','THD50_pct','THD_full_pct','THD_model_pct','Vdc_ripple_pct','Iref_A','Vdc_min_step_V','t_settle_ms','sim_wall_s'}));
end
