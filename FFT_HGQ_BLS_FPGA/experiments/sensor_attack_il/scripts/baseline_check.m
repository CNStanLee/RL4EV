function baseline_check()
outdir = '/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA/experiments/sensor_attack_il/results';
res = sim_il_case('baseline_check',[0 1 0.08 999 0 50 0 0],0.15,outdir);
names = {'iL_true','iL_meas','iL_delta','Iref','predict_D','Vdc','Iac','Vac','iL_phys','THD_sys','Vdc_ripple_sys'};
fprintf('\n%-16s %8s %10s %10s %10s %10s\n','signal','N','min','max','mean','last');
for k=1:numel(names)
    nm=names{k}; y=res.(nm).y;
    if isempty(y), fprintf('%-16s   MISSING\n',nm); continue; end
    fprintf('%-16s %8d %10.4g %10.4g %10.4g %10.4g\n', nm, numel(y), min(y), max(y), mean(y), y(end));
end
% steady-state THD/ripple on [0.10 0.15]
tt=res.THD_sys.t; yy=res.THD_sys.y; m=tt>=0.10;
fprintf('\nSteady THD_sys mean(0.10-0.15) = %.4g\n', mean(yy(m)));
tt=res.Vdc_ripple_sys.t; yy=res.Vdc_ripple_sys.y; m=tt>=0.10;
fprintf('Steady Vdc_ripple_sys mean(0.10-0.15) = %.4g\n', mean(yy(m)));
fprintf('BASELINE_CHECK_DONE\n');
end
