% init_paras.m  --  PV_MEV model InitFcn
%
% Controller variant selection is table-driven: put the variant name in the
% base workspace before running, e.g.
%     VARIANT_NAME = "MPCC_D_F1";  sim("PV_MEV")
% and the row with that name in config.csv (same folder) supplies
%     Fc, use_d_predict, use_p_predict, use_harmonic, estimation_src, simu_time
% Ts_Control = 1/Fc is derived here and nowhere else.  run_benchmark.m runs
% every row of config.csv and writes results/benchmark_results.csv.
%
% estimation_src (harmonic amplitude/phase source, Multiport Switch in PFC Control):
%   1 = FFT 1 cycle   2 = FFT 10 cycles   3 = ONNX model 1 cycle
%   4 = ONNX model 0.5 cycle   5 = RLS
%
% Sensor-chain injection test bench (docs/EMI_INJECTION_TEST_PLAN.md): the
% struct INJ (fields channel, shape, amp, k, f, phase, period, duty, t_on,
% dwell, K_hall) selects the disturbance; run_injection.m fills it from
% tests.csv.  Without INJ the model runs undisturbed.  xInitial holds the
% ModelOperatingPoint snapshot when a run starts from 0.6 s.
%
% CHG_OP (fields Voc, Icc) overrides the charger operating point (CV-segment
% snapshot); EVT (fields chg_t, chg_I, vref_t, vref_dV) adds benign transients
% for the detector dataset.
%
% Only VARIANT_NAME, INJ, CHG_OP, EVT and xInitial survive the workspace reset below.
clearvars -except VARIANT_NAME INJ CHG_OP EVT DET xInitial
close all;

%% System control
ENABLE_HIL = 0;

%% General simulation paras
Fnom= 50;               % System frequency (Hz)
Vnom_ac= 240;           % Nominal Ac voltage (V)

%% python env (only needed for estimation_src 3/4, ONNX Model Predict blocks)
% target = "/home/changhong/anaconda3/envs/matlab_onnx_py310/bin/python";
% pyenv("Version", target);

%% Model Parameters
Ts_Power= 50e-9;    % SPS Model sample time (s)
Ro=22.22;           % legacy 7.2-kW resistive load (Ohms); replaced by Charger Stage
R_bleed=100e3;      % DC-bus bleeder in parallel with the charger (Ohms)
R_pre=Ro*2;         % start-up preload (3.6 kW), switched off at t_pre_off
t_pre_off=0.30;     % preload off while the charger ramp is at 10 A (bus never unloaded)
Ron_FET=50e-3;      % FET resistance (ohms)
Ron_Diode=50e-3;    % FET resistance (ohms)
Vf=0.6;             % Diode forward voltage (V)

%% PFC Data
L_PFC= 600e-6;      % PFC Inductance (H)
RL_PFC= 20e-3;      % Inductance resistance (Ohm)
C_PFC= 2600e-6;     % Capacitance (F)

%% PFC Control System Parameters
Fsw= 100e3;         % PWM Switching frequency (Hz) (CRPR / MPCC_D paths)
DT_PFC=400e-9;

% Current Regulator (PR):
Kp_I= 0.06;         % Proportional gain
Kr_I= 2.5;          % Resonant gain
Zeta_I=0.2;         % Damping coefficient
Fr_I=Fnom*2;        % Resonant frequency (Hz)

% Voltage Regulator (PI):
Kp_V= 0.25;        % Proportional gain
Ki_V= 80;          % Integral gain
Limit_V= 100;      % Output limit

