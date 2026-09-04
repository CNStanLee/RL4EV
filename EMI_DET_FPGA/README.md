# EMI_DET_FPGA — EMI 注入检测器（阶段二）

依据 `Simulation/PV_MEV/docs/EMI_DETECTION_PHASES_2-4_PLAN.md` 第 2 节。检测器只使用控制器内部量（注入后的 Vdc、Vac、Iac，Iref、θ_pll、D，充电级的 Vbat、Ibat、D_dcdc、state、Iref_bat），每个工频周期给出一次判决：10 类（无注入、Vdc+、Vdc−、Vac 直流、Iac 直流、Iac 正交、Iac Hall、Vbat、Ibat、多通道）加归一化幅值回归。

## 目录

| 路径 | 内容 |
|---|---|
| `src/emi_det/features.py` | 路线 B 的 41 个逐周期特征（Goertzel 谐波、半周不对称、参考相关、功率平衡残差、周期差分等）、类别映射、逐周期标签 |
| `scripts/build_dataset.py` | 从 `run_injection` 的时序 csv 组装逐周期数据集（npz）；来源为 `tests.csv` 用例 + 基线，或 `dataset/labels.csv` 随机运行 |
| `scripts/quick_eval.py` | 随机森林可分性检查（按运行或按策略留出），逐类精确率 / 召回率、误报、检测延迟、特征重要性 |
| `scripts/train_detector.py` | HGQ2 量化 MLP（默认 48-32，权重 kif 1/2/7，激活 1/4/7），`--float` 为浮点参考；输出 `model.keras`、`norm.json`、`report.json` |
| `data/` | 数据集 npz（未提交） |
| `runs/` | 训练输出（未提交） |

## 环境

conda 环境 `hgq2`（`D:\Anaconda\envs\hgq2`，Python 3.11）：torch 2.11 cu128、keras 3.15、HGQ2（git）、onnx / onnxruntime、scikit-learn、pandas。Keras 必须用 torch 后端：`KERAS_BACKEND=torch`（脚本内已默认设置）。`alkaid`（FPGA 导出）不在 PyPI 上，尚未安装。

```bash
# 阶段一 84 条运行 → 逐周期数据集，并做可分性检查
python scripts/build_dataset.py --out data/cycles_phase1.npz --tests ../Simulation/PV_MEV/tests.csv \
    --ts ../Simulation/PV_MEV/results/emi/ts --baselines ../Simulation/PV_MEV/results/emi
python scripts/quick_eval.py data/cycles_phase1.npz --holdout-variant MPCC_P
# 随机数据集（run_injection('dataset', ...) 生成后）
python scripts/build_dataset.py --out data/cycles_dataset.npz --labels ../Simulation/PV_MEV/results/emi/dataset/labels.csv \
    --ts ../Simulation/PV_MEV/results/emi/dataset/ts
python scripts/train_detector.py data/cycles_dataset.npz --out runs/det_mlp --test data/cycles_phase1.npz
```

## 阶段一数据上的初步结果（2026-09-03，留出一种策略作为测试）

| 模型 | 留出 | 稳态周期准确率 | 误报 / 无注入周期 | 检测延迟（周期，中位 / 最大） |
|---|---|---|---|---|
| 随机森林 | MPCC_D_R | 100% | 0 / 255 | 1 / 1 |
| 随机森林 | CRPR | 98% | 5 / 255 | 1 / 3 |
| 随机森林 | MPCC_P | 95%（Vdc− 召回 0.2，Iac 直流 0.6） | 0 / 255 | 1 / 2 |
| MLP 浮点 48-32 | MPCC_P | 99.3% | 0 / 255 | 1 / 1 |
| HGQ2 MLP，激活 4/7、权重 2/7 | MPCC_P | 98.7% | 3 / 255 | 1 / 1 |
| HGQ2 MLP，激活 3/5、权重 1/6 | MPCC_P | 91.1% | 18 / 255 | 1 / 3 |

