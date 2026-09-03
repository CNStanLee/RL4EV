function build_injection(step)
% BUILD_INJECTION  Add the sensor-chain injection test bench to PV_MEV.
%
%   build_injection()          library blocks + model edits + save
%   build_injection('lib')     only (re)build the three MyLibrary blocks
%   build_injection('model')   only splice the blocks into PV_MEV/EV System
%   build_injection('probe')   only check the Controlled Current Source polarity
%
% Library blocks (MyLibrary.slx):
%   Disturbance Injector  y_int = y_real + dy(t); dy from base-workspace INJ
%                         (expanded to inj_* by init_paras); mask: ch_id,
%                         Ts_inj, Ts_out.  Channel codes 1 Vdc 2 Vac 3 Iac
%                         4 Vbat 5 Ibat; shape codes 1 step 2 ramp 3 sine
%                         4 tri 5 pulse 6 hall.
%   Protection Monitor    real-quantity thresholds prot_thr, records first
%                         trip [code t_trip]; codes 1 UV 2 OV 3 OC 4 BOV 5 BOC
%   Charger Stage         averaged buck (L_chg) + battery (Voc, Rint) +
%                         CC/CV controller at Ts_chg, draws D*Ibat from the
%                         bus through a Controlled Current Source.  Signal
%                         out = [Vbat_real Ibat_real Vbat_int Ibat_int D state
%                         Iref_bat P_charge Idc_draw].
% Model edits (PV_MEV/EV System): Ro1 -> Rbleed (R_bleed), Ro2 -> Rpre
% (start-up preload, switched off at t_pre_off by the existing Ideal Switch /
% Step2), Charger Stage in parallel, injectors on the Vdc/Vac/Iac lines into
% PFC Control, Protection Monitor added.  See docs/EMI_INJECTION_TEST_PLAN.md
% section 3.
if nargin < 1, step = 'all'; end
mdir = fileparts(mfilename('fullpath')); cd(mdir); addpath(mdir);
switch step
    case 'lib',   build_lib();
    case 'model', build_model();
    case 'probe', probe_ccs();
    otherwise,    build_lib(); build_model();
end
end

% =========================================================================
function build_lib()
lib = 'MyLibrary';
load_system(lib); set_param(lib,'Lock','off');
for nm = {'Disturbance Injector','Protection Monitor','Charger Stage'}
    p = [lib '/' nm{1}];
    if getSimulinkBlockHandle(p) ~= -1, delete_block(p); end
end
make_injector([lib '/Disturbance Injector'], [100 -100 220 -40]);
make_protection([lib '/Protection Monitor'], [100 0 220 80]);
make_charger([lib '/Charger Stage'], [100 130 220 230]);
save_system(lib); close_system(lib);
fprintf('[build] MyLibrary saved\n');
end

% ----------------------------------------------------------- injector ----
function make_injector(p, pos)
add_block('built-in/Subsystem', p, 'Position', pos);
delete_lines_in(p);
add_block('simulink/Sources/In1',  [p '/y_real'], 'Position', [30 93 60 107]);
add_block('simulink/Sinks/Out1',   [p '/y_int'],  'Position', [520 93 550 107]);
add_block('simulink/Sources/Digital Clock', [p '/t'], 'Position', [30 180 80 210], 'SampleTime', 'Ts_inj');
c = {'ch_id','inj_channel','inj_shape','inj_amp','inj_k','inj_f','inj_phase','inj_period','inj_duty','inj_t_on','inj_dwell','K_hall'};
for i = 1:numel(c)
    add_block('simulink/Sources/Constant', sprintf('%s/c%d', p, i), 'Value', c{i}, ...
        'Position', [30 230+35*i 80 250+35*i]);
end
f = [p '/gen'];
add_block('simulink/User-Defined Functions/MATLAB Function', f, 'Position', [200 170 300 700]);
set_mlfcn(f, inj_gen_code(), {'t', '1'; 'ch_id', '1'; 'channel', '[1 2]'; 'shape', '[1 2]'; 'amp', '[1 2]'; 'k', '[1 2]'; 'f', '[1 2]'; 'ph', '[1 2]'; ...
    'period', '1'; 'duty', '1'; 't_on', '1'; 'dwell', '1'; 'K_hall', '1'; 'dy', '1'});