%% Battery charger stage (plan section 3.5; assumed values)
Ts_chg   = 10e-6;   % charger control / averaged-model sample time (s)
L_chg    = 1e-3;    % buck inductor (H)
Voc      = 335;     % battery open-circuit voltage (V), CC-segment snapshot
Rint     = 0.5;     % battery internal resistance (Ohm)
Icc      = 20;      % constant-current setpoint (A)
Vcv      = 350;     % constant-voltage setpoint (V)
V_hys    = 5;       % CV -> CC when Vbat_meas <= Vcv - V_hys ...
T_hys    = 20e-3;   % ... for T_hys seconds (test-only hysteresis)
t_chg_on = 0.20;    % charger enable time (s); 20 A reached at 0.40 s
k_chg    = 100;     % current reference ramp (A/s)
Kp_v_chg = 1.5;  Ki_v_chg = 1500;   % CV loop (A/V, A/(V s))
Kp_i_chg = 0.016; Ki_i_chg = 10;    % CC loop (1/A, 1/(A s)), plus duty feed-forward
D_max_chg = 0.98;
I_SIGN   = 1;       % Controlled Current Source polarity: +1 = load (checked: -1 drove Vdc to 1430 V, Pdc < 0)
if exist('CHG_OP','var') && isstruct(CHG_OP)
    if isfield(CHG_OP,'Voc') && ~isempty(CHG_OP.Voc), Voc = CHG_OP.Voc; end   % 345 V -> CV segment
    if isfield(CHG_OP,'Icc') && ~isempty(CHG_OP.Icc), Icc = CHG_OP.Icc; end
end
% benign transients (detector dataset negatives); t <= 0 disables
chg_ev  = [0 Icc];   % [t_step Icc_new]  charging-current reference step
vref_ev = [0 0];     % [t_step dV]       Vdc reference step
if exist('EVT','var') && isstruct(EVT)
    if isfield(EVT,'chg_t')  && EVT.chg_t  > 0, chg_ev  = [EVT.chg_t  EVT.chg_I];  end
    if isfield(EVT,'vref_t') && EVT.vref_t > 0, vref_ev = [EVT.vref_t EVT.vref_dV]; end
end
chg_par      = [L_chg Voc Rint Ts_chg I_SIGN t_chg_on];
chg_ctrl_par = [Icc Vcv V_hys T_hys Kp_v_chg Ki_v_chg Kp_i_chg Ki_i_chg Ts_chg D_max_chg t_chg_on k_chg];

%% Protection monitor thresholds (plan section 3.3), real quantities only
prot_thr = [300 450 65 355 25 2e-3 0.55];   % [UV_V OV_V OC_A BOV_V BOC_A hold_s t_arm_s]

%% Sensor-chain injection (plan section 3.2); INJ from run_injection.m
% channel: 1 Vdc 2 Vac 3 Iac 4 Vbat 5 Ibat (0 = off); three slots: two
% simultaneous injections + one measurement-noise slot (shape 7).
% shape:   1 step 2 ramp 3 sine 4 tri 5 pulse 6 hall 7 noise
if ~exist('INJ','var') || isempty(INJ), INJ = struct(); end
def = struct('channel',[0 0 0],'shape',[1 1 1],'amp',[0 0 0],'k',[0 0 0],'f',[50 50 50],'phase',[0 0 0], ...
             'period',0.1,'duty',0.5,'t_on',0.70,'dwell',0.30,'K_hall',20);
fn = fieldnames(def);
for i = 1:numel(fn)
    if ~isfield(INJ, fn{i}) || isempty(INJ.(fn{i})), INJ.(fn{i}) = def.(fn{i}); end
end
for f2 = {'channel','shape','amp','k','f','phase'}      % pad to 1x3
    v = double(INJ.(f2{1})); v = v(:)'; if numel(v) < 3, v = [v, def.(f2{1})(numel(v)+1:3)]; end
    INJ.(f2{1}) = v(1:3);
end
inj_channel = INJ.channel; inj_shape = INJ.shape; inj_amp = INJ.amp; inj_k = INJ.k;
inj_f = INJ.f; inj_phase = INJ.phase; inj_period = INJ.period; inj_duty = INJ.duty;
inj_t_on = INJ.t_on; inj_dwell = INJ.dwell; K_hall = INJ.K_hall;
clear def fn i f2 v

%% fft and deep learning model sampling
mm_fund_freq = 50;
mm_points_per_cycle = 80;
mm_sampling_overlap = mm_points_per_cycle - 1;
mm_10cycle_points = mm_points_per_cycle * 10;
mm_10cycle_overlap = mm_10cycle_points - 1;
fs = mm_fund_freq * mm_points_per_cycle;   % 4000 Hz
mm_halfcycle_points = mm_points_per_cycle / 2;     % 40 points
mm_halfcycle_overlap = mm_halfcycle_points - 1;   % sliding half-cycle window

