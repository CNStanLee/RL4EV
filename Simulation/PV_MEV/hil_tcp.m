function y = hil_tcp(x, n_out, port_in, port_out)
% HIL_TCP  One HIL round trip over TCP (send x as little-endian singles to host:port_in, read n_out singles from
% host:port_out), called extrinsically from the MATLAB Function blocks that build_hil.m puts in PV_MEV
% (docs/HIL_TEST_PLAN.md).  The clients live in a persistent map here, outside the model, so a run restarted from a
% ModelOperatingPoint snapshot is unaffected (the instrumentlib TCP/IP System objects lose their client handle on
% restore).  Host / switches come from the base workspace (init_paras: HIL_HOST, ENABLE_HIL, ENABLE_HIL_DET,
% ENABLE_HIL_EST; the switch for a path is chosen by its input port).  With the switch off nothing is sent and
% zeros are returned (the Simulink Switch blocks then use the SIL path).
%
%   hil_tcp('reset')       close every client (run_injection calls it before and after each run)
%   hil_tcp('stats')       struct of per-port call counts and cumulative round-trip time
persistent C ST
if isempty(C), C = containers.Map('KeyType', 'double', 'ValueType', 'any'); ST = containers.Map('KeyType', 'double', 'ValueType', 'any'); end
if ischar(x) || isstring(x)
    switch char(x)
        case 'reset'
            k = keys(C); for i = 1:numel(k), s = C(k{i}); try, clear s; catch, end, end
            C = containers.Map('KeyType', 'double', 'ValueType', 'any'); ST = containers.Map('KeyType', 'double', 'ValueType', 'any'); y = 0;
        case 'stats'
            y = struct(); k = keys(ST); for i = 1:numel(k), y.(sprintf('p%d', k{i})) = ST(k{i}); end
        otherwise, error('hil_tcp: unknown command %s', char(x));
    end
    return;
end
y = zeros(1, n_out);
switch port_in
    case 5010, on = evalin('base', 'ENABLE_HIL');
    case 5020, on = evalin('base', 'ENABLE_HIL_DET');
    case 5030, on = evalin('base', 'ENABLE_HIL_EST');
    otherwise, on = 1;
end
if ~on, return; end
if ~isKey(C, port_in)
    host = evalin('base', 'HIL_HOST');
    s = struct('tx', tcpclient(host, port_in, 'Timeout', 10, 'ConnectTimeout', 10), 'rx', tcpclient(host, port_out, 'Timeout', 10, 'ConnectTimeout', 10));
    s.tx.ByteOrder = 'little-endian'; s.rx.ByteOrder = 'little-endian';
    C(port_in) = s; ST(port_in) = struct('n', 0, 't', 0, 'tmax', 0);
end
s = C(port_in); t0 = tic;
write(s.tx, single(x(:)'), 'single');
r = read(s.rx, n_out, 'single');
dt = toc(t0); st = ST(port_in); st.n = st.n + 1; st.t = st.t + dt; st.tmax = max(st.tmax, dt); ST(port_in) = st;
if numel(r) ~= n_out, error('hil_tcp: port %d returned %d of %d values', port_out, numel(r), n_out); end
y = double(r(:)');
end
