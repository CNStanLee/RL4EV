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

## 评估战役结果（2026-09-04，13 用例 × 8 策略 = 104 次，全部 OK）

同一战役同时给出三件事的答案：SIL 检测器在闭环里的表现、两个 HGQ2 谐波估计变种（MPCC_D_M1 原始、MPCC_D_H1 FFT+HGQ2 融合）与 FFT/RLS 变种的对比、以及阶段一结论在新模型上的复现（原 6 种策略的 78 行 scorecard 与阶段一逐值相同，说明检测器与估计器子系统对它们是纯观测）。原始数据：`Simulation/PV_MEV/results/emi/scorecard.csv`、`ts/<run>_det.csv`；报告：`runs/sil_report/`（`sil_runs.csv`、`summary.json`）、`runs/estimator_report/`。

**SIL 检测器**（`scripts/sil_report.py`，判定 = sigmoid ≥ 阈值且连续 2 周期）

| 指标 | Simulink SIL | 离线参考（features.py + 位精确 ONNX） |
|---|---:|---:|
| 检出（延迟有限且注入周期覆盖 ≥ 50%） | 96 / 104 | 96 / 104 |
| 单通道用例（12 × 8） | 96 / 96 | 96 / 96 |
| 双通道 E-MUL-01（Vdc +50 V 与 Iac +5 A） | 0 / 8（Vdc 全部检出，Iac 分量全部漏检） | 同 |
| 延迟中位数 | 2 周期（40 ms，等于持续判据下限） | 2 周期 |
| 注入前误报周期 | 0 / 416 | 0 / 416 |
| 撤除后（t_off + 60 ms 起）误报周期 | 8 / 1248（全部 MPCC_P，撤除后恢复慢） | 11 / 1248 |
| 与 Simulink 标志字不同的周期 | — | 35 / 3640 |

- 每种策略 13 个用例中检出 12 个（漏的都是 E-MUL-01 的 Iac 分量），策略之间没有差别：检测器对控制策略是不变的。
- 漏检的 Iac +5 A 偏置（峰值约 63 A 上的 8%）与留出评估中的 Iac 弱项一致；下一步若要覆盖它，需要 Iac 专项数据（此前未批准的 60 次补充）或 Iac 交叉校验特征。
- E-DC-01c（Vdc +100 V，母线被钳到 336 V）下 Vdc 之外的通道也会置位（wrong_channel_frac = 1）：这是物理后果（充电级失调、Iref 跌落），不是误报。
- 战役期间 Simulink 里跑的是 Keras 导出的旧 ONNX；用位精确 ONNX 在同一批 Simulink 特征上重算（`scripts/redecide.py`）：3744 个周期中 23 个标志字不同，只有 2 次运行首次置位时刻变化（各 1 周期）。战役结束后 `artifacts/detector.onnx` 已替换为位精确版本（旧文件保留为 `detector_keras_export.onnx`）。

**谐波估计变种**（`scripts/estimator_report.py`；充电级负载 6.9 kW）

| 变种 | 基线 THD50 | 基线全带 THD | E-AC-01a | E-AC-01b | E-BAT-01b | E-DC-01b | 恢复时间（E-DC-01b / 01c） | 保护动作 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| MPCC_D（无补偿） | 5.48% | 5.68% | 6.19% | 8.57% | 5.95% | 6.93% | 120 / 122 ms | E-BAT-01n BOC、E-DC-02b OV |
| MPCC_D_F1（FFT 1 周期） | 2.76% | 3.28% | 4.29% | 7.78% | 3.00% | 3.71% | 180 / 200 ms | + E-BAT-02c OC |
| MPCC_D_F10 | 2.70% | 3.10% | 4.29% | 7.80% | 3.05% | 3.69% | 120 / 160 ms | 同 MPCC_D |
| MPCC_D_R（RLS） | 2.80% | 3.11% | 4.72% | 8.19% | 2.99% | 3.68% | 120 / 140 ms | + E-BAT-02c、E-DC-01c、E-MUL-01 OC |
| MPCC_D_M1（HGQ2 原始） | 3.18% | 3.66% | 4.12% | 5.97% | 3.51% | 4.26% | 180 / 260 ms | + E-DC-01c OC |
| MPCC_D_H1（FFT+HGQ2 融合） | 3.02% | 3.59% | 4.08% | 6.42% | 3.34% | 4.08% | 180 / 200 ms | + E-DC-01c OC |

- 基线上 HGQ2 变种比 FFT/RLS 变种差 0.3 到 0.4 个百分点（8-bit 量化模型，训练数据来自旧工况），融合（H1）把差距缩到 0.25 pp。
- 交流链偏置（E-AC-01a/01b/02b）下 HGQ2 变种反而最好：E-AC-01b（Vac 谐波注入）THD50 5.97% / 6.42% 对 FFT 的 7.78%，因为估计器直接看内部电流波形而不依赖被污染的锁相谐波基准；直流与电池链偏置下 HGQ2 变种比 F1 差约 0.5 pp（估计器输入偏离训练分布）。
- 恢复时间与 F1 同级（一周期估计窗 + 融合 EMA），比 F10/R 慢 40 到 60 ms；E-DC-01c 下 M1 最慢（260 ms）。保护动作与 F1/R 同类：E-DC-01c 的 OC 出现在 M1、H1、R，F1 没有；E-BAT-02c 的 OC 出现在 F1、R，M1、H1 没有——都是 1 到 2 个周期的电流尖峰差异，不是系统性优劣。
- 结论：两个 HGQ2 变种在闭环注入下与 FFT/RLS 变种同一水平，交流链偏置下略优，基线略差；作为阶段三"检测后切换估计源"的候选是可用的。

