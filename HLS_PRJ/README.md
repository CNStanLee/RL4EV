# HLS_PRJ — Vitis HLS 组件

| 组件 | 顶层函数 | 内容 | 状态（Vitis HLS 2022.2，xczu7ev，10 ns） |
|---|---|---|---|
| `mpcc` | `mpcc_hls` | 原 MPCC 占空比预测 IP（14 float 入、1 float 出） | 已上板（ZCU104 HIL） |
| `mpcc_r` | `mpcc_r_hls` | 韧性 MPCC：`mpcc_hls` 核 + 检测条件化的内环输入修正（M2 Vac 前馈重构、M3 Iac 直流补偿、M4 谐波相量保持、M7 撤除斜坡），标志为 0 时与 `mpcc_hls` 逐位相同 | C 仿真通过；LUT 16.6k、DSP 51、延迟 0.7 到 2.6 µs |
| `emi_feat` | `emi_feat_hls` | 检测器的 48 个逐周期特征（`features.cycle_features_v3`），200 × 12 缓冲，单次流水遍历 | C 仿真与 Python 特征相对误差 ≤ 1e-3 |
| `emi_detector` | `emi_detector_axi` | HGQ2 检测器链（hls4ml，bit_exact）+ 标准化 / 阈值 / 持续 / 滞回包装 | 见 `EMI_DET_FPGA/scripts/hls4ml_sweep.py` 的 ReuseFactor 扫描 |
| `harmonic_estimator` | `harmonic_estimator_axi` | HGQ2 Residual-BLS 谐波估计器（hls4ml，bit_exact）+ CycleNorm / 解码包装 | 同上 |

本机（Linux）用 Vitis HLS 2022.2 的 Tcl 流程综合（包装层需 `-std=c++14`）；`hls_config.cfg` / `vitis-comp.json` 供 2023.2+ 统一流程使用。
块设计与 bitstream：`Vivado_PRJ/MPCC_R/build_bd.tcl`；PS 驱动：`PS_notebook/libs/mpcc_r_overlay.py`。
