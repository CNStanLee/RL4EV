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

阶段一数据每类只有一两个幅值档位，且没有良性瞬态，这些数字只说明特征能区分类别、能跨策略泛化，不代表最终性能；幅值泛化与误报率要等随机数据集（`run_injection('dataset')`）。
