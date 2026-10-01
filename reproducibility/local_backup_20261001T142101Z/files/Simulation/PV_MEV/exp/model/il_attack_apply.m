function y = il_attack_apply(u)
%IL_ATTACK_APPLY  ReThink-style current-sensor (IL) spoofing applied to the value
% the MPCC/estimators actually see:  iL_meas = iL_true + delta(t).
% Input  u = [iL_true; t; p(1..8)]
%   p = [enable, mode, t0, t1, A, f, phase, offset]
% Output y = [iL_meas; delta]
%
% Attack modes are grounded in ReThink (Yang et al., NDSS'25):
%   1 constant bias        - Hall-sensor DC offset / "transient effect" (Sec. IV-B1)
%   2 sine oscillation @ f - DoS strategy  Ia(t)=Aa*sin(2*pi*f*t)      (Eq. 11)
%   3 AM triangular        - controllable manipulation envelope         (Fig. 11)
%   4 AM sine (raised-cos) - precise "desired-curve" manipulation       (Fig. 11)
%   5 scaling / gain error - op-amp amplification effect                (Sec. III-A)
iL_true = u(1);  t = u(2);  p = u(3:10);
en = p(1); mode = p(2); t0 = p(3); t1 = p(4);
A = p(5); f = p(6); phi = p(7); off = p(8);
delta = 0;
if en > 0.5 && t >= t0 && t <= t1
    switch round(mode)
        case 1
            delta = A;
        case 2
            delta = A * sin(2*pi*f*(t - t0) + phi);
        case 3
            p01 = mod(f*(t - t0), 1);
            tri = 1 - abs(2*p01 - 1);          % 0 -> 1 -> 0 triangle
            delta = A * tri + off;
        case 4
            delta = A * 0.5 * (1 - cos(2*pi*f*(t - t0))) + off;
        case 5
            delta = (A - 1) * iL_true;
        otherwise
            delta = 0;
    end
end
y = [iL_true + delta; delta];
end
