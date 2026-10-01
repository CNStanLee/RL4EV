function add_vdc_attack()
%ADD_VDC_ATTACK  Add a second ReThink attack chain on the DC-bus voltage sensor
% (Rate Transition4 output in node-0 PFC Control), mirroring the IL chain.
% Vdc_meas = Vdc_true + delta_vdc(t), driven by model-workspace `atk_params_vdc`.
proj='/mnt/data6/playground/RL4EV/Simulation/PV_MEV'; model='PV_MEV';
exp_mdir=fullfile(proj,'exp','model'); newfile=fullfile(exp_mdir,[model '.slx']);
Tc=1/20e3;
warning('off','MATLAB:rmpath:DirNotFound'); rmpath(proj); addpath(exp_mdir); cd(exp_mdir);
load_system(newfile);
pfc=[model '/EV System/PFC Control'];

% guard: skip if already added
if ~isempty(find_system(pfc,'SearchDepth',1,'LookUnderMasks','all','Name','Vdc_atk_apply'))
    fprintf('Vdc attack already present; skipping add.\n');
else
    mux=[pfc '/Vdc_atk_mux']; clk=[pfc '/Vdc_atk_clock']; con=[pfc '/Vdc_atk_params'];
    fcn=[pfc '/Vdc_atk_apply']; dmx=[pfc '/Vdc_atk_demux']; term=[pfc '/Vdc_atk_delta_term'];
    add_block('simulink/Sources/Digital Clock', clk, 'Position',[380 760 420 780],'SampleTime',num2str(Tc));
    add_block('simulink/Sources/Constant', con, 'Position',[380 805 470 835],'Value','atk_params_vdc');
    add_block('simulink/Signal Routing/Mux', mux, 'Position',[500 675 505 835],'Inputs','3');
    add_block('simulink/User-Defined Functions/Interpreted MATLAB Function', fcn, ...
        'Position',[545 720 655 780],'MATLABFcn','il_attack_apply','OutputDimensions','2','SampleTime',num2str(Tc),'Output1D','on');
    add_block('simulink/Signal Routing/Demux', dmx, 'Position',[695 730 700 790],'Outputs','[1 1]');
    add_block('simulink/Sinks/Terminator', term, 'Position',[760 770 780 790]);

    rt=[pfc '/Rate Transition4']; ph=get_param(rt,'PortHandles'); lo=get_param(ph.Outport(1),'Line');
    dbh=get_param(lo,'DstBlockHandle'); dph=get_param(lo,'DstPortHandle');
    dst=cell(numel(dbh),1);
    for i=1:numel(dbh), dst{i}=sprintf('%s/%d',get_param(dbh(i),'Name'),get_param(dph(i),'PortNumber')); end
    delete_line(lo);
    add_line(pfc,'Rate Transition4/1','Vdc_atk_mux/1','autorouting','on');
    add_line(pfc,'Vdc_atk_clock/1','Vdc_atk_mux/2','autorouting','on');
    add_line(pfc,'Vdc_atk_params/1','Vdc_atk_mux/3','autorouting','on');
    add_line(pfc,'Vdc_atk_mux/1','Vdc_atk_apply/1','autorouting','on');
    add_line(pfc,'Vdc_atk_apply/1','Vdc_atk_demux/1','autorouting','on');
    for i=1:numel(dst), add_line(pfc,'Vdc_atk_demux/1',dst{i},'autorouting','on'); end
    add_line(pfc,'Vdc_atk_demux/2','Vdc_atk_delta_term/1','autorouting','on');

    % logging taps
    add_tap(pfc,'Rate Transition4',1,'Vdc_true',2.5e-4);
    add_tap(pfc,'Vdc_atk_demux',1,'Vdc_meas',2.5e-4);
    add_tap(pfc,'Vdc_atk_demux',2,'Vdc_delta',2.5e-4);
    fprintf('Vdc attack chain added on Rate Transition4.\n');
end

hws=get_param(model,'ModelWorkspace');
assignin(hws,'atk_params_vdc',[0 1 0.85 999 0 50 0 0]);   % default: Vdc attack OFF
save_system(model,newfile);
fprintf('SAVED %s\n', newfile);
try
    evalin('base', ['run(''' fullfile(exp_mdir,'init_paras.m') ''')']);
    set_param(model,'SimulationCommand','update'); fprintf('COMPILE_OK\n');
    set_param(model,'SimulationCommand','stop'); close_system(model,1);
catch e
    fprintf('COMPILE_FAIL: %s\n', e.message); close_system(model,0);
end
fprintf('ADD_VDC_DONE\n');
end
function tows=mk_tows(sys,v,Ts)
tows=[sys '/tows_' v];
add_block('simulink/Sinks/To Workspace',tows,'VariableName',v,'SaveFormat','Timeseries','SampleTime',num2str(Ts));
end
function add_tap(sys,blk,port,v,Ts)
tows=mk_tows(sys,v,Ts); sp=get_param([sys '/' blk],'PortHandles'); dp=get_param(tows,'PortHandles');
add_line(sys,sp.Outport(port),dp.Inport(1),'autorouting','on');
end
