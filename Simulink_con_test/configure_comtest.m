function configure_comtest(dataType, sampleTime)
%CONFIGURE_COMTEST Configure the scalar ComTest TCP protocol.
% Examples:
%   configure_comtest                    % single, Ts = 0.01
%   configure_comtest("int8", 0.001)     % int8, Ts = 0.001
arguments
    dataType (1, 1) string {mustBeMember(dataType, ...
        ["int8", "uint8", "int16", "uint16", "int32", "uint32", ...
         "single", "double"])} = "single"
    sampleTime (1, 1) double {mustBePositive} = 0.01
end

model = "ComTest";
load_system(model);

sendBlock = model + "/TCP//IP Send";
receiveBlock = model + "/TCP//IP Receive";

set_param(model + "/Data Type Conversion", "OutDataTypeStr", dataType);
set_param(receiveBlock, ...
    "DataType", dataType, ...
    "DataSize", "[1, 1]", ...
    "ByteOrder", "little-endian", ...
    "SampleTime", string(sampleTime));

% Give both communication blocks the same discrete rate. Explicit priority
% makes Send execute before blocking Receive at every sample hit.
set_param(model + "/Sine Wave", "SampleTime", string(sampleTime));
set_param(sendBlock, "Priority", "-10");
set_param(sendBlock, "TransferDelay", "off");
set_param(receiveBlock, "Priority", "10");

% Plot the original sine and returned signal together on the existing Scope.
scopeBlock = model + "/Scope";
set_param(scopeBlock, "NumInputPorts", "2");
scopePortHandles = get_param(scopeBlock, "PortHandles");
scopeInput2 = scopePortHandles.Inport(2);
if get_param(scopeInput2, "Line") == -1
    add_line(model, "Sine Wave/1", "Scope/2", "autorouting", "on");
end

save_system(model);
close_system(model);
fprintf("ComTest configured: %s, batch=1, Ts=%g s.\n", ...
    dataType, sampleTime);
end
