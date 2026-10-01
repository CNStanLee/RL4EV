function res = sim_il_case(tag, atk_params, stop_time, outdir)
%SIM_IL_CASE Run one IL-sensor-attack scenario on the attack model.
%  atk_params = [enable mode t0 t1 A f phase offset]
if nargin<3||isempty(stop_time), stop_time=0.15; end
if nargin<4, outdir=''; end
proj  = '/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA';
model = 'PV_MEV_FFT_HGQ_BLS';
mdir  = fullfile(proj,'experiments','sensor_attack_il','model');
warning('off','MATLAB:rmpath:DirNotFound');
rmpath(fullfile(proj,'model'));
addpath(mdir); cd(mdir);
evalin('base', ['run(''' fullfile(mdir,'init_paras.m') ''')']);
if ~bdIsLoaded(model), load_system(fullfile(mdir,[model '.slx'])); end
% ensure local/deterministic + ONNX cpu (already saved, re-assert defensively)
sysb = find_system(model,'LookUnderMasks','all','FollowLinks','on','IncludeCommented','on', ...
    'MatchFilter',@Simulink.match.allVariants,'BlockType','MATLABSystem');
for i=1:numel(sysb)
    if contains(string(get_param(sysb{i},'System')),'TCPIP'), set_param(sysb{i},'Commented','on'); end
end
hws = get_param(model,'ModelWorkspace');
assignin(hws,'atk_params',atk_params(:)');
t0=tic;
out = sim(model,'StopTime',num2str(stop_time),'ReturnWorkspaceOutputs','on','SrcWorkspace','base');
wall=toc(t0);
% collect To Workspace timeseries
res = struct('tag',tag,'atk_params',atk_params,'wall',wall,'stop_time',stop_time);
names = {'iL_true','iL_meas','iL_delta','Iref','predict_D','THD_pfc','Vdc','Iac','Vac','iL_phys','Vdc_mean','Pac_Pdc_kW','THD_sys','Vdc_ripple_sys','PF'};
for k=1:numel(names)
    nm=names{k};
    try
        ts = out.(nm);
        res.(nm).t = ts.Time; res.(nm).y = squeeze(ts.Data);
    catch
        try
            ts = out.get(nm); res.(nm).t=ts.Time; res.(nm).y=squeeze(ts.Data);
        catch
            res.(nm).t=[]; res.(nm).y=[]; fprintf('  [warn] missing %s\n',nm);
        end
    end
end
if ~isempty(outdir)
    if ~exist(outdir,'dir'), mkdir(outdir); end
    save(fullfile(outdir,['run_' tag '.mat']),'res','-v7.3');
end
fprintf('CASE %s done wall=%.1fs\n', tag, wall);
end