add_block('simulink/Signal Attributes/Rate Transition', [p '/RT'], 'Position', [340 175 380 205], ...
    'OutPortSampleTime', 'Ts_out', 'Integrity', 'on', 'Deterministic', 'on');
add_block('simulink/Math Operations/Sum', [p '/Sum'], 'Inputs', '++', 'Position', [440 85 470 115]);
add_line(p, 't/1', 'gen/1');
for i = 1:numel(c), add_line(p, sprintf('c%d/1', i), sprintf('gen/%d', i+1)); end
add_line(p, 'gen/1', 'RT/1'); add_line(p, 'RT/1', 'Sum/2');
add_line(p, 'y_real/1', 'Sum/1'); add_line(p, 'Sum/1', 'y_int/1');
m = Simulink.Mask.create(p);
m.addParameter('Name','ch_id','Prompt','Channel id (1 Vdc 2 Vac 3 Iac 4 Vbat 5 Ibat)','Value','1');
m.addParameter('Name','Ts_inj','Prompt','Generator sample time','Value','Ts_Control');
m.addParameter('Name','Ts_out','Prompt','Output sample time','Value','Ts_Power');
m.Type = 'Disturbance Injector';
m.Display = 'disp(sprintf(''inject\\nch %d'', ch_id))';
end

function s = inj_gen_code()
s = sprintf([ ...
'function dy = gen(t, ch_id, channel, shape, amp, k, f, ph, period, duty, t_on, dwell, K_hall)\n' ...
'%% Equivalent measurement bias dy(t).  channel/shape/amp/k/f/ph are 1x2 so two\n' ...
'%% channels can be disturbed at once (E-MUL-01); an entry with channel 0 is off.\n' ...
'dy = 0;\n' ...
'tau = t - t_on;\n' ...
'if tau < 0 || tau >= dwell, return; end\n' ...
'for i = 1:numel(channel)\n' ...
'    if channel(i) ~= ch_id, continue; end\n' ...
'    a = amp(i);\n' ...
'    switch shape(i)\n' ...
'        case 1, d = a;\n' ...
'        case 2, d = sign(a)*min(abs(a), k(i)*tau);\n' ...
'        case 3, d = a*sin(2*pi*f(i)*t + ph(i)*pi/180);\n' ...
'        case 4, x = mod(tau, period)/period; d = a*(1 - abs(2*x - 1));\n' ...
'        case 5, d = a*double(mod(tau, period) < duty*period);\n' ...
'        case 6, d = K_hall*(0.2 + 0.5*sin(2*pi*f(i)*t));\n' ...
'        otherwise, d = 0;\n' ...
'    end\n' ...
'    dy = dy + d;\n' ...
'end\n']);
end

% --------------------------------------------------------- protection ----
function make_protection(p, pos)
add_block('built-in/Subsystem', p, 'Position', pos);
delete_lines_in(p);
names = {'Vdc_real','Iac_real','Vbat_real','Ibat_real'};
for i = 1:4
    add_block('simulink/Sources/In1', [p '/' names{i}], 'Position', [30 40*i+3 60 40*i+17]);
end
% Vdc/Iac come from the power stage at Ts_Power; bring them to Ts_chg
for i = 1:2
    add_block('simulink/Signal Attributes/Rate Transition', sprintf('%s/RT%d', p, i), ...
        'Position', [100 40*i 140 40*i+20], 'OutPortSampleTime', 'Ts_chg', 'Integrity', 'on', 'Deterministic', 'on');
    add_line(p, sprintf('%s/1', names{i}), sprintf('RT%d/1', i));
