cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
build_mitigation('fix_loop');
VARIANT_NAME = "MPCC_R"; assignin('base','VARIANT_NAME',VARIANT_NAME); init_paras; load_system('PV_MEV');
tcp = {'/EV System/PFC Control/Enabled Subsystem', '/EV System/PFC Control/HIL TCP Receive1', '/EV System/PFC Control/HIL TCP Send1', '/EV System/PFC Control/Original vs HIL Predict'};
for k = 1:numel(tcp), try, set_param(['PV_MEV' tcp{k}], 'Commented', 'on'); catch, end, end
so = sim('PV_MEV', 'StopTime', '0.025'); disp('MPCC_R smoke ok');
close_system('PV_MEV', 0);
