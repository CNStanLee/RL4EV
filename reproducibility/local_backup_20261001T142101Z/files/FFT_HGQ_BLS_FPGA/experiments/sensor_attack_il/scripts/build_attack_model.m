function build_attack_model()
%BUILD_ATTACK_MODEL  Inject a ReThink-style IL current-sensor attack into the
% packaged FFT+HGQ2-BLS MPCC model, plus signal logging. Non-destructive: works
% on a copy under experiments/sensor_attack_il/model/.
proj = '/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA';
model = 'PV_MEV_FFT_HGQ_BLS';
orig_mdir = fullfile(proj,'model');
exp_mdir  = fullfile(proj,'experiments','sensor_attack_il','model');
onnx_file = fullfile(proj,'artifacts','harmonic_residual_bls_simulink.onnx');
newfile   = fullfile(exp_mdir,[model '.slx']);
Tc = 0.00025;   % control/estimation sample time (D4 = 4 kHz, 250 us deadline)

% Fresh copy of the model file (keeps internal name == file name).
if bdIsLoaded(model), close_system(model,0); end
copyfile(fullfile(orig_mdir,[model '.slx']), newfile);

% Put ONLY the experiment model dir on top of the path so the copy shadows orig.
warning('off','MATLAB:rmpath:DirNotFound');
rmpath(orig_mdir);
addpath(exp_mdir);
cd(exp_mdir);
load_system(newfile);

pfc = [model '/EV System/PFC Control'];

