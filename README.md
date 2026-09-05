# RL4EV

光伏—电动车充电系统的 PFC 控制、EMI 传感链注入研究与 FPGA 部署。

| 目录 | 内容 |
|---|---|
| [`Simulation/PV_MEV/`](Simulation/PV_MEV/) | 主 Simulink 模型（PV + 三相 PFC + 充电级）、8 种控制策略、注入试验台与运行脚本；文档见 [`docs/EMI_INJECTION_TEST_PLAN.md`](Simulation/PV_MEV/docs/EMI_INJECTION_TEST_PLAN.md)、[`docs/EMI_DETECTION_PHASES_2-4_PLAN.md`](Simulation/PV_MEV/docs/EMI_DETECTION_PHASES_2-4_PLAN.md) 与 [`docs/RESILIENT_MPCC_AND_OFFLOAD_PLAN.md`](Simulation/PV_MEV/docs/RESILIENT_MPCC_AND_OFFLOAD_PLAN.md)、[`docs/HIL_TEST_PLAN.md`](Simulation/PV_MEV/docs/HIL_TEST_PLAN.md)（HIL 联调计划） |
| [`EMI_DET_FPGA/`](EMI_DET_FPGA/README.md) | EMI 注入检测器：逐周期特征、HGQ2 量化模型、训练与评估脚本、SIL 报告 |
| [`FFT_HGQ_BLS_FPGA/`](FFT_HGQ_BLS_FPGA/README.md) | HGQ2 Residual-BLS 谐波估计器：模型、训练数据、ONNX 与接口约定 |
| [`HLS_PRJ/`](HLS_PRJ/) | Vitis HLS 组件：`mpcc`（预测控制）、`emi_detector`、`harmonic_estimator` |
| [`Vivado_PRJ/`](Vivado_PRJ/)、[`PS_notebook/`](PS_notebook/) | ZCU104 工程与 PYNQ 上板运行环境 |

数据存放规则、仓库外分发包与重新生成方法见 [`DATA.md`](DATA.md)。
