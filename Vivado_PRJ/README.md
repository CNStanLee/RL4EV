# Vivado_PRJ — ZCU104 比特流

工具：Vivado 2022.2，器件 xczu7ev-ffvc1156-2-e，PL 时钟 100 MHz。两个设计都由 `build_bd.tcl` 从零重建，
工程目录、比特流与 `.xsa` 不入库；先按 [`HLS_PRJ/README.md`](../HLS_PRJ/README.md) 导出 IP。

```bash
source /tools/Xilinx/Vivado/2022.2/settings64.sh
cd HLS_PRJ && ./build_all.sh && cd ..
# 四 IP 设计（论文中的硬件）：约 35 分钟
cd Vivado_PRJ/MPCC_R && vivado -mode batch -source build_bd.tcl -tclargs $PWD/../../HLS_PRJ 1
# 单 IP 设计（最初的 mpcc_hls HIL 通路）：约 6 分钟
cd ../MPCC && vivado -mode batch -source build_bd.tcl -tclargs $PWD/../../HLS_PRJ 1
```

产物在各自的 `out/`：`mpcc_r.bit` / `mpcc_r.hwh`（或 `mpcc_hil.bit` / `mpcc_hil.hwh`）与 `system_wrapper.xsa`，
以及 `timing_impl.rpt`、`util_impl.rpt`。上板时把 `.bit` 与 `.hwh` 一起复制到 `PS_notebook/hardware/`。

## 复核结果（2026-10-01，只含已入库文件的干净导出）

| 设计 | LUT | FF | RAMB36/18 | DSP | WNS |
|---|---:|---:|---:|---:|---:|
| `MPCC_R` 全设计 | 80,128 | 71,270 | 60/20 | 803 | 2.958 ns |
| 　`mpcc_r_hls` | 10,701 | 7,266 | 1/1 | 54 | |
| 　`emi_feat_hls` | 30,937 | 23,643 | 7/7 | 147 | |
| 　`emi_detector_axi` | 13,318 | 13,178 | 16/5 | 143 | |
| 　`harmonic_estimator_axi` | 23,968 | 25,874 | 36/7 | 459 | |
| `MPCC` 全设计 | 10,845 | 7,653 | 1/0 | 54 | 3.697 ns |

`MPCC_R` 的每一行都与论文资源表逐项相同。用 `i_ref` 修正前的源码（提交 `e2b41c3`）重建，
同样逐项复现当时入库的报告（全设计 80,104 LUT / 71,302 FF）。时序全部满足；WNS 随布局运行略有变化。

## 说明

- `MPCC/MPCC.xpr` 与 `system.bd` 是 Vivado 2025.1 保存的原工程，2022.2 打不开；`MPCC/build_bd.tcl`
  是与其等价、与版本无关的重建脚本（PS 的两个 FPD 主口经 SmartConnect 接 `axi_gpio` 0xA000_0000 和 `mpcc_hls` 0xA001_0000）。
- `MPCC_R` 地址映射：`axi_gpio` 0xA000_0000、`mpcc_r_hls` 0xA001_0000、`emi_feat_hls` 0xA002_0000、
  `emi_detector_axi` 0xA003_0000、`harmonic_estimator_axi` 0xA004_0000、`axi_timer` 0xA005_0000。
- Google Drive 第二批分发包里的 `mpcc_r.bit` 生成于 2026-09-05 03:38，早于 `i_ref` 修正；复现论文硬件结果请重建。