end
add_block('simulink/Sources/Digital Clock', [p '/t'], 'Position', [30 230 80 260], 'SampleTime', 'Ts_chg');
add_block('simulink/Sources/Constant', [p '/thr'], 'Value', 'prot_thr', 'Position', [30 280 80 300]);
add_block('simulink/Sources/Constant', [p '/Ts'],  'Value', 'Ts_chg',   'Position', [30 320 80 340]);
add_block('simulink/Discrete/Unit Delay', [p '/x'], 'Position', [30 370 80 400], ...
    'SampleTime', 'Ts_chg', 'InitialCondition', 'zeros(1,7)');
f = [p '/prot'];
add_block('simulink/User-Defined Functions/MATLAB Function', f, 'Position', [220 40 330 420]);
set_mlfcn(f, prot_code(), {'x', '[1 7]'; 'xn', '[1 7]'; 'y', '[1 2]'; 'thr', '[1 7]'; 'Vdc', '1'; 'Iac', '1'; 'Vbat', '1'; 'Ibat', '1'; 't', '1'; 'Ts', '1'});
add_block('simulink/Sinks/Out1', [p '/trip'], 'Position', [420 93 450 107]);
add_line(p, 'RT1/1', 'prot/1'); add_line(p, 'RT2/1', 'prot/2');
add_line(p, 'Vbat_real/1', 'prot/3'); add_line(p, 'Ibat_real/1', 'prot/4');
add_line(p, 't/1', 'prot/5'); add_line(p, 'x/1', 'prot/6'); add_line(p, 'thr/1', 'prot/7'); add_line(p, 'Ts/1', 'prot/8');
add_line(p, 'prot/1', 'trip/1'); add_line(p, 'prot/2', 'x/1');
m = Simulink.Mask.create(p); m.Type = 'Protection Monitor';
m.Display = 'disp(''protect'')';
end

function s = prot_code()
s = sprintf([ ...
'function [y, xn] = prot(Vdc, Iac, Vbat, Ibat, t, x, thr, Ts)\n' ...
'%% x = [tUV tOV tOC tBOV tBOC trip t_trip]; thr = [UV OV OC BOV BOC hold t_arm]\n' ...
'%% OC / BOC trip immediately, the others after |hold| seconds.  Armed from\n' ...
'%% t_arm on, so the start-up inrush before the snapshot is ignored.\n' ...
'xn = x;\n' ...
'if t < thr(7), xn = zeros(1,7); y = [0 0]; return; end\n' ...
'cond = [Vdc < thr(1), Vdc > thr(2), abs(Iac) > thr(3), Vbat > thr(4), Ibat > thr(5)];\n' ...
'hold = [thr(6) thr(6) 0 thr(6) 0];\n' ...
'for i = 1:5\n' ...
'    if cond(i), xn(i) = x(i) + Ts; else, xn(i) = 0; end\n' ...
'end\n' ...
'if x(6) == 0\n' ...
'    for i = 1:5\n' ...
'        if cond(i) && xn(i) > hold(i), xn(6) = i; xn(7) = t; break; end\n' ...
'    end\n' ...
'end\n' ...
'y = xn(6:7);\n']);
end

% ------------------------------------------------------------ charger ----
function make_charger(p, pos)
add_block('built-in/Subsystem', p, 'Position', pos);
delete_lines_in(p);
% physical ports on the DC bus
add_block('nesl_utility/Connection Port', [p '/+'], 'Position', [30 40 60 60], 'Side', 'Left', 'Port', '1');
add_block('nesl_utility/Connection Port', [p '/-'], 'Position', [30 140 60 160], 'Side', 'Left', 'Port', '2');
add_block('powerlib/Electrical Sources/Controlled Current Source', [p '/Iload'], ...
    'Position', [150 70 190 130], 'Orientation', 'down');
try, set_param([p '/Iload'], 'Init', 'off'); catch, end
try, set_param([p '/Iload'], 'SourceType', 'DC'); catch, end
try, set_param([p '/Iload'], 'Measurements', 'None'); catch, end
hI = get_param([p '/Iload'], 'PortHandles');
hP = get_param([p '/+'], 'PortHandles'); hN = get_param([p '/-'], 'PortHandles');
% Orientation down: LConn is on top, RConn at the bottom.  Polarity is checked
% by build_injection('probe'); the sign is applied in the plant function (I_SIGN).
add_line(p, hP.RConn(1), hI.LConn(1)); add_line(p, hN.RConn(1), hI.RConn(1));
% signal side
add_block('simulink/Sources/In1', [p '/Vdc'], 'Position', [30 243 60 257]);
add_block('simulink/Signal Attributes/Rate Transition', [p '/RTin'], 'Position', [100 240 140 260], ...
    'OutPortSampleTime', 'Ts_chg', 'Integrity', 'on', 'Deterministic', 'on');