阶段一数据每类只有一两个幅值档位，且没有良性瞬态，这些数字只说明特征能区分类别、能跨策略泛化，不代表最终性能。

## 随机数据集（240 条运行，2026-09-04）上的结果

数据：`run_injection('dataset',[2 240])`，含无注入 55、单通道 146、双通道 39 条，良性瞬态（充电电流阶跃、Vref 阶跃、测量噪声）与 CC / CV 两种工作点。特征为 43 个基础特征 + 43 个基线相对量 + 6 个策略 one-hot（`features.FEATURE_NAMES_V2`），目标为逐通道存在（`ych`）。

| 模型 / 评估 | 注入运行检出 | 单通道检出（Vdc / Vac / Iac / Vbat / Ibat） | 误报（清洁周期） | 延迟 |
|---|---|---|---|---|
| 随机森林，5 折按运行留出，逐通道 1% 误报预算（`eval_channels.py`） | 160 / 185 | 29/30、31/33、20/27、29/29、26/28；双通道 26/39 | 179 / 6425（2.8%，任一通道） | 中位 1 周期，90 分位 2 |
| 浮点 MLP 48-32（`train_detector.py --float`），留出运行 / 阶段一独立测试 | 29 / 45，63 / 78 | — | 44 / 1622，73 / 1578 | 中位 1 到 2 周期 |
| HGQ2 MLP 激活 4/7、权重 2/7 | 24 / 45，32 / 78 | — | 39 / 1622，93 / 1578 | — |

漏检集中在 Iac 链小幅值（< 8 A 时 4 / 9）与 Iac 正弦（1 / 5）。MLP 过拟合（训练集 100%），下一步是正则化、特征筛选和更多 Iac 类样本后再量化。

## 阶段二 B / C 现状（2026-09-04）

- **可用检测器**：`scripts/train_detector_v4.py`——sklearn 多标签 MLP（64-64，43 个基础特征，标准化输入）作为初始化，迁入 HGQ2 `QDense`（激活 kif 1/4/7，权重 1/2/7）做短量化感知微调。留出运行 34 / 45，阶段一独立 72 / 78，清洁周期误报 2.5% / 3.3%，延迟中位 1 周期；ONNX 与 Keras 逐值一致。产物：`artifacts/detector.onnx`（含标准化，43 → 5 + 10 + 1）、`artifacts/detector.json`（阈值、mu、sd）、`runs/det_v4/chain_std.keras`（板上模型：标准化输入的纯 QDense 链）。
- **从头训练的 Keras 管线为何失败**：类别加权 + 多任务头 + dropout + 按 val_loss 早停导致严重欠训练（14 到 23 / 45），基线相对特征块与策略 one-hot 反而降低留出性能；随机森林（`eval_channels.py`）仍是上限参考（160 / 185）。
- **Simulink SIL**：`Simulation/PV_MEV/build_detector.m` 在 `PFC Control` 内加入 `EMI Detector`（10 kHz 缓冲 → 43 特征 → `OnnxRunner`（Python onnxruntime 桥）→ 阈值 + 连续计数），逐周期输出 `det_*` 由 `run_injection` 记录到 `<run>_det.csv`；`scripts/sil_parity.py` 做 Simulink 与 Python 特征、ONNX 输出的逐周期对照。
- **上板版本**：`hls4ml 1.3`（Vitis 后端，`bit_exact=True`，xczu7ev，10 ns）已生成两个工程：`fpga/estimator_hls4ml/`（HGQ2 Residual-BLS 谐波估计器）与 `runs/det_v4/fpga/hls4ml/`（检测器链）。Windows 上 hls4ml 的 C 仿真脚本不可用（需要 Linux shell），C/RTL 协同仿真与综合留到 Vitis HLS 主机。`da4ml` 路线不适用：它只接受 WRAP 溢出模式，而两个模型都以 SAT 训练，WRAP 复刻在数据集上偏差达数百 logit（`scripts/fpga_export.py` 记录了检查）；标准化必须在特征提取模块内以定点常数完成，不能折进第一层权重（折叠后 |Δlogit| 130）。
