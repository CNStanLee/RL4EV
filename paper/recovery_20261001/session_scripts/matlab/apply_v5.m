% Apply the detector v5 layout and the MPCC_R mitigation to PV_MEV, then smoke-test.
% Run only when no other MATLAB process uses PV_MEV.slx (night batch finished).
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
R = fileparts(fileparts(pwd));
assert(isfile(fullfile(R, 'EMI_DET_FPGA', 'artifacts', 'detector.onnx')), 'install the v5 ONNX as artifacts/detector.onnx first');
build_detector();          % 48 features, ONNX 48 -> 20, hysteresis (saves the model)
build_mitigation();        % Mitigation + chg_corr (saves the model)
build_mitigation('inspect');
% smoke: 25 ms of MPCC_R (all blocks compile, python bridge ok)
VARIANT_NAME = "MPCC_R"; assignin('base', 'VARIANT_NAME', VARIANT_NAME);
init_paras; load_system('PV_MEV');
tcp = {'/EV System/PFC Control/Enabled Subsystem', '/EV System/PFC Control/HIL TCP Receive1', '/EV System/PFC Control/HIL TCP Send1', '/EV System/PFC Control/Original vs HIL Predict'};
for k = 1:numel(tcp), try, set_param(['PV_MEV' tcp{k}], 'Commented', 'on'); catch, end, end
t0 = tic; so = sim('PV_MEV', 'StopTime', '0.025'); fprintf('MPCC_R smoke ok %.0f s\n', toc(t0));
close_system('PV_MEV', 0);
