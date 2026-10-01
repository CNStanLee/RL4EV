function run_attack(variant, stop_time, onset)
%RUN_ATTACK  Run the ReThink IL attack scenarios under a chosen test.csv control
% mode (variant), on the instrumented PV_MEV copy. Attack starts at `onset`
% (after the system has reached steady state) and runs to `stop_time`.
%   variant    : VARIANT_NAME from test.csv (e.g. 'MPCC_D', 'CRPR')
%   stop_time  : total sim time (s), default 1.6
%   onset      : attack start time (s), default 1.0 (post-settle)
if nargin<2||isempty(stop_time), stop_time=1.6; end
if nargin<3||isempty(onset), onset=1.0; end
proj='/mnt/data6/playground/RL4EV/Simulation/PV_MEV'; model='PV_MEV';
exp_mdir=fullfile(proj,'exp','model');
rdir=fullfile(proj,'exp','results',['attack_' char(variant)]);
if ~exist(rdir,'dir'), mkdir(rdir); end
warning('off','MATLAB:rmpath:DirNotFound'); rmpath(proj); addpath(exp_mdir); cd(exp_mdir);
evalin('base', ['run(''' fullfile(exp_mdir,'init_paras.m') ''')']);
load_system(fullfile(exp_mdir,[model '.slx']));
sysb=find_system(model,'LookUnderMasks','all','FollowLinks','on','IncludeCommented','on','MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb), if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end, end
hws=get_param(model,'ModelWorkspace');

% ---- control-mode config from test.csv ----
T=readtable(fullfile(proj,'test.csv'),'TextType','string');
row=T(T.VARIANT_NAME==string(variant),:);
assert(~isempty(row),'variant %s not in test.csv',variant);
Fc=row.Fc(1);
assignin(hws,'Fc',Fc); assignin(hws,'Ts_Control',1/Fc);
assignin(hws,'use_d_predict',row.use_d_predict(1)); assignin(hws,'use_p_predict',row.use_p_predict(1));
assignin(hws,'use_harmonic',row.use_harmonic(1)); assignin(hws,'estimation_src',row.estimation_src(1));

% ---- attack scenarios (amplitudes scaled to MPCC IL ~70 A rms) ----
T0=onset;
S={
 'S00_baseline',      [0 1 T0 999   0  50 0 0], 'Baseline (no attack)'
 'S01_bias_p30',      [1 1 T0 999  30  50 0 0], 'Bias +30 A'
 'S02_bias_p60',      [1 1 T0 999  60  50 0 0], 'Bias +60 A (strong)'
 'S03_sine_A30_f50',  [1 2 T0 999  30  50 0 0], 'Sine 50 Hz 30 A (DoS)'
 'S04_sine_A60_f50',  [1 2 T0 999  60  50 0 0], 'Sine 50 Hz 60 A (strong DoS)'
 'S05_scale_g1p3',    [1 5 T0 999 1.3 50 0 0], 'Scaling x1.3'
 'S06_scale_g0p6',    [1 5 T0 999 0.6 50 0 0], 'Scaling x0.6'
};
names={'iL_true','iL_meas','iL_delta','Vdc_mean','Pac_Pdc_kW','THD_sys','Vdc_ripple_sys','PF','Vdc_inst','Iac','Vac'};
pre=[onset-0.1 onset]; post=[stop_time-0.1 stop_time];
K=struct([]);
for s=1:size(S,1)
    tag=S{s,1}; p=S{s,2}; label=S{s,3};
    assignin(hws,'atk_params',p(:)');
    t0=tic; out=sim(model,'StopTime',num2str(stop_time),'ReturnWorkspaceOutputs','on','SrcWorkspace','base'); wall=toc(t0);
    res=struct('tag',tag,'label',label,'variant',string(variant),'atk_params',p,'onset',onset,'stop',stop_time);
    for k=1:numel(names)
        nm=names{k}; try, ts=out.(nm); res.(nm).t=ts.Time; res.(nm).y=squeeze(ts.Data); catch, end
    end
    save(fullfile(rdir,['run_' tag '.mat']),'res','-v7.3');
    kk.tag=tag; kk.label=label; kk.variant=string(variant);
    kk.THD_pre=wm(out,'THD_sys',pre); kk.THD_post=wm(out,'THD_sys',post);
    kk.ripple_post=wm(out,'Vdc_ripple_sys',post); kk.Vdc_post=wm(out,'Vdc_mean',post);
    kk.Pac_post=wm(out,'Pac_Pdc_kW',post,1); kk.PF_post=wm(out,'PF',post);
    kk.Vdc_peak=wmax(out,'Vdc_inst',post); kk.delta_rms=wrms(out,'iL_delta',post); kk.wall=wall;
    if isempty(K), K=kk; else, K(end+1)=kk; end %#ok<AGROW>
    fprintf('[%s] %-16s THD %6.2f->%6.2f  ripple %5.2f Vdc %6.1f(pk %6.1f) P %6.2f PF %.3f (%.0fs)\n', ...
        variant, tag, kk.THD_pre, kk.THD_post, kk.ripple_post, kk.Vdc_post, kk.Vdc_peak, kk.Pac_post, kk.PF_post, wall);
end
Tt=struct2table(K); writetable(Tt, fullfile(rdir,'attack_kpis.csv'));
save(fullfile(rdir,'attack_summary.mat'),'K','variant','onset','stop_time','-v7.3');
fprintf('ATTACK_DONE[%s] -> %s\n', variant, fullfile(rdir,'attack_kpis.csv'));
close_system(model,0);
end
function v=wm(out,nm,win,chan)
if nargin<4, chan=1; end
try, ts=out.(nm); catch, ts=out.get(nm); end
t=ts.Time; y=squeeze(ts.Data); if ~isvector(y), if size(y,1)<size(y,2), y=y(chan,:).'; else, y=y(:,chan); end, end
k=t>=win(1)&t<=win(2); v=mean(y(k));
end
function v=wmax(out,nm,win), ts=out.(nm); t=ts.Time; y=squeeze(ts.Data); k=t>=win(1)&t<=win(2); v=max(abs(y(k))); end
function v=wrms(out,nm,win), ts=out.(nm); t=ts.Time; y=squeeze(ts.Data); k=t>=win(1)&t<=win(2); v=sqrt(mean(y(k).^2)); end