% ---- ONNX absolute path (like setup_project) ----
sysb = find_system(model,'LookUnderMasks','all','FollowLinks','on', ...
    'IncludeCommented','on','MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb)
    parent = get_param(sysb{i},'Parent');
    pr = get_param(parent,'ObjectParameters');
    if isfield(pr,'ModelFile'), set_param(parent,'ModelFile',onnx_file);
        if isfield(pr,'ExecutionProviders'), set_param(parent,'ExecutionProviders','CPUExecutionProvider'); end
    end
end
% ---- disable TCPIP transport (deterministic local run) ----
for i=1:numel(sysb)
    if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end
end

% ---- injection line: Rate Transition5 output -> {Goto11, AbsI} ----
rt = [pfc '/Rate Transition5'];
ph = get_param(rt,'PortHandles');
lo = get_param(ph.Outport(1),'Line');
dbh = get_param(lo,'DstBlockHandle');  dph = get_param(lo,'DstPortHandle');
dst = cell(numel(dbh),1);
for i=1:numel(dbh)
    dst{i} = sprintf('%s/%d', get_param(dbh(i),'Name'), get_param(dph(i),'PortNumber'));
end
delete_line(lo);

% ---- attack blocks (Interpreted MATLAB Function: robust fixed 1-in/1-out) ----
mux  = [pfc '/IL_atk_mux'];
clk  = [pfc '/IL_atk_clock'];
con  = [pfc '/IL_atk_params'];
fcn  = [pfc '/IL_atk_apply'];
dmx  = [pfc '/IL_atk_demux'];
term = [pfc '/IL_atk_delta_term'];
add_block('simulink/Sources/Digital Clock', clk, 'Position',[380 630 420 650],'SampleTime',num2str(Tc));
add_block('simulink/Sources/Constant', con, 'Position',[380 675 460 705],'Value','atk_params');
add_block('simulink/Signal Routing/Mux', mux, 'Position',[500 545 505 705],'Inputs','3');
add_block('simulink/User-Defined Functions/Interpreted MATLAB Function', fcn, ...
    'Position',[545 590 655 650],'MATLABFcn','il_attack_apply','OutputDimensions','2', ...
    'SampleTime',num2str(Tc),'Output1D','on');
add_block('simulink/Signal Routing/Demux', dmx, 'Position',[695 600 700 660],'Outputs','[1 1]');
add_block('simulink/Sinks/Terminator', term, 'Position',[760 640 780 660]);

% ---- wiring ----
% Mux input order: 1 iL_true, 2 t, 3 params
add_line(pfc, 'Rate Transition5/1', 'IL_atk_mux/1', 'autorouting','on');
add_line(pfc, 'IL_atk_clock/1',     'IL_atk_mux/2', 'autorouting','on');
add_line(pfc, 'IL_atk_params/1',    'IL_atk_mux/3', 'autorouting','on');
add_line(pfc, 'IL_atk_mux/1',       'IL_atk_apply/1', 'autorouting','on');
add_line(pfc, 'IL_atk_apply/1',     'IL_atk_demux/1', 'autorouting','on');
% Demux out: 1 iL_meas -> former RT5 destinations, 2 delta -> terminator
for i=1:numel(dst)
    add_line(pfc, 'IL_atk_demux/1', dst{i}, 'autorouting','on');
end
add_line(pfc, 'IL_atk_demux/2', 'IL_atk_delta_term/1', 'autorouting','on');

% ---- model workspace: attack params (survives InitFcn 'clear' of base) ----
hws = get_param(model,'ModelWorkspace');
assignin(hws,'atk_params',[0 1 0.08 999 0 50 0 0]);

% ---- logging via To Workspace taps (robust across releases) ----
Tlog_c = 2.5e-4;   % control-rate signals
Tlog_p = 1e-5;     % power/grid signals (100 kHz, matches switching, for waveforms)
ev = [model '/EV System'];
% attack + control signals (inside PFC Control; Iref/predict_D are LOCAL gotos)
add_tap(pfc,'Rate Transition5',1,'iL_true',Tlog_c);
add_tap(pfc,'IL_atk_demux',1,'iL_meas',Tlog_c);
add_tap(pfc,'IL_atk_demux',2,'iL_delta',Tlog_c);
add_from_tap(pfc,'Iref','Iref',Tlog_c);
add_from_tap(pfc,'predict_D','predict_D',Tlog_c);
add_tap(pfc,'THD',1,'THD_pfc',Tlog_c);
% tagged signals via From blocks (EV System scope)
add_from_tap(ev,'Vdc_PFC','Vdc',Tlog_c);
add_from_tap(ev,'Iac','Iac',Tlog_p);
add_from_tap(ev,'Vac','Vac',Tlog_p);
add_from_tap(ev,'iL','iL_phys',Tlog_p);
% system KPIs straight from Measurements 1 outports
% (1 Vdc_mean, 2 Pac_Pdc_kW, 3 THD%, 4 Ripple%, 5 PF)
add_tap(ev,'Measurements 1',1,'Vdc_mean',Tlog_c);
add_tap(ev,'Measurements 1',2,'Pac_Pdc_kW',Tlog_c);
add_tap(ev,'Measurements 1',3,'THD_sys',Tlog_c);
add_tap(ev,'Measurements 1',4,'Vdc_ripple_sys',Tlog_c);
add_tap(ev,'Measurements 1',5,'PF',Tlog_c);

set_param(model,'ReturnWorkspaceOutputs','on');
set_param(model,'StopTime','0.15');

save_system(model, newfile);
fprintf('BUILT %s\n', newfile);

% ---- compile test ----
try
    evalin('base', ['run(''' fullfile(exp_mdir,'init_paras.m') ''')']);
    set_param(model,'SimulationCommand','update');
    fprintf('COMPILE_OK\n');
    set_param(model,'SimulationCommand','stop');
    close_system(model,1);
catch e
    fprintf('COMPILE_FAIL: %s\n', e.message);
    close_system(model,0);
end
fprintf('DONE_BUILD\n');
end

function tows = mk_tows(sys,varName,Ts)
tows = [sys '/tows_' varName];
add_block('simulink/Sinks/To Workspace', tows, ...
    'VariableName',varName,'SaveFormat','Timeseries','SampleTime',num2str(Ts));
end

function add_tap(sys,srcBlk,srcPort,varName,Ts)
% branch a To Workspace off an existing block output port
tows = mk_tows(sys,varName,Ts);
sp = get_param([sys '/' srcBlk],'PortHandles');
dp = get_param(tows,'PortHandles');
add_line(sys, sp.Outport(srcPort), dp.Inport(1), 'autorouting','on');
end

function add_from_tap(sys,tag,varName,Ts)
% From(tag) -> To Workspace, in system `sys`
frm = [sys '/from_' varName];
add_block('simulink/Signal Routing/From', frm, 'GotoTag',tag);
tows = mk_tows(sys,varName,Ts);
add_line(sys, [ 'from_' varName '/1'], ['tows_' varName '/1'], 'autorouting','on');
end

function add_disp_tap(model,dpath,varName,Ts)
% branch a To Workspace off the port that drives a Display block
ph = get_param(dpath,'PortHandles'); lh = get_param(ph.Inport(1),'Line');
sph = get_param(lh,'SrcPortHandle');
sys = get_param(dpath,'Parent');
tows = mk_tows(sys,varName,Ts);
dp = get_param(tows,'PortHandles');
add_line(sys, sph, dp.Inport(1), 'autorouting','on');
end
