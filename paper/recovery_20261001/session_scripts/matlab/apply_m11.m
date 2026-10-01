% apply_m11.m: handover-consistency measures on three mask bits (review-3 P0-A)
%   M11 (2048): protection-consistent voltage-loop output limit (55 A) while any correction is active, anti-windup inside
%   M12 (4096): charger current-reference slew limit (400 A/s, rising) at every re-engagement, not only at power-up
%   M13 (8192): entry-only slew (1000 V/s) of the bus correction for 0.1 s after the Vdc flag rises
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd); mdl='PV_MEV'; load_system(mdl);
pc=[mdl '/EV System/PFC Control']; cs=[mdl '/EV System/Charger Stage']; sr=[pc '/Speed Regulator2'];
clean=@(s) strrep(s,newline,' ');
% ---------------- 1. voltage regulator: dynamic limit input --------------------------------------------
b=find_system(sr,'SearchDepth',1,'LookUnderMasks','all'); H=containers.Map;
for i=2:numel(b), H(clean(strrep(b{i},[sr '/'],'')))=get_param(b{i},'Handle'); end
RO=H('Relational Operator'); RO1=H('Relational Operator1'); S6=H('Sum6'); OUT=H('Out'); SAT=H('Saturation2');
lh=get_param(RO,'LineHandles'); delete_line(lh.Inport(2)); lh=get_param(RO1,'LineHandles'); delete_line(lh.Inport(2));
delete_block(H('Constant1')); delete_block(H('Constant2'));
lh=get_param(SAT,'LineHandles'); delete_line(lh.Inport(1)); delete_line(lh.Outport(1)); psat=get_param(SAT,'Position'); delete_block(SAT);
hin=add_block('simulink/Sources/In1',[sr '/Ilim'],'Position',[30 300 60 314]);
hneg=add_block('simulink/Math Operations/Gain',[sr '/neg'],'Gain','-1','Position',[110 330 140 360]);
hsd=add_block('simulink/Discontinuities/Saturation Dynamic',[sr '/SatDyn'],'Position',psat+[0 -10 0 10]);
gp=@(h,k) subsref(get_param(h,'PortHandles'),substruct('.','Outport','()',{k}));
ip=@(h,k) subsref(get_param(h,'PortHandles'),substruct('.','Inport','()',{k}));
add_line(sr,gp(hin,1),ip(RO,2),'autorouting','on'); add_line(sr,gp(hin,1),ip(hneg,1),'autorouting','on');
add_line(sr,gp(hneg,1),ip(RO1,2),'autorouting','on');
add_line(sr,gp(hin,1),ip(hsd,1),'autorouting','on'); add_line(sr,gp(S6,1),ip(hsd,2),'autorouting','on');
add_line(sr,gp(hneg,1),ip(hsd,3),'autorouting','on'); add_line(sr,gp(hsd,1),ip(OUT,1),'autorouting','on');
fprintf('[regulator] Ilim inport, dynamic saturation, anti-windup on Ilim\n');
% ---------------- 2. Mitigation chart: Ilim output, M11 / M13 --------------------------------------------
rt=sfroot; ch=rt.find('-isa','Stateflow.EMChart','Path',[pc '/Mitigation']); sc=ch(1).Script;
sc=strrep(sc,'function [Vdc_fb, Iref_out, Vin_out, iL_out, hold, g_alpha, dbg] = mitigation(flags, amps, Vdc, Vac, th, iL, Iref, chg, mask, use_det, force, Ts, t_ramp, tnow, t_arm, inj_ch, inj_sh, inj_t0, inj_dw)', ...
             'function [Vdc_fb, Iref_out, Vin_out, iL_out, hold, g_alpha, dbg, Ilim] = mitigation(flags, amps, Vdc, Vac, th, iL, Iref, chg, mask, use_det, force, Ts, t_ramp, tnow, t_arm, inj_ch, inj_sh, inj_t0, inj_dw, Ilim0)');