add_line(p, 'Vdc/1', 'RTin/1');
% charge-current enable ramp: Icc*min(1, max(0,(t-t_chg_on)*k_chg/Icc))
add_block('simulink/Sources/Digital Clock', [p '/t'], 'Position', [30 300 80 330], 'SampleTime', 'Ts_chg');
add_block('simulink/Sources/Constant', [p '/pp'], 'Value', 'chg_par', 'Position', [30 360 80 380]);
add_block('simulink/Sources/Constant', [p '/pc'], 'Value', 'chg_ctrl_par', 'Position', [30 400 80 420]);
add_block('simulink/Discrete/Unit Delay', [p '/Ibat'], 'Position', [30 450 80 480], 'SampleTime', 'Ts_chg', 'InitialCondition', '0');
add_block('simulink/Discrete/Unit Delay', [p '/xc'],   'Position', [30 500 80 530], 'SampleTime', 'Ts_chg', 'InitialCondition', 'zeros(1,4)');
% plant: [Ibat_next, Isrc] = plant(D, Ibat, Vdc, pp, t);  batt: [Vbat, P] = batt(Ibat, pp)
% (battery voltage is computed from the state only, so no algebraic loop
%  ctrl -> plant -> Vbat -> ctrl)
add_block('simulink/User-Defined Functions/MATLAB Function', [p '/plant'], 'Position', [300 420 400 560]);
set_mlfcn([p '/plant'], plant_code(), {'D', '1'; 'Ibat', '1'; 'Vdc', '1'; 'pp', '[1 6]'; 't', '1'; 'Ibat_next', '1'; 'Isrc', '1'});
add_block('simulink/User-Defined Functions/MATLAB Function', [p '/batt'], 'Position', [300 600 400 680]);
set_mlfcn([p '/batt'], batt_code(), {'Ibat', '1'; 'pp', '[1 6]'; 'Vbat', '1'; 'P', '1'});
% injectors on the two measurement chains
add_block('MyLibrary/Disturbance Injector', [p '/inj_Vbat'], 'Position', [480 400 560 440], 'ch_id', '4', 'Ts_inj', 'Ts_chg', 'Ts_out', 'Ts_chg');
add_block('MyLibrary/Disturbance Injector', [p '/inj_Ibat'], 'Position', [480 470 560 510], 'ch_id', '5', 'Ts_inj', 'Ts_chg', 'Ts_out', 'Ts_chg');
% controller: [D, Iref, xn] = ctrl(Vbat_m, Ibat_m, Vdc, t, xc, pc)
add_block('simulink/User-Defined Functions/MATLAB Function', [p '/ctrl'], 'Position', [660 240 760 400]);
set_mlfcn([p '/ctrl'], ctrl_code(), {'Vbat_m', '1'; 'Ibat_m', '1'; 'Vdc', '1'; 't', '1'; 'x', '[1 4]'; 'pc', '[1 12]'; 'D', '1'; 'Iref', '1'; 'xn', '[1 4]'; 'state', '1'});
add_block('simulink/Signal Attributes/Rate Transition', [p '/RTout'], 'Position', [300 90 340 110], ...
    'OutPortSampleTime', 'Ts_Power', 'Integrity', 'on', 'Deterministic', 'on');
