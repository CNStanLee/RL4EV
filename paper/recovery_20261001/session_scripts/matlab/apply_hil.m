cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
copyfile('PV_MEV.slx', '<RL4EV>/Simulation/PV_MEV/results/emi/PV_MEV_pre_hil_backup.slx');
VARIANT_NAME = "MPCC_R"; init_paras;
build_hil();
% compile check in SIL mode (all switches 0, TCP blocks commented), MPCC_R and MPCC_D_H1
for v = {"MPCC_R", "MPCC_D_H1"}
    VARIANT_NAME = v{1}; init_paras; load_system('PV_MEV');
    tcp = {'/EV System/PFC Control/HIL TCP Receive1', '/EV System/PFC Control/HIL TCP Send1', '/EV System/PFC Control/EMI Detector/HIL Det Send', '/EV System/PFC Control/EMI Detector/HIL Det Receive', '/EV System/PFC Control/One  Cycle Model Prediction/HIL Est Send', '/EV System/PFC Control/One  Cycle Model Prediction/HIL Est Receive'};
    for k = 1:numel(tcp), set_param(['PV_MEV' tcp{k}], 'Commented', 'on'); end
    t0 = tic; so = sim('PV_MEV', 'StopTime', '0.002'); fprintf('[apply_hil] %s SIL smoke 2 ms ok (%.0f s)\n', v{1}, toc(t0));
    close_system('PV_MEV', 0);
end
