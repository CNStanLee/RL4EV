function verify_configs(only, outname)
%VERIFY_CONFIGS  Reproduce control-mode rows in test.csv on the instrumented
% PV_MEV copy (attack OFF), simulate to its simu_time (1 s), and compare the
% measured steady-state THD against the expected value in test.csv.
%   only    : optional cellstr/string array of VARIANT_NAMEs to run (default all)
%   outname : optional results CSV filename (default 'verify_results.csv')
if nargin<1, only=[]; end
if nargin<2||isempty(outname), outname='verify_results.csv'; end
proj='/mnt/data6/playground/RL4EV/Simulation/PV_MEV';
model='PV_MEV';
exp_mdir=fullfile(proj,'exp','model');
rdir=fullfile(proj,'exp','results');
if ~exist(rdir,'dir'), mkdir(rdir); end
warning('off','MATLAB:rmpath:DirNotFound'); rmpath(proj); addpath(exp_mdir); cd(exp_mdir);
evalin('base', ['run(''' fullfile(exp_mdir,'init_paras.m') ''')']);
load_system(fullfile(exp_mdir,[model '.slx']));
sysb=find_system(model,'LookUnderMasks','all','FollowLinks','on','IncludeCommented','on','MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb), if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end, end
hws=get_param(model,'ModelWorkspace');

T=readtable(fullfile(proj,'test.csv'),'TextType','string');
fprintf('%-12s %6s %2s %2s %2s %2s | %8s %8s | %7s %6s %6s %6s\n', ...
    'variant','Fc/k','d','p','h','es','exp_THD','meas_THD','ripple','Vdc','P_kW','PF');
R=struct([]);
for r=1:height(T)
    name=T.VARIANT_NAME(r);
    if ~isempty(only) && ~any(string(only)==string(name)), continue; end
    Fc=T.Fc(r); d=T.use_d_predict(r); p=T.use_p_predict(r); h=T.use_harmonic(r);
    es=T.estimation_src(r);
    expTHD=str2double(erase(string(T.THD(r)),'%')); st=T.simu_time(r);
    assignin(hws,'Fc',Fc); assignin(hws,'Ts_Control',1/Fc);
    assignin(hws,'use_d_predict',d); assignin(hws,'use_p_predict',p);
    assignin(hws,'use_harmonic',h); assignin(hws,'estimation_src',es);
    assignin(hws,'atk_params',[0 1 0.85 999 0 50 0 0]);   % attack OFF
    t0=tic;
    out=sim(model,'StopTime',num2str(st),'ReturnWorkspaceOutputs','on','SrcWorkspace','base');
    wall=toc(t0);
    win=[st-0.1 st];
    thd=wm(out,'THD_sys',win); rip=wm(out,'Vdc_ripple_sys',win);
    vdc=wm(out,'Vdc_mean',win); pac=wm(out,'Pac_Pdc_kW',win,1); pf=wm(out,'PF',win);
    res=struct('variant',name,'Fc',Fc,'d',d,'p',p,'h',h,'es',es,'exp_THD',expTHD, ...
        'meas_THD',thd,'ripple',rip,'Vdc',vdc,'Pac_kW',pac,'PF',pf,'wall',wall,'simu_time',st);
    % save full timeseries for this config
    saveres=struct('variant',name);
    for nm=["iL_true","iL_meas","THD_sys","Vdc_mean","Vdc_inst","Pac_Pdc_kW","PF","Vdc_ripple_sys","Iac","Vac"]
        try, ts=out.(char(nm)); saveres.(char(nm)).t=ts.Time; saveres.(char(nm)).y=squeeze(ts.Data); catch, end
    end %#ok<*NASGU>
    save(fullfile(rdir,['verify_' char(name) '.mat']),'saveres','-v7.3');
    if isempty(R), R=res; else, R(end+1)=res; end %#ok<AGROW>
    fprintf('%-12s %6g %2d %2d %2d %2d | %7.2f%% %7.2f%% | %6.2f %6.0f %6.2f %6.3f  (%.0fs)\n', ...
        name, Fc/1e3, d, p, h, es, expTHD, thd, rip, vdc, pac, pf, wall);
end
Tt=struct2table(R); writetable(Tt, fullfile(rdir,outname));
fprintf('VERIFY_DONE -> %s\n', fullfile(rdir,outname));
close_system(model,0);
end
function v=wm(out,nm,win,chan)
if nargin<4, chan=1; end
try, ts=out.(nm); catch, ts=out.get(nm); end
t=ts.Time; y=squeeze(ts.Data);
if ~isvector(y), if size(y,1)<size(y,2), y=y(chan,:).'; else, y=y(:,chan); end, end
k=t>=win(1)&t<=win(2); v=mean(y(k));
end