add_block('simulink/Signal Routing/Mux', [p '/Mux'], 'Inputs', '9', 'Position', [880 300 885 560]);
add_block('simulink/Sinks/Out1', [p '/sig'], 'Position', [940 423 970 437]);
% wiring
add_line(p, 'ctrl/1', 'plant/1');            % D
add_line(p, 'Ibat/1', 'plant/2');            % Ibat state
add_line(p, 'RTin/1', 'plant/3');            % Vdc
add_line(p, 'pp/1',   'plant/4');
add_line(p, 't/1',    'plant/5');
add_line(p, 'plant/1', 'Ibat/1');            % Ibat_next -> state
add_line(p, 'Ibat/1',  'batt/1'); add_line(p, 'pp/1', 'batt/2');
add_line(p, 'batt/1', 'inj_Vbat/1');         % Vbat real
add_line(p, 'Ibat/1',  'inj_Ibat/1');        % Ibat real
add_line(p, 'inj_Vbat/1', 'ctrl/1'); add_line(p, 'inj_Ibat/1', 'ctrl/2');
add_line(p, 'RTin/1', 'ctrl/3'); add_line(p, 't/1', 'ctrl/4'); add_line(p, 'xc/1', 'ctrl/5'); add_line(p, 'pc/1', 'ctrl/6');
add_line(p, 'ctrl/3', 'xc/1');
add_line(p, 'plant/2', 'RTout/1'); add_line(p, 'RTout/1', 'Iload/1');
% output vector
add_line(p, 'batt/1', 'Mux/1');   add_line(p, 'Ibat/1', 'Mux/2');
add_line(p, 'inj_Vbat/1', 'Mux/3'); add_line(p, 'inj_Ibat/1', 'Mux/4');
add_line(p, 'ctrl/1', 'Mux/5');   add_line(p, 'ctrl/4', 'Mux/6');    % D, state
add_line(p, 'ctrl/2', 'Mux/7');   add_line(p, 'batt/2', 'Mux/8');    % Iref_bat, P_charge
add_line(p, 'plant/2', 'Mux/9');                                     % Isrc (signed, as sent to the source)
add_line(p, 'Mux/1', 'sig/1');
m = Simulink.Mask.create(p); m.Type = 'Charger Stage';
m.Display = 'disp(''charger\\nbuck + battery\\nCC/CV'')';
end

function s = plant_code()
s = sprintf([ ...
'function [Ibat_next, Isrc] = plant(D, Ibat, Vdc, pp, t)\n' ...
'%% Averaged buck.  pp = [L_chg Voc Rint Ts_chg I_SIGN t_chg_on]\n' ...
'%% Ibat is the inductor/battery current state (>= 0, diode conduction).\n' ...
'L = pp(1); Voc = pp(2); Rint = pp(3); Ts = pp(4); sgn = pp(5);\n' ...
'Vbat = Voc + Rint*Ibat;\n' ...
'Idc = D*Ibat;                      %% lossless averaged input current\n' ...
'Isrc = sgn*Idc;\n' ...
'if t < pp(6)\n' ...
'    Ibat_next = 0;\n' ...
'else\n' ...
'    Ibat_next = Ibat + Ts/L*(D*Vdc - Vbat);\n' ...
'    if Ibat_next < 0, Ibat_next = 0; end\n' ...
'end\n']);
end

function s = batt_code()
s = sprintf([ ...
'function [Vbat, P] = batt(Ibat, pp)\n' ...
'%% Battery terminal voltage and charging power from the current state.\n' ...
'Vbat = pp(2) + pp(3)*Ibat;\n' ...
'P = Vbat*Ibat;\n']);
end

