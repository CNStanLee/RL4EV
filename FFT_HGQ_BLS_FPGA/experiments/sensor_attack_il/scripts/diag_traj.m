function diag_traj()
%DIAG_TRAJ  Log full THD/Vdc/P/iL trajectories for candidate baselines over a
% longer settle, to fix the calibrated-MPCC and normal-PFC operating points.
proj  = '/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA';
model = 'PV_MEV_FFT_HGQ_BLS';
mdir  = fullfile(proj,'experiments','sensor_attack_il','model');
rdir  = fullfile(proj,'experiments','sensor_attack_il','results','diag');
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
assignin(hws,'atk_params',[0 1 0.08 999 0 50 0 0]);
STOP = 0.35;
C = {
 'CRPR_20k',   0 0 0 1 20
 'MPCCd_20k',  1 0 0 1 20
 'MPCC4_20k',  1 0 1 1 20
};
for s=1:size(C,1)
    tag=C{s,1};
    assignin(hws,'use_d_predict',C{s,2}); assignin(hws,'use_p_predict',C{s,3});
    assignin(hws,'use_harmonic', C{s,4}); assignin(hws,'estimation_src',C{s,5});
    Ts=1/(C{s,6}*1e3); assignin(hws,'Ts_Control',Ts); assignin(hws,'Fc',C{s,6}*1e3);
    out = sim(model,'StopTime',num2str(STOP),'ReturnWorkspaceOutputs','on','SrcWorkspace','base');
    res=struct('tag',tag);
    for nm = ["THD_sys","Vdc","Pac_Pdc_kW","Iac","Iref","iL_true"]
        try, ts=out.(char(nm)); res.(char(nm)).t=ts.Time; res.(char(nm)).y=squeeze(ts.Data); catch, end
    end
    save(fullfile(rdir,['diag_' tag '.mat']),'res','-v7.3');
    thd=wm(out,'THD_sys',[STOP-0.06 STOP]); pac=wm(out,'Pac_Pdc_kW',[STOP-0.06 STOP],1);
    fprintf('DIAG %-10s settle THD=%7.2f  P=%6.2f\n', tag, thd, pac);
end
close_system(model,0); fprintf('DIAG_TRAJ_DONE\n');
end
function v=wm(out,nm,win,chan)
if nargin<4, chan=1; end
try, ts=out.(nm); catch, ts=out.get(nm); end
t=ts.Time; y=squeeze(ts.Data);
if ~isvector(y), if size(y,1)<size(y,2), y=y(chan,:).'; else, y=y(:,chan); end, end
k=t>=win(1)&t<=win(2); v=mean(y(k));
end
