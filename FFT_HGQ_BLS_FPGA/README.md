# FFT + HGQ2 Residual-BLS 精简 Simulink 工程

这是独立、自包含的交付包，不依赖已删除的 `HGQ_MODEL`。本目录保留 FFT+HGQ2-BLS 仿真、训练数据、重新训练、ONNX/Alkaid 导出和后续 FPGA 代码生成需要的文件。

## 快速运行

在 MATLAB R2025a 中进入本目录后执行：

```matlab
addpath("scripts")
setup_project                 % 自动修复移动后的 ONNX 路径并打开模型
```

直接运行一次本地闭环仿真：

```matlab
addpath("scripts")
out = run_closed_loop(0.15);
```

主模型为 `model/PV_MEV_FFT_HGQ_BLS.slx`。`run_closed_loop` 会关闭与估计无关的 TCP/IP 块，保持 FFT、HGQ2 ONNX 推理、watchdog、融合和 MPCC 全部在环。

需要 Simulink、Simscape Electrical/Specialized Power Systems、Deep Learning Toolbox 的 ONNX Model Predict 支持，以及 MATLAB 可用的 Python/ONNX Runtime 环境。

如果只运行现成模型，不需要重新训练，也不需要 `HGQ_MODEL`：

```matlab
cd /path/to/FFT_HGQ_BLS_FPGA
addpath("scripts")
out = run_closed_loop(0.15);
```

## 重新训练与导出

训练数据已经放在 `data/pv_mev_real.npz`。先在包目录创建 Python 环境：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[torch,onnx,hardware]'
```

一条命令完成 HGQ2 训练、Keras 保存、ONNX 导出、Simulink 接口包装、Alkaid bit-exact 检查和 ALIR 更新：

```bash
python scripts/retrain_and_export.py
```

各阶段也可以单独运行：

```bash
python scripts/train_model.py --config config/training.json --model residual_bls
python scripts/export_simulink.py --config config/training.json --model residual_bls
python scripts/check_alkaid.py --config config/training.json --model residual_bls
```

训练结果写入 `runs/pv_mev_hgq_residual_bls/residual_bls/`，部署结果写入 `artifacts/`。重新导出后在 MATLAB 执行一次 `setup_project`，Simulink 就会绑定新的 ONNX。

## 模型与控制接口

HGQ2 Residual-BLS 是固定静态结构：

```text
80点归一化波形
  -> QDense(64, ReLU)
  -> [QDense(64, ReLU) -> QDense(64, ReLU) -> QAdd(skip)] x 3
  -> QDense(8)
  -> [c1,s1,c3,s3,c5,s5,c7,s7]
```

- 30,664 个可训练参数、8 个 HGQ2 `QDense`、3 个 `QAdd`。
- 权重、激活和输出均采用 8-bit KIF 配置；没有 RNN、Attention、LayerNorm、动态尺寸或运行时可变 batch。
- 输入是 4 kHz 下的一周期 80 点窗口；归一化为 `x/max(abs(x))`。
- FFT 始终作为可信锚点和 watchdog 回退路径。
- MPCC 的逐阶融合系数为 `[0.67045, 0.72217, 0.64464, 0.41926]`，分别对应 1/3/5/7 次复相量。

完整张量约定见 `artifacts/contract.json`，训练配置见 `config/training.json`，硬件配置见 `config/deployment.json`，HGQ2 源模型位于 `src/hgq_model/models.py`。

## 离线精度

| 数据 | 方法 | Complex RMSE | 波形 NRMSE |
|---|---:|---:|---:|
| ID | FFT 1-cycle | 0.03370 | 5.958% |
| ID | HGQ2 Residual-BLS | 0.02920 | 4.099% |
| ID | FFT+HGQ2 Residual-BLS | **0.02565** | **3.224%** |
| OOD | FFT 1-cycle | 0.18136 | 25.216% |
| OOD | HGQ2 Residual-BLS | 0.06840 | 15.502% |
| OOD | FFT+HGQ2 Residual-BLS | **0.06528** | **10.071%** |

GT 是因果两周期、PLL 同步、1–15 次联合加权最小二乘估计。OOD 中单独 BLS 的 THD 比值会因预测的基波幅值接近零而数值爆炸，因此控制中必须保留 FFT 锚点、基波下限检查和回退；不要用该异常比值替代波形/复相量指标判断模型。

更完整指标见 `reports/estimator_comparison.csv`。新 HGQ2 的短闭环验证接受率为 100%；尚未把旧 Brevitas 模型的稳态 THD 当作新模型结论，详细边界见 `reports/VALIDATION.md`。

## FPGA 工程生成

包内包含目标无关的、已通过 Keras bit-exact parity 的 Alkaid ALIR：

```text
artifacts/harmonic_residual_bls.alir.json.gz
```

安装依赖并检查包：

```bash
python -m pip install -r requirements-fpga.txt
python scripts/verify_package.py
```

确定器件后生成工程，例如：

```bash
python scripts/generate_fpga_project.py \
  --part xczu7ev-ffvc1156-2-e \
  --flavor verilog \
  --clock-ns 10 \
  --validate-rtl
```

如果使用 Vitis HLS，将 `--flavor` 改为 `vitis`。目标器件尚未给定，所以本包不虚报 LUT/DSP/BRAM、Fmax 或时序闭合；生成后还必须完成 bit-true、综合、PIL/HIL 和 250 us deadline 验证。

## 目录

```text
model/       Simulink 模型、自定义库、初始化和 PV 工况数据
data/        可复现训练使用的 run-isolated 数据集
src/         HGQ2 模型、训练、ONNX 和 Alkaid 导出实现
artifacts/   HGQ2 Keras、Simulink ONNX、Alkaid ALIR、接口与一致性清单
config/      训练参数、固定点、融合系数和 I/O 配置
scripts/     训练/导出、Simulink 运行、包校验和 FPGA 生成入口
reports/     精度表、回归图和当前验证边界
```
