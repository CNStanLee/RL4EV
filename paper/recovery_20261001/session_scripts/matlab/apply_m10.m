% M10 (bit 1024): baseline-referenced physics estimates for M0 / M5 (review point 8, model mismatch).
% The residual of the buck identity observed while no bus flag is up is a model-mismatch offset (charger losses,
% parameter error), not a measurement bias; it is tracked with a slow filter (0.2 s) gated to small changes and removed.
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd);
mdl = 'PV_MEV'; load_system(mdl);
rt = sfroot;
% ---- Mitigation chart
ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/EV System/PFC Control/Mitigation']); ch = ch(1); s = ch.Script;
if contains(s, 'M10'), error('M10 already applied'); end
s = strrep(s, sprintf('persistent g dVf Iref_prev pkp pkn Vamp th_prev init\n'), sprintf('persistent g dVf Iref_prev pkp pkn Vamp th_prev init eb\n'));
s = strrep(s, 'Vamp = 0; th_prev = 0; init = 1; end', 'Vamp = 0; th_prev = 0; eb = 0; init = 1; end');
old = sprintf('dV = min(max(dV, -120), 120);\n');
new = sprintf(['dV = min(max(dV, -120), 120);\n' ...
 '%% --- M10 (1024): baseline-referenced estimate.  The residual seen while no bus flag is up is a model-mismatch offset\n' ...
 '%% (charger losses, parameter error), not a bias: track it slowly (0.2 s) while it moves by less than 5 V, freeze it\n' ...
 '%% while a flag is up or the residual jumps (an attack), and remove it from the estimate.\n' ...
 'if M(10)\n' ...
 '    if g(1) == 0 && phys_ok && abs(dV - eb) < 5, eb = eb + (Ts / 0.2) * (dV - eb); end\n' ...
 '    if phys_ok, dV = min(max(dV - eb, -120), 120); end\n' ...
 'end\n']);
assert(contains(s, old)); s = strrep(s, old, new);
s = strrep(s, 'dbg = [g(1), dVf, double(phys_ok), Vamp, g(3), hold];', 'dbg = [g(1), dVf, double(phys_ok), Vamp, g(3), eb];');
ch.Script = s; fprintf('[M10] Mitigation chart patched\n');
% ---- chg_corr chart
ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/EV System/Charger Stage/chg_corr']); ch = ch(1); s = ch.Script;
s = strrep(s, sprintf('persistent g dVf init\n'), sprintf('persistent g dVf init eb\n'));
s = strrep(s, 'g = zeros(1, 2); dVf = 0; init = 1; end', 'g = zeros(1, 2); dVf = 0; eb = 0; init = 1; end');
old = sprintf('dV = min(max(dV, -60), 60);\n');
new = sprintf(['dV = min(max(dV, -60), 60);\n' ...
 'if bitand(uint32(mask), uint32(1024)) > 0      %% M10: baseline-referenced (model-mismatch offset removed), see Mitigation\n' ...
 '    if g(1) == 0 && phys_ok && abs(dV - eb) < 3, eb = eb + (Ts / 0.2) * (dV - eb); end\n' ...
 '    if phys_ok, dV = min(max(dV - eb, -60), 60); end\n' ...
 'end\n']);
assert(contains(s, old)); s = strrep(s, old, new); ch.Script = s; fprintf('[M10] chg_corr chart patched\n');
save_system(mdl); close_system(mdl, 0); fprintf('[M10] PV_MEV saved\n');
% compile check
VARIANT_NAME = 'MPCC_R_BR'; init_paras; load_system(mdl); set_param(mdl, 'SimulationCommand', 'update'); fprintf('compile ok\n'); close_system(mdl, 0);
