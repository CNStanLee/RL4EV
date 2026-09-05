# 数据存储与分发

本仓库只放源码、模型、小体积派生产物和文档。PV_MEV 注入实验产生约 3 GB 波形日志，
不进 git；它们全部可由 `Simulation/PV_MEV/run_injection.m` 重新生成，也打包成了下面的
分发包。规则写在 `.gitignore` 的 “Simulation data” 段。

## 仓库内保留的数据（约 10 MB）

| 路径 | 体积 | 内容与用途 |
|---|---:|---|
| `Simulation/PV_MEV/results/emi/scorecard.csv` | 72 KB | 104 次评估运行的全部指标（THD、恢复时间、保护动作、功率等），所有结论表与图的数据源 |
| `Simulation/PV_MEV/results/emi/scorecard_phase1.csv` | 56 KB | 阶段一 78 次运行的同格式记录，用于回归对照 |
| `Simulation/PV_MEV/results/emi/E-*_*.csv` | 0.4 MB | 每次运行一行的指标明细（104 个） |
| `Simulation/PV_MEV/results/emi/baseline_*.csv` | 60 KB | 8 种策略的无扰基线（CC 段与 CV 段） |
| `Simulation/PV_MEV/results/emi/ts/*_det.csv` | 3.0 MB + 6 MB | 逐周期检测器记录：v4 为 43 特征 / 16 输出，v5（2026-09-05 起）为 48 特征 / 20 输出 / 5 幅值，MPCC_R 运行另含 6 个 Mitigation 状态列（`scripts/sil_report.py` 直接读取） |
| `Simulation/PV_MEV/results/emi/dataset/labels.csv`、`dataset/D*.csv` | 1.3 MB | 240 次随机数据集运行的标签与指标 |
| `EMI_DET_FPGA/data/cycles_dataset.npz` | 3.8 MB | 8709 个周期 × 92 特征的训练集（重训检测器只需要它） |
| `EMI_DET_FPGA/data/cycles_phase1.npz` | 1.3 MB | 阶段一独立测试集 |
| `EMI_DET_FPGA/runs/det_v4/` | 0.9 MB | 定型检测器：Keras 模型、板上链、ONNX、阈值与训练报告 |
| `EMI_DET_FPGA/runs/{sil_report,estimator_report}/` | 0.2 MB | 评估战役的 SIL 与估计器报告 |
| `HLS_PRJ/{emi_detector,harmonic_estimator}/` | 3.5 MB | 两个 Vitis 组件：包装层、hls4ml 固件、C 测试台与参考向量 |
| `HLS_PRJ/{mpcc_r,emi_feat}/` | 2 MB | 韧性 MPCC IP 与特征提取 IP（2026-09-05），含 C 测试台与参考向量 |
| `EMI_DET_FPGA/runs/det_v5/`、`data/cycles_v3_*.npz` | 6 MB | 检测器 v5（48 特征）模型、阈值与训练报告；补充数据的逐周期特征集 |
| `EMI_DET_FPGA/runs/{resilience_report,random_sil_report,sil_report_v2,estimator_report_v2}/` | 2 MB | 韧性消融、随机工况、SIL、估计器报告与图（2026-09-05） |
| `FFT_HGQ_BLS_FPGA/{data/pv_mev_windows_v2.npz,runs/pv_mev_v2,artifacts/pv_mev_v2}` | 10 MB | 估计器 v2：PV_MEV 真实波形训练集、模型、ONNX 与 hls4ml 固件 |
| `PS_notebook/hardware/mpcc_r.{bit,hwh}` | 19 MB | ZCU104 MPCC_R overlay（Vivado 2022.2，`Vivado_PRJ/MPCC_R/build_bd.tcl` 可重建） |
| `Simulation/PV_MEV/results/emi/scorecard.csv`（更新） | | 新模型上 CRPR / MPCC_P / MPCC_D / MPCC_D_H1 / MPCC_R / MPCC_R_ON 与逐位对照各行；旧 6 策略结果仍在 `scorecard_phase1.csv` |

有了这些，不跑 MATLAB 也可以：复现全部指标表和结论、重训检测器、重跑 SIL 报告、
做板级 C 仿真。需要重画波形图或用别的方法重算特征时，才需要下面的分发包。

## 仓库外的分发包（共 2.4 GB）

打包脚本见本文件末尾，产物在 `D:/Prj/RL4EV_data_bundles/`（不在仓库内）。
校验值在同目录 `SHA256SUMS.txt`。

| 分发包 | 体积 | 内容 | 解压位置 |
|---|---:|---|---|
| `emi_campaign_ts_10kHz.tar.xz` | 55 MB | 104 次评估运行的 10 kHz 时序表（22 列，0.6–1.3 s）加逐周期检测记录 | `Simulation/PV_MEV/results/emi/` |
| `emi_dataset_ts_10kHz.tar.xz` | 125 MB | 240 次随机数据集运行的 10 kHz 时序表 | 同上 |
| `emi_snapshots.tar.xz` | 47 MB | 8 种策略在 0.6 s 的 ModelOperatingPoint 快照 | 同上 |
| `emi_campaign_iac_1MHz.tar` | 641 MB | 104 次评估运行的 1 MHz 电网电流（单精度 .mat，已由 MATLAB 压过，再压无收益） | 同上 |
| `emi_dataset_iac_1MHz.tar` | 1541 MB | 240 次数据集运行的 1 MHz 电网电流 | 同上 |

前三个是分析所需，后两个只在重算 THD 或重画电流波形时需要。
按需下载，解压后目录结构与仓库内一致，脚本无需改路径。

2026-09-05 的第二批，打成一个 zip（243 MB，SHA256 `0683ce03f7aa9e96bef54459a61f561d7aa5e9db64a2abe952ea1957655ad376`，内含 `SHA256SUMS_2026-09-05.txt`）：

