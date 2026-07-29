clc;
clear;
close all;
%%
% target = "/home/changhong/anaconda3/envs/matlab_onnx_py310/bin/python";
% pe = pyenv;
% 
% pyenv("Version", target);
% 
% pyenv
% string(py.sys.executable)

%% Model Parameters
Ts_Power= 50e-9;    % SPS Model sample time (s)
Ro=22.22;           % 7.2-kW nominal load (Ohms)
Ron_FET=50e-3;      % FET resistance (ohms)
Ron_Diode=50e-3;    % FET resistance (ohms)
Vf=0.6;             % Diode forward voltage (V)
      

%% PFC Data
Vnom_ac= 240;       % Nominal Ac voltage (V)
Fnom= 50;           % System frequency (Hz)
L_PFC= 600e-6;      % PFC Inductance (H)
RL_PFC= 20e-3;      % Inductance resistance (Ohm)
C_PFC= 2600e-6;     % Capacitance (F)

%% PFC Control System Parameters
Fc = 20e3;
% Fc = 100e3;
Ts_Control= 1/Fc;  % Control system time (s)
Fsw= 100e3;         % PWM Switching frequency (Hz)
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
%
%% fft and deep learning model sampling

mm_fund_freq = 50;
mm_points_per_cycle = 80;
mm_sampling_overlap = mm_points_per_cycle - 1;
mm_10cycle_points = mm_points_per_cycle * 10;
mm_10cycle_overlap = mm_10cycle_points - 1;
fs = mm_fund_freq * mm_points_per_cycle;   % 4000 Hz
mm_halfcycle_points = mm_points_per_cycle / 2;     % 40 points
mm_halfcycle_overlap = mm_halfcycle_points - 1;   % sliding half-cycle window


%% control choose
% use_d_predict = 1;
% use_p_predict = 0;
% use_harmonic = 1;
% estimation_src = 1; % 1: fft(1) 2:fft(10) 3:BLS(1) 4:BLS(0.5) 5:RLS

%% EXAMPLE cases
%% CASE 1: CRPR control
% Fc = 20 kHz
% THD 70.77%
% Ripple 5.24%

% Fc = 100 kHz
% THD 11.77%
% Ripple 5.95%

% use_d_predict = 0;
% use_p_predict = 0;
% use_harmonic = 0;
% estimation_src = 1;

%% CASE 2: MPCC P Predict
% Fc = 20 kHz
% THD 48.11%
% Ripple 6.00%

% Fc = 100 kHz
% THD 11.47%
% Ripple 5.72%


% use_d_predict = 0;
% use_p_predict = 1;
% use_harmonic = 0;
% estimation_src = 1;

%% CASE 3: MPCC D Predict
% THD 6.1%
% Ripple 5.75%

% use_d_predict = 1;
% use_p_predict = 0;
% use_harmonic = 0;
% estimation_src = 1;

%% CASE 4: MPCC D Predict with harmonic info
% THD 3.37% (fft1) 3.38 (fft10) 3.38 (rls) 2.85 (model 1) 
% Ripple 5.6% (fft1) 5.61 (fft10) 5.56 (rls) 5.61 (model 1) 

use_d_predict = 1;
use_p_predict = 0;
use_harmonic = 1;
estimation_src = 3;