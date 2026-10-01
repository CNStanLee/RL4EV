function run_attack3(variant, stop_time, onset)
%RUN_ATTACK3  ReThink three-consequence demonstration on the EV side, using the
% IL current sensor AND the Vdc bus-voltage sensor, under a chosen control mode.
%   DoS(AC)  : IL sine injection -> oscillation
%   DoS(DC)  : Vdc measured UP  -> controller lowers real Vdc -> under-voltage
%   Damage   : Vdc measured DOWN-> controller raises real Vdc -> over-voltage
%   Damping  : IL gain>1 -> controller under-drives -> power reduced (stealthy)
if nargin<1||isempty(variant), variant='MPCC_D'; end
if nargin<2||isempty(stop_time), stop_time=1.6; end
if nargin<3||isempty(onset), onset=1.0; end
proj='/mnt/data6/playground/RL4EV/Simulation/PV_MEV'; model='PV_MEV';
exp_mdir=fullfile(proj,'exp','model'); rdir=fullfile(proj,'exp','results',['atk3_' char(variant)]);
if ~exist(rdir,'dir'), mkdir(rdir); end
warning('off','MATLAB:rmpath:DirNotFound'); rmpath(proj); addpath(exp_mdir); cd(exp_mdir);
evalin('base', ['run(''' fullfile(exp_mdir,'init_paras.m') ''')']);
load_system(fullfile(exp_mdir,[model '.slx']));
sysb=find_system(model,'LookUnderMasks','all','FollowLinks','on','IncludeCommented','on','MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb), if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end, end
hws=get_param(model,'ModelWorkspace');
T=readtable(fullfile(proj,'test.csv'),'TextType','string'); row=T(T.VARIANT_NAME==string(variant),:);
Fc=row.Fc(1); assignin(hws,'Fc',Fc); assignin(hws,'Ts_Control',1/Fc);
assignin(hws,'use_d_predict',row.use_d_predict(1)); assignin(hws,'use_p_predict',row.use_p_predict(1));
assignin(hws,'use_harmonic',row.use_harmonic(1)); assignin(hws,'estimation_src',row.estimation_src(1));

OFF=[0 1 onset 999 0 50 0 0]; T0=onset;
% {tag, IL params, Vdc params, label, ReThink type}
S={
 'S00_baseline',      OFF,                        OFF,                         'Baseline','-'
 'S01_IL_sine60',     [1 2 T0 999 60 50 0 0],     OFF,                         'IL 正弦 60A@50Hz','DoS(AC)'
 'S02_IL_scale1p3',   [1 5 T0 999 1.3 50 0 0],    OFF,                         'IL 增益 x1.3','Damping'
 'S03_IL_bias60',     [1 1 T0 999 60 50 0 0],     OFF,                         'IL 偏置 +60A','Quality'
 'S04_Vdc_neg100',    OFF,                        [1 1 T0 999 -100 0 0 0],     'Vdc 测量 -100V','Damage'
 'S05_Vdc_neg200',    OFF,                        [1 1 T0 999 -200 0 0 0],     'Vdc 测量 -200V','Damage+'
 'S06_Vdc_pos150',    OFF,                        [1 1 T0 999  150 0 0 0],     'Vdc 测量 +150V','DoS(DC)'
};
names={'iL_true','iL_meas','iL_delta','Vdc_true','Vdc_meas','Vdc_delta','Vdc_inst','Vdc_mean', ...
       'Pac_Pdc_kW','THD_sys','Vdc_ripple_sys','PF','Iac'};
pre=[onset-0.1 onset]; post=[stop_time-0.1 stop_time];
K=struct([]);
for s=1:size(S,1)
    tag=S{s,1};
    assignin(hws,'atk_params',S{s,2}(:)'); assignin(hws,'atk_params_vdc',S{s,3}(:)');
    t0=tic; out=sim(model,'StopTime',num2str(stop_time),'ReturnWorkspaceOutputs','on','SrcWorkspace','base'); wall=toc(t0);
    res=struct('tag',tag,'label',string(S{s,4}),'rethink',string(S{s,5}),'variant',string(variant), ...
               'il',S{s,2},'vdc',S{s,3},'onset',onset,'stop',stop_time);
    for k=1:numel(names), nm=names{k}; try, ts=out.(nm); res.(nm).t=ts.Time; res.(nm).y=squeeze(ts.Data); catch, end, end
    save(fullfile(rdir,['run_' tag '.mat']),'res','-v7.3');
    kk.tag=tag; kk.label=string(S{s,4}); kk.rethink=string(S{s,5}); kk.variant=string(variant);
    kk.THD_pre=wm(out,'THD_sys',pre); kk.THD_post=wm(out,'THD_sys',post);
    kk.Vdc_pre=wm(out,'Vdc_inst',pre); kk.Vdc_post=wm(out,'Vdc_inst',post);
    kk.Vdc_peak=wmax(out,'Vdc_inst',post); kk.Vdc_min=wmin(out,'Vdc_inst',post);
    kk.Pac_pre=wm(out,'Pac_Pdc_kW',pre,1); kk.Pac_post=wm(out,'Pac_Pdc_kW',post,1);
    kk.PF_post=wm(out,'PF',post); kk.ripple_post=wm(out,'Vdc_ripple_sys',post);
    kk.Iac_rms_pre=wrms(out,'Iac',pre); kk.Iac_rms_post=wrms(out,'Iac',post); kk.Iac_peak_post=wmax(out,'Iac',post);
    kk.wall=wall;
    if isempty(K), K=kk; else, K(end+1)=kk; end %#ok<AGROW>
    fprintf('[%s] %-16s %-9s THD %6.2f->%6.2f Vdc %5.0f->%5.0f(pk%5.0f,mn%5.0f) P %6.2f->%6.2f PF %.3f Iac_rms %5.1f (%.0fs)\n', ...
        variant, tag, kk.rethink, kk.THD_pre,kk.THD_post, kk.Vdc_pre,kk.Vdc_post,kk.Vdc_peak,kk.Vdc_min, kk.Pac_pre,kk.Pac_post, kk.PF_post, kk.Iac_rms_post, wall);
end
Tt=struct2table(K); writetable(Tt, fullfile(rdir,'atk3_kpis.csv'));
save(fullfile(rdir,'atk3_summary.mat'),'K','variant','onset','stop_time','-v7.3');
fprintf('ATK3_DONE[%s] -> %s\n', variant, fullfile(rdir,'atk3_kpis.csv'));
close_system(model,0);
end
function v=wm(out,nm,win,chan), if nargin<4, chan=1; end
try, ts=out.(nm); catch, ts=out.get(nm); end
t=ts.Time; y=squeeze(ts.Data); if ~isvector(y), if size(y,1)<size(y,2), y=y(chan,:).'; else, y=y(:,chan); end, end
k=t>=win(1)&t<=win(2); v=mean(y(k)); end
function v=wmax(out,nm,win), ts=out.(nm); t=ts.Time; y=squeeze(ts.Data); k=t>=win(1)&t<=win(2); v=max(y(k)); end
function v=wmin(out,nm,win), ts=out.(nm); t=ts.Time; y=squeeze(ts.Data); k=t>=win(1)&t<=win(2); v=min(y(k)); end
function v=wrms(out,nm,win), ts=out.(nm); t=ts.Time; y=squeeze(ts.Data); k=t>=win(1)&t<=win(2); v=sqrt(mean(y(k).^2)); end