**图**：`Simulation/PV_MEV/docs/figures/fig2..fig8`（已含 M1、H1 列）、`docs/figures/waveforms/<case>_{state,iac,transition}.png`（8 种策略）、`runs/estimator_report/estimator_thd_cases.png`。

## 阶段二 B / C 现状（2026-09-04）

- **可用检测器**：`scripts/train_detector_v4.py`——sklearn 多标签 MLP（64-64，43 个基础特征，标准化输入）作为初始化，迁入 HGQ2 `QDense`（激活 kif 1/4/7，权重 1/2/7）做短量化感知微调。留出运行 34 / 45，阶段一独立 72 / 78，清洁周期误报 2.5% / 3.3%，延迟中位 1 周期；ONNX 与 Keras 逐值一致。产物：`artifacts/detector.onnx`（含标准化，43 → 5 + 10 + 1）、`artifacts/detector.json`（阈值、mu、sd）、`runs/det_v4/chain_std.keras`（板上模型：标准化输入的纯 QDense 链）。
- **从头训练的 Keras 管线为何失败**：类别加权 + 多任务头 + dropout + 按 val_loss 早停导致严重欠训练（14 到 23 / 45），基线相对特征块与策略 one-hot 反而降低留出性能；随机森林（`eval_channels.py`）仍是上限参考（160 / 185）。
- **Simulink SIL**：`Simulation/PV_MEV/build_detector.m` 在 `PFC Control` 内加入 `EMI Detector`（10 kHz 缓冲 → 43 特征 → `OnnxRunner`（Python onnxruntime 桥）→ 阈值 + 连续计数），逐周期输出 `det_*` 由 `run_injection` 记录到 `<run>_det.csv`；`scripts/sil_parity.py` 做 Simulink 与 Python 特征、ONNX 输出的逐周期对照。
- **上板版本**：`hls4ml 1.3`（Vitis 后端，`bit_exact=True`，xczu7ev，10 ns）生成的两个工程已包装成与 `HLS_PRJ/mpcc` 同款的 Vitis 统一流程组件（`scripts/make_board_components.py`）：`HLS_PRJ/emi_detector/`（`emi_detector_axi(float feat[43], float logit[5], unsigned *flags)`，包装层做标准化 `(x-mu)*inv_sd` → `ap_fixed<12,5>` 与 1% 误报阈值 → 标志位，2 周期持续判据留给 PS）与 `HLS_PRJ/harmonic_estimator/`（`harmonic_estimator_axi(float wave[80], float enc[8], float *peak, float legacy[7])`，包装层做 CycleNorm 与 `harmonic_postprocess8_block` 同款解码，输出 MPCC 用的 `[A1,A3,A5,A7,delta3,delta5,delta7]`）。两者各带 `hls_config.cfg`、`vitis-comp.json`、C 测试台与参考向量；本机没有 Vitis，用 `scripts/csim_local.sh`（zig c++，hls4ml 自带 ap_types）做了 C 仿真：估计器 361 个窗口与 ONNX 参考逐值相同（max 0）；检测器 1089 个周期 max |Δlogit| 4.6e-5、标志字全部一致。综合、协同仿真与资源/延迟数字留到 Vitis 主机（`vitis-run --mode hls --cfg hls_config.cfg --csynth`）。`da4ml` 路线不适用：它只接受 WRAP 溢出模式，而两个模型都以 SAT 训练，WRAP 复刻在数据集上偏差达数百 logit（`scripts/fpga_export.py` 记录了检查）；标准化不能折进第一层权重（折叠后 |Δlogit| 130）。
- **ONNX 舍入缺陷（2026-09-04 发现）**：Keras/torch 导出的 `artifacts/detector.onnx` 把 HGQ2 定点量化器映射成 `Round`（四舍六入五成双），而 HGQ2 与 hls4ml 固件（`AP_RND`）是逢五进一；激活与权重都在 2^-7 网格上，累加结果是 2^-14 的整数倍，平局非常频繁，结果该 ONNX 与训练网络在几乎每个周期都不同（8709 周期 max |Δlogit| 4.3、rms 0.41、68 个周期的标志判定不同）。`scripts/export_bitexact_onnx.py` 直接按定点语义构图（Sub/Mul 标准化 → Mul/Add/Floor/Clip 量化 → Gemm → Relu），`artifacts/detector_bitexact.onnx` 与 Keras 链在全数据集上逐值相同（max 0），接口与旧文件一致（43 → 5 + 10 + 1），可直接替换 `OnnxRunner` 的模型文件。当前评估战役（104 次）仍使用旧 ONNX，跑完后用 `scripts/redecide.py` 在 Simulink 记录的特征上重算判定，量化两者差异后再切换。
