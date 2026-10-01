function build_attack_pvmev()
%BUILD_ATTACK_PVMEV  Instrument a non-invasive copy of Simulation/PV_MEV/PV_MEV.slx:
% inject a ReThink IL current-sensor attack (disabled by default) on node-0
% "EV System" and add To-Workspace logging. Config (Fc/flags) and attack params
% are driven per-run from the model workspace (survive InitFcn 'clear').
proj  = '/mnt/data6/playground/RL4EV/Simulation/PV_MEV';
model = 'PV_MEV';
orig  = fullfile(proj,[model '.slx']);
exp_mdir = fullfile(proj,'exp','model');
newfile  = fullfile(exp_mdir,[model '.slx']);
Tc = 1/20e3;   % default control sample time placeholder for the attack clock

if bdIsLoaded(model), close_system(model,0); end
copyfile(orig, newfile);
warning('off','MATLAB:rmpath:DirNotFound'); rmpath(proj);
addpath(exp_mdir); cd(exp_mdir);
load_system(newfile);

ev  = [model '/EV System'];              % node-0 (instrumented, has THD display)
pfc = [ev '/PFC Control'];

% ---- disable TCPIP transport (deterministic local run) ----
sysb = find_system(model,'LookUnderMasks','all','FollowLinks','on','IncludeCommented','on', ...
    'MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb)
    if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end
end

% ---- attack blocks (Interpreted MATLAB Function) in node-0 PFC Control ----
mux=[pfc '/IL_atk_mux']; clk=[pfc '/IL_atk_clock']; con=[pfc '/IL_atk_params'];
fcn=[pfc '/IL_atk_apply']; dmx=[pfc '/IL_atk_demux']; term=[pfc '/IL_atk_delta_term'];
add_block('simulink/Sources/Digital Clock', clk, 'Position',[380 630 420 650],'SampleTime',num2str(Tc));
add_block('simulink/Sources/Constant', con, 'Position',[380 675 460 705],'Value','atk_params');
add_block('simulink/Signal Routing/Mux', mux, 'Position',[500 545 505 705],'Inputs','3');
add_block('simulink/User-Defined Functions/Interpreted MATLAB Function', fcn, ...
    'Position',[545 590 655 650],'MATLABFcn','il_attack_apply','OutputDimensions','2','SampleTime',num2str(Tc),'Output1D','on');
add_block('simulink/Signal Routing/Demux', dmx, 'Position',[695 600 700 660],'Outputs','[1 1]');
add_block('simulink/Sinks/Terminator', term, 'Position',[760 640 780 660]);

% ---- inject at Rate Transition5 output (node-0) ----
rt=[pfc '/Rate Transition5']; ph=get_param(rt,'PortHandles'); lo=get_param(ph.Outport(1),'Line');
dbh=get_param(lo,'DstBlockHandle'); dph=get_param(lo,'DstPortHandle');
dst=cell(numel(dbh),1);
for i=1:numel(dbh), dst{i}=sprintf('%s/%d',get_param(dbh(i),'Name'),get_param(dph(i),'PortNumber')); end
delete_line(lo);
add_line(pfc,'Rate Transition5/1','IL_atk_mux/1','autorouting','on');
add_line(pfc,'IL_atk_clock/1','IL_atk_mux/2','autorouting','on');
add_line(pfc,'IL_atk_params/1','IL_atk_mux/3','autorouting','on');
add_line(pfc,'IL_atk_mux/1','IL_atk_apply/1','autorouting','on');
add_line(pfc,'IL_atk_apply/1','IL_atk_demux/1','autorouting','on');
for i=1:numel(dst), add_line(pfc,'IL_atk_demux/1',dst{i},'autorouting','on'); end
add_line(pfc,'IL_atk_demux/2','IL_atk_delta_term/1','autorouting','on');

% ---- model-workspace defaults (attack off + MPCC_D config) ----
hws=get_param(model,'ModelWorkspace');
assignin(hws,'atk_params',[0 1 0.85 999 0 50 0 0]);   % onset 0.85s (near end, after 1s settle)

% ---- logging taps (direct block-port taps, node-0 scoped, unambiguous) ----
Tlc=2.5e-4; Tlp=1e-5;
add_tap(pfc,'Rate Transition5',1,'iL_true',Tlc);
add_tap(pfc,'IL_atk_demux',1,'iL_meas',Tlc);
add_tap(pfc,'IL_atk_demux',2,'iL_delta',Tlc);
% Measurements 1 outports (1 Vdc_mean, 2 Pac_Pdc_kW, 3 THD%, 4 Ripple%, 5 PF)
add_tap(ev,'Measurements 1',1,'Vdc_mean',Tlc);
add_tap(ev,'Measurements 1',2,'Pac_Pdc_kW',Tlc);
add_tap(ev,'Measurements 1',3,'THD_sys',Tlc);
add_tap(ev,'Measurements 1',4,'Vdc_ripple_sys',Tlc);
add_tap(ev,'Measurements 1',5,'PF',Tlc);
% Measurements 1 inputs for waveforms (1 Vac, 2 Iac, 3 Vdc)
add_tap_in(ev,'Measurements 1',1,'Vac',Tlp);
add_tap_in(ev,'Measurements 1',2,'Iac',Tlp);
add_tap_in(ev,'Measurements 1',3,'Vdc_inst',Tlp);

set_param(model,'ReturnWorkspaceOutputs','on'); set_param(model,'StopTime','1');
save_system(model,newfile);
fprintf('BUILT %s\n', newfile);
try
    evalin('base', ['run(''' fullfile(exp_mdir,'init_paras.m') ''')']);
    set_param(model,'SimulationCommand','update'); fprintf('COMPILE_OK\n');
    set_param(model,'SimulationCommand','stop'); close_system(model,1);
catch e
    fprintf('COMPILE_FAIL: %s\n', e.message); close_system(model,0);
end
fprintf('DONE_BUILD\n');
end

function tows=mk_tows(sys,v,Ts)
tows=[sys '/tows_' v];
add_block('simulink/Sinks/To Workspace',tows,'VariableName',v,'SaveFormat','Timeseries','SampleTime',num2str(Ts));
end
function add_tap(sys,blk,port,v,Ts)
tows=mk_tows(sys,v,Ts); sp=get_param([sys '/' blk],'PortHandles'); dp=get_param(tows,'PortHandles');
add_line(sys,sp.Outport(port),dp.Inport(1),'autorouting','on');
end
function add_tap_in(sys,blk,inport,v,Ts)
% branch a To Workspace off the source line feeding blk's input port `inport`
ph=get_param([sys '/' blk],'PortHandles'); lh=get_param(ph.Inport(inport),'Line');
if lh<0, fprintf('  [warn] no line into %s in%d\n',blk,inport); return; end
sph=get_param(lh,'SrcPortHandle');
tows=mk_tows(sys,v,Ts); dp=get_param(tows,'PortHandles');
add_line(sys,sph,dp.Inport(1),'autorouting','on');
end