sc=strrep(sc,'% M9 (512): slew-limited introduction / removal of the Vdc correction (bumpless), MPCC_R_B', ...
   ['% M9 (512): slew-limited introduction / removal of the Vdc correction (bumpless), MPCC_R_B' newline ...
    '% M11 (2048): protection-consistent voltage-loop limit Ilim = 55 A (OC 65 A less ripple and an uncorrected DC offset) while any correction is active' newline ...
    '% M13 (8192): entry-only slew (1000 V/s) of the bus correction during the first 0.1 s after the Vdc flag rises (M9 acts on the fallback path only)']);
sc=strrep(sc,'persistent g dVf Iref_prev pkp pkn Vamp th_prev init eb', 'persistent g dVf Iref_prev pkp pkn Vamp th_prev init eb t_rise');
sc=strrep(sc,'if isempty(init), g = zeros(1, 5); dVf = 0; Iref_prev = 0; pkp = 0; pkn = 0; Vamp = 0; th_prev = 0; eb = 0; init = 1; end', ...
             'if isempty(init), g = zeros(1, 5); dVf = 0; Iref_prev = 0; pkp = 0; pkn = 0; Vamp = 0; th_prev = 0; eb = 0; t_rise = -1; init = 1; end');
sc=strrep(sc,['for c = 1:5' newline '    if f(c) > 0.5, g(c) = 1;'], ['g1_prev = g(1);' newline 'for c = 1:5' newline '    if f(c) > 0.5, g(c) = 1;']);
sc=strrep(sc,['    else, g(c) = 0; end' newline 'end' newline '% --- Vdc chain'], ['    else, g(c) = 0; end' newline 'end' newline 'if g(1) > 0 && g1_prev == 0, t_rise = tnow; end   % rising edge of the bus correction (M13 entry window)' newline '% --- Vdc chain']);
old=['else' newline '    if g(1) > 0, dVf = dVf + (Ts / 0.005) * (dV - dVf); else, dVf = 0; end' newline '    if M(0), Vdc_fb = Vdc - g(1) * dVf; end' newline 'end'];
new=['else' newline '    if g(1) > 0' newline '        if M(13) && tnow < t_rise + 0.1' newline ...
     '            lim = 1000 * Ts; stp = min(max(dV - dVf, -lim), lim); dVf = dVf + stp;   % M13: the correction enters at 1000 V/s, leaves at once' newline ...
     '        else, dVf = dVf + (Ts / 0.005) * (dV - dVf); end' newline '    else, dVf = 0; end' newline '    if M(0), Vdc_fb = Vdc - g(1) * dVf; end' newline 'end' newline ...
     '% --- M11: while a correction is active the voltage loop may not command a current the protection would trip on' newline ...
     'Ilim = Ilim0;' newline 'if M(11) && any(g > 0), Ilim = 55; end'];
