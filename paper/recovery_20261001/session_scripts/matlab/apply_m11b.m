% apply_m11b.m: M11 bounds the loop only while a power-moving correction (M0 bus, M5 battery voltage) is active
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd); load_system('PV_MEV');
rt=sfroot; ch=rt.find('-isa','Stateflow.EMChart','Path','PV_MEV/EV System/PFC Control/Mitigation'); sc=ch(1).Script;
old='if M(11) && any(g > 0), Ilim = 55; end';
new=['if M(11) && (g(1) > 0 || g(4) > 0), Ilim = 55; end   % only the power-moving corrections M0 / M5 (an Ibat / Iac / Vac flag alone leaves the limit at Limit_V)'];
assert(contains(sc,old)); sc=strrep(sc,old,new); ch(1).Script=sc;
assignin('base','VARIANT_NAME','MPCC_R'); evalin('base','init_paras'); set_param('PV_MEV','SimulationCommand','update'); fprintf('[compile] OK\n');
save_system('PV_MEV'); close_system('PV_MEV',0); fprintf('[saved]\n');
