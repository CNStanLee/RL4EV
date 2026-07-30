pynq = tcpclient("134.226.86.100", 5000, "Timeout", 10)
pynq.ByteOrder = "little-endian"

write(pynq, single(12.5), "single")

while pynq.NumBytesAvailable < 4
    pause(0.001)
end

result = read(pynq, 1, "single")
disp(result)