https://drive.google.com/file/d/1CKC42j9BdYCIpTBw753kKhEpezDVdHpM/view?usp=sharing


| 分发包 | 内容 | 解压位置 |
|---|---|---|
| `emi_campaign2_ts_10kHz_2026-09-05.tar.xz` | 新模型（检测器 v5 + 估计器 v2 + Mitigation）上的 13 用例 × {CRPR, MPCC_P, MPCC_D, MPCC_D_H1, MPCC_R, MPCC_R_OFF, MPCC_R_ON, MPCC_R_m0..m8} 的 10 kHz 时序（无 1 MHz 电流） | `Simulation/PV_MEV/results/emi/` |
| `emi_dataset_supp_ts_10kHz_2026-09-05.tar.xz` | 随机运行 D0241 到 D0320（Iac 专项 / 双通道 / 良性补充 48 次，随机工况 SIL 40 次） | 同上 |
| `emi_snapshots_2026-09-05.tar.xz` | 新模型的 20 个 0.6 s 快照（4 策略 CC / CV、MPCC_R 变种） | 同上 |
| `mpcc_r.bit`、`system_wrapper.xsa` | ZCU104 比特流与硬件平台文件 | `PS_notebook/hardware/`、`Vivado_PRJ/MPCC_R/out/` |

注意：旧模型的 13 用例时序（第一批 `emi_campaign_ts_10kHz.tar.xz`）与新模型同名，在 Linux 机上解压到了 `results/emi/ts_v1/`（git 忽略），不要覆盖 `ts/`。

**下载**：Drive 文件是公开的，命令行直接取即可（claude.ai 的 Drive 连接器没有下载权限，与文件是否公开无关）：

```bash
pip install gdown
gdown 186uhv86RkQAilBb9XWfCzl1BwmxdGY6W        # 第一批 RL4EV_data_bundles.zip, 2.5 GB (SHA256 12c07cf8...)
unzip RL4EV_data_bundles.zip && (cd RL4EV_data_bundles && sha256sum -c SHA256SUMS.txt)
gdown 1CKC42j9BdYCIpTBw753kKhEpezDVdHpM        # 第二批 RL4EV_data_bundles_2026-09-05.zip, 243 MB (SHA256 0683ce03...)
unzip RL4EV_data_bundles_2026-09-05.zip && (cd RL4EV_data_bundles_2026-09-05 && sha256sum -c SHA256SUMS_2026-09-05.txt)
```

两批都已从 Drive 回下载校验过（2026-09-05）。

**上传到 Google Drive**：本会话没有 Drive 授权（claude.ai 的 Google Drive 连接器需要交互式
OAuth），所以分发包只生成在本地，需要你手动上传。上传后把共享链接填到上表下面：

https://drive.google.com/file/d/186uhv86RkQAilBb9XWfCzl1BwmxdGY6W/view?usp=sharing

## 重新生成

不下载分发包时，全部数据可以重跑（R2024b，单次 0.7 s 仿真约 7 分钟，最多 3 个并行进程）：

```matlab
cd Simulation/PV_MEV
run_injection('baseline', [], {'CRPR','MPCC_P','MPCC_D','MPCC_D_F1','MPCC_D_F10','MPCC_D_R','MPCC_D_M1','MPCC_D_H1'})  % 快照，约 50 min
run_injection('run', 'all', {'CRPR','MPCC_P','MPCC_D'})        % 评估战役，13 用例 × 变种，3 批并行约 10 h
run_injection('dataset', [1 240], {})                          % 随机数据集，约 40 h
run_injection('resummarize'); run_injection('merge');          % 汇总成 scorecard.csv
make_injection_figs(); make_waveform_figs();                   % 图
```

```bash
cd EMI_DET_FPGA
python scripts/build_dataset.py            # 时序 -> cycles_dataset.npz
KERAS_BACKEND=torch python scripts/train_detector_v4.py data/cycles_dataset.npz --out runs/det_v4 --test data/cycles_phase1.npz
KERAS_BACKEND=torch python scripts/export_bitexact_onnx.py runs/det_v4
KERAS_BACKEND=torch python scripts/make_board_components.py    # 两个 Vitis 组件
python scripts/sil_report.py --ts ../Simulation/PV_MEV/results/emi/ts --tests ../Simulation/PV_MEV/tests.csv --out runs/sil_report
```

## 重新打包

```bash
R=/d/Prj/RL4EV; O=/d/Prj/RL4EV_data_bundles; mkdir -p "$O"
cd "$R/Simulation/PV_MEV/results/emi"
find ts -name "E-*.csv"          | sort | tar -cf - -T - | xz -T0 -6 > "$O/emi_campaign_ts_10kHz.tar.xz"
find dataset/ts -name "D*.csv"   | sort | tar -cf - -T - | xz -T0 -6 > "$O/emi_dataset_ts_10kHz.tar.xz"
tar -cf - snapshots                     | xz -T0 -6 > "$O/emi_snapshots.tar.xz"
find ts -name "E-*_iac.mat"      | sort | tar -cf "$O/emi_campaign_iac_1MHz.tar" -T -
find dataset/ts -name "D*_iac.mat" | sort | tar -cf "$O/emi_dataset_iac_1MHz.tar" -T -
cd "$O" && sha256sum *.tar *.tar.xz > SHA256SUMS.txt
```

## 其它大文件说明

`PS_notebook/` 里的两个比特流（`mpcc_hil.bit`、`system_wrapper.bit`，各 18 MB）是 ZCU104
上板运行所需的交付物，保留在仓库中；它们已在历史里，占 git 包体积的大半。若以后要缩小
仓库，唯一办法是重写历史，需要单独决定。