function s = ctrl_code()
s = sprintf([ ...
'function [D, Iref, xn, state] = ctrl(Vbat_m, Ibat_m, Vdc, t, x, pc)\n' ...
'%% CC/CV charge controller.  x = [state tmr xv xi]  (0 CC, 1 CV)\n' ...
'%% pc = [Icc Vcv Vhys Thys Kp_v Ki_v Kp_i Ki_i Ts Dmax t_on k_ramp]\n' ...
'Icc=pc(1); Vcv=pc(2); Vhys=pc(3); Thys=pc(4); Kpv=pc(5); Kiv=pc(6);\n' ...
'Kpi=pc(7); Kii=pc(8); Ts=pc(9); Dmax=pc(10); t_on=pc(11); kr=pc(12);\n' ...
'st = x(1); tmr = x(2); xv = x(3); xi = x(4);\n' ...
'Iramp = min(Icc, max(0, (t - t_on)*kr));\n' ...
'%% --- state machine\n' ...
'if st == 0\n' ...
'    if Vbat_m >= Vcv, st = 1; tmr = 0; end\n' ...
'else\n' ...
'    if Vbat_m <= Vcv - Vhys, tmr = tmr + Ts; else, tmr = 0; end\n' ...
'    if tmr >= Thys, st = 0; tmr = 0; end\n' ...
'end\n' ...
'%% --- outer voltage loop (CV only), preloaded to Iramp in CC\n' ...
'if st == 1\n' ...
'    ev = Vcv - Vbat_m;\n' ...
'    xv = xv + Kiv*ev*Ts;\n' ...
'    Iref = Kpv*ev + xv;\n' ...
'    if Iref > Iramp, Iref = Iramp; xv = min(xv, Iramp); end\n' ...
'    if Iref < 0,     Iref = 0;     xv = max(xv, 0); end\n' ...
'else\n' ...
'    Iref = Iramp; xv = Iramp;\n' ...
'end\n' ...
'%% --- inner current loop with duty feed-forward\n' ...
'ei = Iref - Ibat_m;\n' ...
'xi = xi + Kii*ei*Ts;\n' ...
'Dff = Vbat_m / max(Vdc, 50);\n' ...
'D = Dff + Kpi*ei + xi;\n' ...
'if D > Dmax, D = Dmax; xi = xi - Kii*ei*Ts; end\n' ...
'if D < 0,    D = 0;    xi = xi - Kii*ei*Ts; end\n' ...
'if t < t_on, D = 0; xi = 0; end\n' ...
'xn = [st tmr xv xi];\n' ...
'state = st;\n']);
end

% =========================================================================
function build_model()
mdl = 'PV_MEV'; ev = [mdl '/EV System'];
load_system(mdl); load_system('MyLibrary');
% --- 1. load branch -> charger stage
% NOTE: never "clean up" lines by SrcBlockHandle here - SPS physical lines have
% no source block and would be deleted, which opens the whole DC bus.
% Ro1 -> Rbleed (100 kOhm).  Ro2 + Ideal Switch + Step2 are kept as a
% start-up preload (R_pre, on until t_pre_off): the CRPR voltage loop winds
% up and keeps boosting on an unloaded bus (Vdc > 900 V before the charger
% comes in), so the bus must carry load during warm-up.
if getSimulinkBlockHandle([ev '/Ro1']) ~= -1, set_param([ev '/Ro1'], 'Name', 'Rbleed'); end
set_param([ev '/Rbleed'], 'Resistance', 'R_bleed');
if getSimulinkBlockHandle([ev '/Ro2']) ~= -1, set_param([ev '/Ro2'], 'Name', 'Rpre'); end
set_param([ev '/Rpre'], 'Resistance', 'R_pre');
set_param([ev '/Step2'], 'Time', 't_pre_off', 'Before', '1', 'After', '0');
chg = [ev '/Charger Stage'];
if getSimulinkBlockHandle(chg) ~= -1, delete_block(chg); end
add_block('MyLibrary/Charger Stage', chg, 'Position', [1790 1085 1900 1185]);
hR = get_param([ev '/Rbleed'], 'PortHandles'); hC = get_param(chg, 'PortHandles');
% Rbleed is vertical (RLC branch): LConn(1) top, RConn(1) bottom.  Branch the
% charger ports off the same nodes.
add_line(ev, hR.LConn(1), hC.LConn(1), 'autorouting', 'on');
add_line(ev, hR.RConn(1), hC.LConn(2), 'autorouting', 'on');
add_block('simulink/Signal Routing/From', [ev '/From_Vdc_chg'], 'GotoTag', 'Vdc_PFC', 'Position', [1700 1200 1760 1220]);
add_line(ev, 'From_Vdc_chg/1', 'Charger Stage/1', 'autorouting', 'on');
add_block('simulink/Signal Routing/Goto', [ev '/Goto_chg'], 'GotoTag', 'chg_sig', 'Position', [1940 1125 2000 1145]);
add_line(ev, 'Charger Stage/1', 'Goto_chg/1');
% --- 2. injectors on the three PFC measurement lines
spec = {'From16', 2, 1; 'From18', 3, 2; 'From19', 4, 3};     % From, PFC port, ch_id
for i = 1:size(spec,1)
    fr = [ev '/' spec{i,1}]; nm = sprintf('inj_ch%d', spec{i,3}); ib = [ev '/' nm];
    if getSimulinkBlockHandle(ib) ~= -1
        continue;                                          % already spliced
    end
    ph = get_param(fr, 'PortHandles'); ln = get_param(ph.Outport(1), 'Line');
    if ln ~= -1, delete_line(ln); end
    fpos = get_param(fr, 'Position');
    add_block('MyLibrary/Disturbance Injector', ib, 'Position', [fpos(1)+80 fpos(2)-8 fpos(1)+140 fpos(4)+8], ...
        'ch_id', num2str(spec{i,3}), 'Ts_inj', 'Ts_Control', 'Ts_out', 'Ts_Power');
    add_line(ev, [spec{i,1} '/1'], [nm '/1']);
    add_line(ev, [nm '/1'], sprintf('PFC Control/%d', spec{i,2}), 'autorouting', 'on');
