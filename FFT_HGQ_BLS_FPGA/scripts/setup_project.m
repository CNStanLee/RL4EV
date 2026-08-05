function model_name = setup_project(open_model)
%SETUP_PROJECT Configure the portable FFT+HGQ-BLS Simulink project.

arguments
    open_model (1, 1) logical = true
end

script_dir = fileparts(mfilename("fullpath"));
project_dir = fileparts(script_dir);
model_dir = fullfile(project_dir, "model");
model_name = "PV_MEV_FFT_HGQ_BLS";
model_file = fullfile(model_dir, model_name + ".slx");
onnx_file = fullfile(project_dir, "artifacts", ...
    "harmonic_residual_bls_simulink.onnx");
assert(isfile(model_file), "Missing model: %s", model_file);
assert(isfile(onnx_file), "Missing HGQ2 ONNX artifact: %s", onnx_file);

addpath(model_dir);
previous_dir = pwd;
cd(model_dir);
directory_cleanup = onCleanup(@() cd(previous_dir));
load_system(model_file);

system_blocks = find_system(model_name, ...
    "LookUnderMasks", "all", "FollowLinks", "on", ...
    "IncludeCommented", "on", ...
    "MatchFilter", @Simulink.match.allVariants, ...
    "BlockType", "MATLABSystem");
configured = 0;
for index = 1:numel(system_blocks)
    parent = string(get_param(system_blocks{index}, "Parent"));
    parameters = get_param(parent, "ObjectParameters");
    if ~isfield(parameters, "ModelFile")
        continue
    end
    set_param(parent, "ModelFile", onnx_file);
    if isfield(parameters, "ExecutionProviders")
        set_param(parent, "ExecutionProviders", "CPUExecutionProvider");
    end
    configured = configured + 1;
end
assert(configured >= 1, "No ONNX model block was found");
set_param(model_name, "InitFcn", "init_paras");
save_system(model_name, model_file);
if open_model
    open_system(model_name);
else
    close_system(model_name, 0);
end
fprintf("configured %s\n", model_file);
end
