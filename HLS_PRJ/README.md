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

## 构建与复核（Vitis HLS 2022.2 Tcl 流程）

论文中的 IP 用 Vitis HLS 2022.2 的 Tcl 流程综合；`build_hls.tcl` / `build_all.sh` 是该流程的入库版本
（与原始构建相同的设置：`-std=c++14`、xczu7ev-ffvc1156-2-e、10 ns 时钟、27 % 不确定度、`export_design -format ip_catalog`）。

```bash
cd HLS_PRJ
./build_all.sh                    # 五个组件：C 仿真 + 综合 + 导出 IP（约 3 分钟）
HLS_STEPS=csim ./build_all.sh     # 只做 C 仿真
./build_all.sh mpcc_r emi_feat    # 指定组件
```

工作目录是 `<组件>/<组件>/`（git 忽略），打包好的 IP 在 `<组件>/<组件>/hls/impl/ip`，
因此 `HLS_PRJ` 本身可以直接作为 Vivado 的 IP 仓库路径。Vitis HLS 不在 `/tools/Xilinx` 时设置 `XILINX_HLS_SETTINGS`。

2026-10-01 在只含已入库文件的干净导出上复核：

| 组件 | C 仿真 | 综合估计（LUT / FF / DSP） |
|---|---|---|
| `mpcc` | 最大误差 0，PASSED | 14,638 / 6,080 / 51 |
| `mpcc_r` | 1600 拍与 `mpcc_hls` 逐位相同；Vac 重构误差 0.00 V | 16,484 / 7,473 / 51 |
| `emi_feat` | 100 周期，容差外 0 个 | 26,401 / 19,002 / 169 |
| `emi_detector` | 1089 周期，max \|Δlogit\| 4.8e-6，标志字 0 不一致 | 27,372 / 14,762 / 143 |
| `harmonic_estimator` | 1287 窗，max \|Δenc\| 0 | 69,306 / 26,448 / 459 |

实现后的资源见 `Vivado_PRJ/README.md`。

**`i_ref` 符号**：2026-09-05 的 HIL 发现 `mpcc_hls` / `mpcc_r_hls` 把电流参考取了绝对值，电压环给出负参考时
（+100 V 母线偏置）会把母线推到过压。两个源文件已改为保留 `i_ref` 的符号（与 PV_MEV 的 `D_predict` 一致），
`tb_mpcc.cpp` 的参考模型同步修改。论文中的硬件资源与 HIL 结果对应修正后的版本。
