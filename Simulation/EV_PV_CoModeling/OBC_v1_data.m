%% Parameter file: OBC_4_data.m

%% Model Parameters
Ts_Power= 50e-9;        % SPS Model sample time (s)
Co=150e-6;              % Output filter (F)
Ron_FET=50e-3;          % FET resistance (ohms)
Ron_Diode=50e-3;        % FET resistance (ohms)
Vf=0.6;                 % Diode forward voltage (V)
%
%% PFC Data
Vnom_ac= 240;           % Nominal Ac voltage (V)
Fnom= 60;               % System frequency (Hz)
L_PFC= 600e-6;          % PFC Inductance (H)
RL_PFC= 20e-3;          % Inductance resistance (Ohm)
C_PFC= 2600e-6;         % Capacitance (F)

%% PFC Control System Parameters
Ts_Control= 10e-6;      % Control system time (s)
Fsw= 100e3;             % PWM Switching frequency (Hz)
DT_PFC=400e-9;
%
% Current Regulator (PR): 
Kp_I= 0.06;             % Proportional gain 
Kr_I= 2.5;              % Resonant gain
Zeta_I=0.2;             % Damping coefficient
Fr_I=Fnom*2;            % Resonant frequency (Hz)
%
% Voltage Regulator (PI): 
Kp_V= 0.25;             % Proportional gain 
Ki_V= 80;               % Integral gain
Limit_V= 100;           % Output limit
%
%% LLC Data
Vdc_in=400;             % DC input voltage (V)
Vo_nom=400;             % DC nominal output voltage (V)
Po_nom=7.2e3;           % Nominal output power (W)
Lr=25e-6;               % Transformer leakage inductance (Resonant inductance in Henry)
Lm=150e-6;              % Magnetization inductance (H)
Cr=75e-9;               % Resonant capacitor (F)
Np=10; Ns=12; N=Np/Ns;  % Transformer ratio
%
%% LLC Control System Parameters
DT_LLC=400e-9;
Ts_Control=10e-6;
% Voltage Regulator (PI): 
Kp_LLC= 100/4;          % Proportional gain 
Ki_LLC= 150e3;          % Integral gain
fs_LCC_min= 120e3;      % Minimum switching frequency (Hz)
fs_LCC_max= 300e3;      % Maximum switching frequency (Hz)
Vref_LCC_min= 275;      % Minimum voltage setpoint (V)
Vref_LCC_max= 450;      % Maximum voltage setpoint (V)
%
%%
% Resonant tank data
Ro=Vo_nom^2/Po_nom      % LLC output load (Ohm)
Rac=(8/pi^2)*N^2*Ro     % Equivalent pprimary AC resistance (Ohm)
Q=sqrt(Lr/Cr)/Rac       % Quality factor
fr=1/(2*pi*sqrt(Lr*Cr)) % Resonant frequency (Hz)
m=(Lr+Lm)/Lr            % Ratio of total primary reactance to resonant inductance (Lr) 
%%



