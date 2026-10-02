# RL4EV

光伏—电动车充电系统的 PFC 控制、EMI 传感链注入研究与 FPGA 部署。

| 目录 | 内容 |
|---|---|
| [`Simulation/PV_MEV/`](Simulation/PV_MEV/) | 主 Simulink 模型（PV + 三相 PFC + 充电级）、8 种控制策略、注入试验台与运行脚本；文档见 [`docs/EMI_INJECTION_TEST_PLAN.md`](Simulation/PV_MEV/docs/EMI_INJECTION_TEST_PLAN.md)、[`docs/EMI_DETECTION_PHASES_2-4_PLAN.md`](Simulation/PV_MEV/docs/EMI_DETECTION_PHASES_2-4_PLAN.md) 与 [`docs/RESILIENT_MPCC_AND_OFFLOAD_PLAN.md`](Simulation/PV_MEV/docs/RESILIENT_MPCC_AND_OFFLOAD_PLAN.md)、[`docs/HIL_TEST_PLAN.md`](Simulation/PV_MEV/docs/HIL_TEST_PLAN.md)（HIL 联调计划） |
| [`EMI_DET_FPGA/`](EMI_DET_FPGA/README.md) | EMI 注入检测器：逐周期特征、HGQ2 量化模型、训练与评估脚本、SIL 报告 |
| [`FFT_HGQ_BLS_FPGA/`](FFT_HGQ_BLS_FPGA/README.md) | HGQ2 Residual-BLS 谐波估计器：模型、训练数据、ONNX 与接口约定 |
| [`HLS_PRJ/`](HLS_PRJ/) | Vitis HLS 组件：`mpcc`（预测控制）、`emi_detector`、`harmonic_estimator` |
| [`Vivado_PRJ/`](Vivado_PRJ/)、[`PS_notebook/`](PS_notebook/) | ZCU104 工程与 PYNQ 上板运行环境 |

FPGA 复现：`HLS_PRJ/build_all.sh`（Vitis HLS 2022.2，C 仿真 + 综合 + 导出 IP）→ `Vivado_PRJ/*/build_bd.tcl`（Vivado 2022.2，比特流）→
[`PS_notebook/README.md`](PS_notebook/README.md)（上板自检、HIL 服务、实时性重放）。步骤与复核结果见
[`HLS_PRJ/README.md`](HLS_PRJ/README.md) 和 [`Vivado_PRJ/README.md`](Vivado_PRJ/README.md)；重建的实现资源与论文资源表逐项相同。
2026-09-05 之后未入库工作的恢复情况见 [`paper/recovery_20261001/README.md`](paper/recovery_20261001/README.md)。

2026-10-01 / 02 用重建的比特流在 ZCU104 上补做的实验（最终策略 `MPCC_R6`）：

| 实验 | 结果 | 位置 |
|---|---|---|
| 全链路 HIL：13 个攻击、250 / 500 V/s 斜坡、11 个基准攻击的三个延后起始相位，共 48 例，各配一次 SIL | 闭锁、标志、检测时刻 48 对全部相同；基准 11 例联合成功 10 / 11（各起始相位相同） | [`Simulation/PV_MEV/results/emi/hil_v6/`](Simulation/PV_MEV/results/emi/hil_v6/)（`equivalence.csv`、`detector_summary.csv`） |
| 实时调度下的三任务并发定时重放 | 五次 20 s，2 000 005 次控制释放无迟到 | [`PS_notebook/logs_20261001/`](PS_notebook/logs_20261001/README.md) |
| 板卡功耗（PMBus） | 完整设计运行 11.35 W，比仅控制器设计多 0.61 W | [`PS_notebook/logs_20261002/`](PS_notebook/logs_20261002/README.md) |

过程与判据见 [`Simulation/PV_MEV/docs/HIL_TEST_PLAN.md`](Simulation/PV_MEV/docs/HIL_TEST_PLAN.md) 第 14 节。

数据存放规则、仓库外分发包与重新生成方法见 [`DATA.md`](DATA.md)。

DAES 论文的实验结果整理、证据口径和可复现图表脚本见
[`paper/daes_results/README.md`](paper/daes_results/README.md)。
该包保留小体积原始记分卡，是 2026-10-01 之前的整理版本（最终 SIL、历史 HIL 与独立板端时序）；
论文当前使用的数据包在论文仓库 [DAES_Special_Issue](https://github.com/CNStanLee/DAES_Special_Issue) 的
`data/daes_results/`，其中 2026-10-01 / 02 的 HIL、定时与功耗记录按提交号和 SHA-256 指回本仓库。

2026-10-01 同步前的本地模型、实验数据和论文初稿完整快照见
[`reproducibility/README.md`](reproducibility/README.md)，代码与论文仓库均保存
相同的原始文件及 SHA-256 校验清单。

`Simulation/PV_MEV/docs/figures` 的完整原始数据、重建脚本与图集见
[`paper/pv_mev_figures/README.md`](paper/pv_mev_figures/README.md)。论文仓库的
`data/pv_mev/` 只保存作图所需的精简输入（带 SHA-256 清单，指回这里的完整数据），
用于结果章节的传感链机理、CC/CV 切换、恢复时间、部分负载和最终控制版本的时域对照图。
