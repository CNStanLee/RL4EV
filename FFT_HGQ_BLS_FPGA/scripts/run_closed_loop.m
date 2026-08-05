function simulation_output = run_closed_loop(stop_time)
%RUN_CLOSED_LOOP Run the packaged FFT+HGQ-BLS MPCC model.

arguments
    stop_time (1, 1) double {mustBePositive} = 0.15
end

model_name = setup_project(false);
script_dir = fileparts(mfilename("fullpath"));
project_dir = fileparts(script_dir);
model_dir = fullfile(project_dir, "model");
previous_dir = pwd;
cd(model_dir);
directory_cleanup = onCleanup(@() cd(previous_dir));
run("init_paras.m");
load_system(model_name);
model_cleanup = onCleanup(@() close_system(model_name, 0));
set_param(model_name, "InitFcn", "");

% Network transport is unrelated to the estimator and is disabled for a
% deterministic local run. The HGQ2 ONNX co-execution block remains active.
system_blocks = find_system(model_name, ...
    "LookUnderMasks", "all", "FollowLinks", "on", ...
    "MatchFilter", @Simulink.match.allVariants, ...
    "BlockType", "MATLABSystem");
for index = 1:numel(system_blocks)
    system_name = string(get_param(system_blocks{index}, "System"));
    if contains(system_name, "TCPIP")
        set_param(system_blocks{index}, "Commented", "on");
    end
end

assignin("base", "Ro", 22.22);
assignin("base", "Vnom_ac", 240.0);
assignin("base", "use_harmonic", 1);
assignin("base", "use_d_predict", 1);
simulation_output = sim(model_name, ...
    "StopTime", num2str(stop_time, 17), ...
    "ReturnWorkspaceOutputs", "on");
fprintf("completed FFT+HGQ-BLS closed-loop run to %.6g s\n", stop_time);
end