end
% --- 3. protection monitor (real quantities only)
pm = [ev '/Protection Monitor'];
if getSimulinkBlockHandle(pm) ~= -1, delete_block(pm); end
add_block('MyLibrary/Protection Monitor', pm, 'Position', [2110 1230 2200 1330]);
add_block('simulink/Signal Routing/From', [ev '/From_pm1'], 'GotoTag', 'Vdc_PFC', 'Position', [1990 1235 2050 1255]);
add_block('simulink/Signal Routing/From', [ev '/From_pm2'], 'GotoTag', 'Iac',     'Position', [1990 1265 2050 1285]);
add_block('simulink/Signal Routing/From', [ev '/From_pm3'], 'GotoTag', 'chg_sig', 'Position', [1960 1295 2020 1315]);
add_block('simulink/Signal Routing/Demux', [ev '/Demux_chg'], 'Outputs', '9', 'Position', [2050 1290 2055 1360]);
add_line(ev, 'From_pm1/1', 'Protection Monitor/1'); add_line(ev, 'From_pm2/1', 'Protection Monitor/2');
add_line(ev, 'From_pm3/1', 'Demux_chg/1');
add_line(ev, 'Demux_chg/1', 'Protection Monitor/3'); add_line(ev, 'Demux_chg/2', 'Protection Monitor/4');
for k = 3:9
    add_block('simulink/Sinks/Terminator', sprintf('%s/T_chg%d', ev, k), 'Position', [2080 1290+10*k 2095 1300+10*k]);
    add_line(ev, sprintf('Demux_chg/%d', k), sprintf('T_chg%d/1', k));
end
add_block('simulink/Sinks/Terminator', [ev '/T_pm'], 'Position', [2230 1275 2245 1285]);
add_line(ev, 'Protection Monitor/1', 'T_pm/1');
fprintf('[build] DC-bus connectivity after splice:\n'); check_bus(ev);
save_system(mdl); close_system(mdl); close_system('MyLibrary');
fprintf('[build] PV_MEV saved\n');
end