%% Python for the ONNX models (OnnxRunner -> onnx_bridge.py -> onnxruntime); conda env hgq2
try
    pe = pyenv;
    if pe.Status == "NotLoaded" && ~contains(pe.Executable, 'hgq2')
        pyenv('Version', 'D:\Anaconda\envs\hgq2\python.exe');
    end
catch
end

%% EMI-injection detector (build_detector.m); model from EMI_DET_FPGA/runs/<run>/model.onnx
det_onnx_file      = 'D:/Prj/RL4EV/EMI_DET_FPGA/runs/det_v2_q/model.onnx';
det_thr            = [0.5 0.5 0.5 0.5 0.5];   % per-channel sigmoid thresholds (run_injection passes detector.json values in DET.thr)
if exist('DET', 'var') && isstruct(DET) && isfield(DET, 'thr') && numel(DET.thr) == 5, det_thr = double(DET.thr(:)'); end
det_ema_alpha      = 0.1;                     % baseline EMA (features.EMA_ALPHA)
det_persist        = 2;                       % consecutive cycles before a channel flag is raised
det_variant_onehot = [0 0 0 0 0 0];           % set below from VARIANT_NAME (CRPR MPCC_P MPCC_D MPCC_D_F1 MPCC_D_F10 MPCC_D_R)

%% HGQ2 harmonic estimator (estimation_src 3 raw, 6 = FFT1 + HGQ2 fusion), see build_estimator.m
% Per-order fusion weights from FFT_HGQ_BLS_FPGA/config/deployment.json (fft_fusion_alpha_mpcc)
hgq_fusion_alpha = [0.6704476522845647 0.7221651725151749 0.6446423751787858 0.41926421682656173];
hgq_min_ratio    = single(0);

%% Controller variant (from config.csv)
if ~exist('VARIANT_NAME','var') || isempty(VARIANT_NAME)
    VARIANT_NAME = "MPCC_D_F1";          % default case when nothing is selected
end
VARIANT_NAME = string(VARIANT_NAME);

cfg_dir = fileparts(mfilename('fullpath'));
if isempty(cfg_dir), cfg_dir = fileparts(which('init_paras')); end
cfg_file = fullfile(cfg_dir, 'config.csv');
cfg_tbl  = readtable(cfg_file, 'TextType', 'string');
cfg_row  = cfg_tbl(strcmp(cfg_tbl.VARIANT_NAME, VARIANT_NAME), :);
if height(cfg_row) ~= 1
    error('init_paras:variant', ...
        'VARIANT_NAME "%s" not found (or not unique) in %s. Available: %s', ...
        VARIANT_NAME, cfg_file, strjoin(cfg_tbl.VARIANT_NAME', ', '));
end

Fc             = cfg_row.Fc;             % control-loop frequency (Hz)
Ts_Control     = 1/Fc;                   % control sample time (s)
use_d_predict  = cfg_row.use_d_predict;  % 1: MPCC duty prediction -> PWM
use_p_predict  = cfg_row.use_p_predict;  % 1: MPCC direct gating (bypasses PWM)
use_harmonic   = cfg_row.use_harmonic;   % 1: subtract estimated 3/5/7th harmonics from Iref
estimation_src = cfg_row.estimation_src; % see table above
simu_time      = cfg_row.simu_time;      % model StopTime (s)

if use_d_predict && use_p_predict
    error('init_paras:variant', 'use_d_predict and use_p_predict cannot both be 1 (%s)', VARIANT_NAME);
end
det_vlist = ["CRPR" "MPCC_P" "MPCC_D" "MPCC_D_F1" "MPCC_D_F10" "MPCC_D_R"];
det_variant_onehot = double(det_vlist == VARIANT_NAME);      % all-zero for variants unseen by the detector
fprintf('[init_paras] variant %-11s Fc=%6.0f Hz  d=%d p=%d h=%d src=%d  simu_time=%g s\n', ...
    VARIANT_NAME, Fc, use_d_predict, use_p_predict, use_harmonic, estimation_src, simu_time);
clear cfg_dir cfg_file cfg_tbl cfg_row
