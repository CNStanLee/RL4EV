function baseline_modes()
%BASELINE_MODES  Diagnose which config reproduces the documented CRPR / MPCC THD.
% Mode flags + Ts_Control are pushed into the MODEL workspace so they shadow base
% and survive the InitFcn 'clear'. Fc is NOT a model variable (only feeds Ts_Control
% inside init_paras), so the real knob is Ts_Control = 1/Fc.
proj  = '/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA';
model = 'PV_MEV_FFT_HGQ_BLS';
mdir  = fullfile(proj,'experiments','sensor_attack_il','model');
rdir  = fullfile(proj,'experiments','sensor_attack_il','results');
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
assignin(hws,'atk_params',[0 1 0.08 999 0 50 0 0]);   % attack OFF

STOP = 0.20; WIN = [0.14 0.20];
% cfg: tag, use_d, use_p, use_h, est_src, Fc(kHz)
C = {
 'CRPR_20k',  0 0 0 1 20
 'CRPR_100k', 0 0 0 1 100
 'MPCCd_20k', 1 0 0 1 20
 'MPCCd_100k',1 0 0 1 100
 'MPCC4_20k', 1 0 1 1 20
 'MPCC4_100k',1 0 1 1 100
};
fprintf('%-12s %8s %8s %8s %8s\n','cfg','Ts_us','THD%','ripple%','P_kW');
for s=1:size(C,1)
    tag=C{s,1};
    assignin(hws,'use_d_predict',C{s,2});
    assignin(hws,'use_p_predict',C{s,3});
    assignin(hws,'use_harmonic', C{s,4});
    assignin(hws,'estimation_src',C{s,5});
    Ts = 1/(C{s,6}*1e3);
    assignin(hws,'Ts_Control',Ts);
    assignin(hws,'Fc',C{s,6}*1e3);
    out = sim(model,'StopTime',num2str(STOP),'ReturnWorkspaceOutputs','on','SrcWorkspace','base');
    thd = wm(out,'THD_sys',WIN); rip = wm(out,'Vdc_ripple_sys',WIN);
    pac = wm(out,'Pac_Pdc_kW',WIN,1); vdc = wm(out,'Vdc_mean',WIN);
    fprintf('%-12s %8.1f %8.2f %8.2f %8.2f  Vdc=%.0f\n', tag, Ts*1e6, thd, rip, pac, vdc);
end
close_system(model,0);
fprintf('BASELINE_MODES_DONE\n');
end

function v = wm(out,nm,win,chan)
if nargin<4, chan=1; end
try, ts=out.(nm); catch, ts=out.get(nm); end
t=ts.Time; y=squeeze(ts.Data);
if ~isvector(y), if size(y,1)<size(y,2), y=y(chan,:).'; else, y=y(:,chan); end, end
k=t>=win(1)&t<=win(2); v=mean(y(k));
end