% =========================================================================
function probe_ccs()
% Tiny SPS circuit: 400 V source, 1 ohm, then the Charger Stage wiring
% convention (+ on LConn(1) of a down-oriented Controlled Current Source).
% If V(+,-) drops below 400 V with a positive command, the source is a load.
t = 'ccs_probe'; if bdIsLoaded(t), close_system(t,0); end
new_system(t); open_system(t);
add_block('powerlib/powergui', [t '/powergui'], 'Position', [10 10 80 40]);
set_param([t '/powergui'], 'SimulationMode', 'Discrete', 'SampleTime', '1e-5');
add_block('powerlib/Electrical Sources/DC Voltage Source', [t '/V'], 'Position', [50 100 80 140], 'Amplitude', '400');
add_block('powerlib/Elements/Series RLC Branch', [t '/R'], 'Position', [130 60 170 80], 'BranchType', 'R', 'Resistance', '1');
add_block('powerlib/Electrical Sources/Controlled Current Source', [t '/I'], 'Position', [230 100 270 140], 'Orientation', 'down');
try, set_param([t '/I'], 'Init', 'off'); catch, end
try, set_param([t '/I'], 'SourceType', 'DC'); catch, end
add_block('powerlib/Measurements/Voltage Measurement', [t '/Vm'], 'Position', [320 100 350 140]);
add_block('simulink/Sources/Constant', [t '/c'], 'Value', '10', 'Position', [140 110 170 130]);
add_block('simulink/Sinks/To Workspace', [t '/w'], 'VariableName', 'vprobe', 'Position', [400 110 450 130]);
h = @(b) get_param([t '/' b], 'PortHandles');
add_line(t, h('V').LConn(1), h('R').LConn(1));
add_line(t, h('R').RConn(1), h('I').LConn(1));
vm = h('Vm'); vmp = [vm.LConn vm.RConn];              % + and - terminals
add_line(t, h('R').RConn(1), vmp(1));
add_line(t, h('V').RConn(1), h('I').RConn(1));
add_line(t, h('V').RConn(1), vmp(2));
add_line(t, 'c/1', 'I/1'); add_line(t, 'Vm/1', 'w/1');
so = sim(t, 'StopTime', '1e-3', 'ReturnWorkspaceOutputs', 'on');
v = so.vprobe; if isa(v,'timeseries'), v = v.Data; end
% The DC Voltage Source's LConn is its NEGATIVE terminal, so V(+,-) reads
% -400 V unloaded.  A load (source sinking current at its LConn) makes the
% node more negative: |V| = 410 V -> I_SIGN = +1.  Confirmed in the model:
% I_SIGN = -1 drove Vdc to 1430 V with Pdc < 0.
fprintf('[probe] |V(+,-)| = %.1f V with +10 A command  ->  I_SIGN = %+d\n', abs(v(end)), 2*(abs(v(end)) > 400) - 1);
close_system(t, 0);
end

% =========================================================================
function set_mlfcn(blk, code, sizes)
% sizes: {name, '[1 4]'; ...} explicit sizes for data that sit in feedback
% loops through Unit Delays (Simulink cannot infer them otherwise).
rt = sfroot; ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', blk);
if isempty(ch), error('MATLAB Function chart not found: %s', blk); end
ch = ch(1); ch.Script = code;
if nargin > 2
    for i = 1:size(sizes, 1)
        d = ch.find('-isa', 'Stateflow.Data', 'Name', sizes{i, 1});
        if isempty(d), error('data %s not found in %s', sizes{i, 1}, blk); end
        d(1).Props.Array.Size = sizes{i, 2}; d(1).DataType = 'double';
    end
end
end
function delete_lines_in(p)
l = find_system(p, 'SearchDepth', 1, 'FindAll', 'on', 'Type', 'line');
for k = 1:numel(l), try, delete_line(l(k)); catch, end, end
b = find_system(p, 'SearchDepth', 1); b = b(~strcmp(b, p));
for k = 1:numel(b), try, delete_block(b{k}); catch, end, end
end
function check_bus(ev)
% print the physical neighbours of the DC-bus blocks (sanity check after the splice)
for b = {'C', 'Rbleed', 'Rpre', 'Ideal Switch', 'Charger Stage', 'Current Measurement4', 'Voltage Measurement1', 'Diode1', 'FET2'}
    pc = get_param([ev '/' b{1}], 'PortConnectivity');
    for p = pc'
        if isempty(regexp(p.Type, 'Conn', 'once')), continue; end
        nb = {}; for h = [p.SrcBlock(:); p.DstBlock(:)]', if h > 0, nb{end+1} = get_param(h, 'Name'); end, end %#ok<AGROW>
        fprintf('  %-22s %-7s -> %s\n', b{1}, p.Type, strjoin(unique(nb), ', '));
    end
end
end
