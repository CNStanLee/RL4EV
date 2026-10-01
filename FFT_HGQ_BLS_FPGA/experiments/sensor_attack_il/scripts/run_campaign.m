function run_campaign()
%RUN_CAMPAIGN  First experiment group: ReThink-style IL current-sensor attacks on
% the FFT+HGQ2-BLS MPCC. Runs baseline + a scenario set, logs signals, extracts
% steady-window KPIs, and writes per-run mats + a summary CSV.
proj  = '/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA';
model = 'PV_MEV_FFT_HGQ_BLS';
mdir  = fullfile(proj,'experiments','sensor_attack_il','model');
rdir  = fullfile(proj,'experiments','sensor_attack_il','results');
if ~exist(rdir,'dir'), mkdir(rdir); end
warning('off','MATLAB:rmpath:DirNotFound');
rmpath(fullfile(proj,'model')); addpath(mdir); cd(mdir);
evalin('base', ['run(''' fullfile(mdir,'init_paras.m') ''')']);
load_system(fullfile(mdir,[model '.slx']));
sysb = find_system(model,'LookUnderMasks','all','FollowLinks','on','IncludeCommented','on', ...
    'MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb)
    if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end
end
hws = get_param(model,'ModelWorkspace');
STOP = 0.15; T0 = 0.08;   % attack onset after DC-bus settles (~0.08 s)

% scenario table: tag, [enable mode t0 t1 A f phase offset], human label
S = {
 'S00_baseline',      [0 1 T0 999   0  50 0 0], 'Baseline (no attack)'
 'S01_bias_p30',      [1 1 T0 999  30  50 0 0], 'Bias +30 A (Hall DC offset)'
 'S02_bias_p60',      [1 1 T0 999  60  50 0 0], 'Bias +60 A'
 'S03_bias_p120',     [1 1 T0 999 120  50 0 0], 'Bias +120 A (strong)'
 'S04_bias_n60',      [1 1 T0 999 -60  50 0 0], 'Bias -60 A'
 'S05_sine_A60_f50',  [1 2 T0 999  60  50 0 0], 'Sine 50 Hz, 60 A (DoS strategy)'
 'S06_sine_A120_f50', [1 2 T0 999 120  50 0 0], 'Sine 50 Hz, 120 A (strong DoS)'
 'S07_sine_A60_f150', [1 2 T0 999  60 150 0 0], 'Sine 150 Hz, 60 A (3rd-harm inject)'
 'S08_amtri_A120_f10',[1 3 T0 999 120  10 0 0], 'AM triangular env, 120 A @10 Hz'
 'S09_amsin_A120_f10',[1 4 T0 999 120  10 0 0], 'AM sine env, 120 A @10 Hz'
 'S10_scale_g1p3',    [1 5 T0 999 1.3 50 0 0], 'Scaling gain x1.3 (amplify)'
 'S11_scale_g0p6',    [1 5 T0 999 0.6 50 0 0], 'Scaling gain x0.6 (attenuate)'
};

names = {'iL_true','iL_meas','iL_delta','Iref','predict_D','THD_pfc','Vdc','Iac','Vac', ...
         'iL_phys','Vdc_mean','Pac_Pdc_kW','THD_sys','Vdc_ripple_sys','PF'};
win = [0.10 0.15];   % steady KPI window
K = struct([]);
for s = 1:size(S,1)
    tag = S{s,1}; p = S{s,2}; label = S{s,3};
    assignin(hws,'atk_params',p(:)');
    t0=tic;
    out = sim(model,'StopTime',num2str(STOP),'ReturnWorkspaceOutputs','on','SrcWorkspace','base');
    wall = toc(t0);
    res = struct('tag',tag,'label',label,'atk_params',p,'wall',wall,'stop_time',STOP);
    for k=1:numel(names)
        nm=names{k};
        try, ts=out.(nm); catch, ts=out.get(nm); end
        res.(nm).t = ts.Time; res.(nm).y = squeeze(ts.Data);
    end
    save(fullfile(rdir,['run_' tag '.mat']),'res','-v7.3');
    % steady KPIs
    kk = kpis(res,win);  kk.tag=tag; kk.label=label; kk.wall=wall;
    kk.mode=p(2); kk.A=p(5); kk.f=p(6); kk.enable=p(1);
    if isempty(K), K=kk; else, K(end+1)=kk; end %#ok<AGROW>
    fprintf('DONE %-18s wall=%5.1fs THD=%6.2f ripple=%5.2f Vdc=%6.1f P=%6.2fkW PF=%.3f dRMS=%.1f\n', ...
        tag, wall, kk.THD_sys, kk.Vdc_ripple, kk.Vdc_mean, kk.Pac_kW, kk.PF, kk.delta_rms);
end
% write summary CSV
Tt = struct2table(K);
Tt = movevars(Tt,{'tag','label','enable','mode','A','f'},'Before',1);
writetable(Tt, fullfile(rdir,'summary_kpis.csv'));
save(fullfile(rdir,'campaign_summary.mat'),'K','S','win','STOP','T0','-v7.3');
fprintf('CAMPAIGN_DONE  %d runs -> %s\n', numel(K), fullfile(rdir,'summary_kpis.csv'));
close_system(model,0);
end

function kk = kpis(res,win)
mwin = @(nm) maskmean(res.(nm),win);
kk.THD_sys    = mwin('THD_sys');
kk.THD_pfc    = mwin('THD_pfc');
kk.Vdc_ripple = mwin('Vdc_ripple_sys');
kk.Vdc_mean   = mwin('Vdc_mean');
kk.Pac_kW     = mwin('Pac_Pdc_kW');
kk.PF         = mwin('PF');
% Vdc extremes over window (protection view)
[vmin,vmax,~] = mmwin(res.Vdc,win);
kk.Vdc_min = vmin; kk.Vdc_max = vmax;
% attack magnitude
kk.delta_rms = rmswin(res.iL_delta,win);
kk.delta_max = mmax(res.iL_delta,win);
% measured vs true current rms (what controller sees vs reality)
kk.iL_true_rms = rmswin(res.iL_true,win);
kk.iL_meas_rms = rmswin(res.iL_meas,win);
% grid current rms/peak
kk.Iac_rms = rmswin(res.Iac,win);
kk.Iac_peak = mmax(res.Iac,win);
end

function m = maskmean(s,win)
t=s.t; y=s.y; k=t>=win(1)&t<=win(2); m=mean(y(k));
end
function r = rmswin(s,win)
t=s.t; y=s.y; k=t>=win(1)&t<=win(2); r=sqrt(mean(y(k).^2));
end
function v = mmax(s,win)
t=s.t; y=s.y; k=t>=win(1)&t<=win(2); v=max(abs(y(k)));
end
function [lo,hi,mu]=mmwin(s,win)
t=s.t; y=s.y; k=t>=win(1)&t<=win(2); lo=min(y(k)); hi=max(y(k)); mu=mean(y(k));
end
