% apply_m14.m: M14 (16384) -- the corrected bus sample enters the MPCC predictor as well as the voltage loop
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd); load_system('PV_MEV');
pc='PV_MEV/EV System/PFC Control'; rt=sfroot; ch=rt.find('-isa','Stateflow.EMChart','Path',[pc '/Mitigation']); sc=ch(1).Script;
sc=strrep(sc,'function [Vdc_fb, Iref_out, Vin_out, iL_out, hold, g_alpha, dbg, Ilim] = mitigation(', 'function [Vdc_fb, Iref_out, Vin_out, iL_out, hold, g_alpha, dbg, Ilim, Vo_ctl] = mitigation(');
old=['Ilim = Ilim0;' newline 'if M(11) && any(g > 0), Ilim = 55; end'];
new=[old newline '% --- M14 (16384): the corrected bus sample also feeds the current predictor (its plant model uses V_o); without it a bus bias' newline ...
     '% makes the inner loop deliver a current that differs from the reference and the outer loop must over-command (E-DC-02b)' newline ...
     'Vo_ctl = Vdc;' newline 'if M(14), Vo_ctl = Vdc_fb; end'];
assert(contains(sc,old)); sc=strrep(sc,old,new); ch(1).Script=sc;
dd=ch(1).find('-isa','Stateflow.Data'); d=dd(strcmp({dd.Name},'Vo_ctl')); d.Props.Array.Size='1'; d.DataType='double';
% D_predict: find the inport fed by the same source as Mitigation in3 (Vdc_int via Rate Transition4)
hm=get_param([pc '/Mitigation'],'Handle'); lm=get_param(hm,'LineHandles'); srcVdc=get_param(lm.Inport(3),'SrcPortHandle');
hd=get_param([pc '/D_predict'],'Handle'); ld=get_param(hd,'LineHandles'); pd=get_param(hd,'PortHandles');
fprintf('D_predict inports:\n'); k=0;
for i=1:numel(ld.Inport), if ld.Inport(i)>0, sp=get_param(ld.Inport(i),'SrcPortHandle'); sb=get_param(sp,'Parent'); fprintf('  in%d <- %s\n', i, strrep(get_param(sb,'Name'),newline,' ')); if strcmp(get_param(sb,'BlockType'),'From') && strcmp(get_param(sb,'GotoTag'),'V_o'), k=i; end, end, end
assert(k>0,'D_predict V_o inport not found'); fprintf('V_o is D_predict inport %d\n', k);
% other destinations of the Vdc_int line (e.g. HIL path)
dsts=get_param(lm.Inport(3),'DstBlockHandle'); for j=1:numel(dsts), fprintf('  Vdc line also feeds: %s\n', strrep(get_param(dsts(j),'Name'),newline,' ')); end
delete_line(ld.Inport(k)); pm=get_param(hm,'PortHandles');
add_line(pc, pm.Outport(9), pd.Inport(k), 'autorouting','on'); fprintf('[wired] Mitigation:9 (Vo_ctl) -> D_predict:%d\n', k);
assignin('base','VARIANT_NAME','MPCC_R'); evalin('base','init_paras'); set_param('PV_MEV','SimulationCommand','update'); fprintf('[compile] OK\n');
save_system('PV_MEV'); close_system('PV_MEV',0); fprintf('[saved]\n');
