% apply_res.m: online joint-residual detector as an alternative score source (det_src = 1) in the EMI Detector subsystem
cd('<RL4EV>/Simulation/PV_MEV'); addpath(pwd); load_system('PV_MEV'); d='PV_MEV/EV System/EMI Detector';
% residual_score: six residual features -> z-scores -> per-channel logistic logits, in the ONNX raw layout [5 logits, 10 zeros, 5 amplitudes]
hb=add_block('simulink/User-Defined Functions/MATLAB Function',[d '/residual_score'],'Position',[800 560 900 620]);
rt=sfroot; ch=rt.find('-isa','Stateflow.EMChart','Path',[d '/residual_score']);
ch.Script=sprintf(['function raw = residual_score(feat, par)\n%%#codegen\n' ...
 '%% joint-residual baseline of detector_eval_unified.py (export_residual.py): |x - med| / mad on six residual features,\n' ...
 '%% one logistic regression per channel; the same decision block, thresholds (RES.thr) and corrections follow.\n' ...
 'f = double(feat(:)''); idx = round(par(1:6)); med = par(7:12); mad = par(13:18); W = reshape(par(19:48), 6, 5); b = par(49:53);\n' ...
 'z = abs(f(idx) - med) ./ mad;\n' ...
 'lg = z * W + b;\n' ...
 'raw = single([lg, zeros(1, 10), zeros(1, 5)]);\n']);
dd=ch.find('-isa','Stateflow.Data');
for nm={'feat','par','raw'}, x=dd(strcmp({dd.Name},nm{1})); x.Props.Array.Size=struct('feat','[1 48]','par','[1 53]','raw','[1 20]').(nm{1}); x.DataType=struct('feat','single','par','double','raw','single').(nm{1}); end
hp=add_block('simulink/Sources/Constant',[d '/res_par'],'Value','res_par','Position',[700 600 760 620]);
hs=add_block('simulink/Sources/Constant',[d '/det_src'],'Value','det_src','Position',[800 660 860 680]);
hw=add_block('simulink/Signal Routing/Switch',[d '/det_switch'],'Criteria','u2 > Threshold','Threshold','0.5','Position',[900 200 930 260]);
gp=@(h,k) subsref(get_param(h,'PortHandles'),substruct('.','Outport','()',{k})); ip=@(h,k) subsref(get_param(h,'PortHandles'),substruct('.','Inport','()',{k}));
ho=get_param([d '/ONNX Runner'],'Handle'); he=get_param([d '/emi_decide'],'Handle'); hts=get_param([d '/to_single'],'Handle');
lh=get_param(he,'LineHandles'); delete_line(lh.Inport(1));
add_line(d,gp(hts,1),ip(hb,1),'autorouting','on'); add_line(d,gp(hp,1),ip(hb,2),'autorouting','on');
add_line(d,gp(hb,1),ip(hw,1),'autorouting','on'); add_line(d,gp(hs,1),ip(hw,2),'autorouting','on'); add_line(d,gp(ho,1),ip(hw,3),'autorouting','on');
add_line(d,gp(hw,1),ip(he,1),'autorouting','on'); fprintf('[wired] residual_score / ONNX -> det_switch -> emi_decide\n');
rj=jsondecode(fileread('<RL4EV>/EMI_DET_FPGA/artifacts/residual.json')); assignin('base','RES',struct('thr',rj.thr(:)','par',rj.par(:)'));
assignin('base','VARIANT_NAME','MPCC_R6_RES'); evalin('base','init_paras'); set_param('PV_MEV','SimulationCommand','update'); fprintf('[compile MPCC_R6_RES] OK\n');
assignin('base','VARIANT_NAME','MPCC_R'); evalin('base','init_paras'); set_param('PV_MEV','SimulationCommand','update'); fprintf('[compile MPCC_R] OK\n');
save_system('PV_MEV'); close_system('PV_MEV',0); fprintf('[saved]\n');