assert(contains(sc,old)); sc=strrep(sc,old,new);
sc=strrep(sc,'dbg = [g(1), dVf, double(phys_ok), Vamp, g(3), eb];','dbg = [g(1), dVf, double(phys_ok), Vamp, g(3), eb, Ilim];');
assert(contains(sc,'Ilim0') && contains(sc,'M(11)') && contains(sc,'M(13)') && contains(sc,'t_rise = tnow'));
ch(1).Script=sc;
dd=ch(1).find('-isa','Stateflow.Data'); ref=dd(strcmp({dd.Name},'Ts')); fprintf('[chart data] Ts: scope=%s size=%s type=%s\n', ref.Scope, ref.Props.Array.Size, ref.DataType);
for nm={'Ilim0','Ilim'}, d=dd(strcmp({dd.Name},nm{1})); fprintf('[chart data] %s: scope=%s size=%s type=%s -> ', nm{1}, d.Scope, d.Props.Array.Size, d.DataType); d.Props.Array.Size='1'; d.DataType='double'; fprintf('size=%s type=%s\n', d.Props.Array.Size, d.DataType); end
d=dd(strcmp({dd.Name},'dbg')); fprintf('[chart data] dbg size=%s -> ', d.Props.Array.Size); if ~strcmp(d.Props.Array.Size,'-1'), d.Props.Array.Size='[1 7]'; end; fprintf('%s\n', d.Props.Array.Size);
ch2=rt.find('-isa','Stateflow.EMChart','Path',[pc '/Mitigation Iref']); dd2=ch2(1).find('-isa','Stateflow.Data'); d2=dd2(strcmp({dd2.Name},'dbg')); fprintf('[Mitigation Iref] dbg size=%s -> ', d2.Props.Array.Size); if ~strcmp(d2.Props.Array.Size,'-1'), d2.Props.Array.Size='[1 7]'; end; fprintf('%s\n', d2.Props.Array.Size);
for k=1:numel(dd), fprintf('   %-10s %-9s %s\n', dd(k).Name, dd(k).Scope, dd(k).Props.Array.Size); end
hc=add_block('simulink/Sources/Constant',[pc '/mit_ilim0'],'Value','Limit_V','Position',[5200 1810 5250 1830]);
hm=get_param([pc '/Mitigation'],'Handle'); hsr=get_param(sr,'Handle');
add_line(pc,gp(hc,1),ip(hm,20),'autorouting','on'); add_line(pc,gp(hm,8),ip(hsr,3),'autorouting','on');
fprintf('[mitigation] Ilim0 input (Limit_V), Ilim output -> Speed Regulator2:3\n');
% ---------------- 3. charger regulator: slew-limited reference (M12 via pc(13)) ---------------------------
ch=rt.find('-isa','Stateflow.EMChart','Path',[cs '/ctrl']); sc=ch(1).Script;
sc=strrep(sc,'% x = [state tmr xv xi]  (0 CC, 1 CV)','% x = [state tmr xv xi Iref_prev]  (0 CC, 1 CV)');
sc=strrep(sc,'% pc = [Icc Vcv Vhys Thys Kp_v Ki_v Kp_i Ki_i Ts Dmax t_on k_ramp]','% pc = [Icc Vcv Vhys Thys Kp_v Ki_v Kp_i Ki_i Ts Dmax t_on k_ramp k_soft]; k_soft > 0 (M12): rising slew limit on Iref at every re-engagement');
sc=strrep(sc,'Kpi=pc(7); Kii=pc(8); Ts=pc(9); Dmax=pc(10); t_on=pc(11); kr=pc(12);','Kpi=pc(7); Kii=pc(8); Ts=pc(9); Dmax=pc(10); t_on=pc(11); kr=pc(12); kso=0; if numel(pc) >= 13, kso=pc(13); end');
sc=strrep(sc,'st = x(1); tmr = x(2); xv = x(3); xi = x(4);','st = x(1); tmr = x(2); xv = x(3); xi = x(4); Iprev = x(5);');
old=['else' newline '    Iref = Iramp; xv = Iramp;' newline 'end'];
new=['else' newline '    Iref = Iramp; xv = Iramp;' newline 'end' newline ...
     'if kso > 0 && t >= t_on && Iref > Iprev + kso*Ts, Iref = Iprev + kso*Ts; xv = min(xv, Iref); end   % M12: soft re-engagement'];
assert(contains(sc,old)); sc=strrep(sc,old,new);
sc=strrep(sc,'xn = [st tmr xv xi];','xn = [st tmr xv xi Iref];');
assert(contains(sc,'kso') && contains(sc,'Iprev = x(5)')); ch(1).Script=sc;
dd=ch(1).find('-isa','Stateflow.Data'); sz=struct('x','[1 5]','xn','[1 5]','pc','[1 13]');
for nm={'x','xn','pc'}, d=dd(strcmp({dd.Name},nm{1})); d.Props.Array.Size=sz.(nm{1}); fprintf('[ctrl data] %s: scope=%s size=%s type=%s\n', nm{1}, d.Scope, d.Props.Array.Size, d.DataType); end
set_param([cs '/xc'],'InitialCondition','zeros(1,5)');
fprintf('[charger] Iref slew (pc(13)), state vector 5\n');
% ---------------- 4. compile check and save ------------------------------------------------------------------
assignin('base','VARIANT_NAME','MPCC_R'); evalin('base','init_paras');
set_param(mdl,'SimulationCommand','update'); fprintf('[compile] update diagram OK\n');
save_system(mdl); close_system(mdl,0); fprintf('[saved] %s\n', which('PV_MEV.slx'));
