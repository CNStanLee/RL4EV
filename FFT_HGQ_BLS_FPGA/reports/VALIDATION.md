# 验证状态

## 已完成

- HGQ2 Keras → ONNX：16 个测试样本最大绝对误差为 `0`。
- HGQ2 Keras → Alkaid ALIR：16 个测试样本逐值完全相等。
- ONNX 图通过 ONNX checker；Simulink 包装接口固定为 `[batch,80] -> [batch,8]`。
- `PV_MEV_FFT_HGQ_BLS.slx` 已在 MATLAB R2025a 完成模型更新和 0.15 s 闭环运行。
- 0.15 s 闭环捕获共 601 个估计周期，watchdog 接受率为 `100%`。
- 原始仿真数据的 run-isolated ID/OOD 离线结果见 `estimator_comparison.csv`。

## 尚未完成

- 新 HGQ2 版本的 0.8 s 多工况稳态 THD 扫描；包中没有混用旧 Brevitas-BLS 的稳态结果。
- 针对目标 FPGA 的综合、资源、Fmax、功耗与 250 us deadline 签核。
- bit-true C/RTL、PIL/FPGA-in-the-loop、PLL unlock/ADC 饱和/丢样等故障注入。

因此当前包可用于 Simulink 联调和 FPGA 工程生成起点，但不能直接视为量产闭环签核版本。
