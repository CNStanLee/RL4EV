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
% Only VARIANT_NAME survives the workspace reset below.
clearvars -except VARIANT_NAME
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
Ro=22.22;           % 7.2-kW nominal load (Ohms)
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

%% fft and deep learning model sampling
mm_fund_freq = 50;
mm_points_per_cycle = 80;
mm_sampling_overlap = mm_points_per_cycle - 1;
mm_10cycle_points = mm_points_per_cycle * 10;
mm_10cycle_overlap = mm_10cycle_points - 1;
fs = mm_fund_freq * mm_points_per_cycle;   % 4000 Hz
mm_halfcycle_points = mm_points_per_cycle / 2;     % 40 points
mm_halfcycle_overlap = mm_halfcycle_points - 1;   % sliding half-cycle window

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
fprintf('[init_paras] variant %-11s Fc=%6.0f Hz  d=%d p=%d h=%d src=%d  simu_time=%g s\n', ...
    VARIANT_NAME, Fc, use_d_predict, use_p_predict, use_harmonic, estimation_src, simu_time);
clear cfg_dir cfg_file cfg_tbl cfg_row
