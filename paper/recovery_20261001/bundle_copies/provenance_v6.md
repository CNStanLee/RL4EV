# 数字溯源表（v6）

每一行：论文中的数字 → 原始文件 → 生成脚本 / 命令 → 模型或固件版本。"v5 模型"= 2026-09-10 之前的 PV_MEV.slx（tick_hold 之后、handover 补丁之前）；"v6 模型"= 2026-09-11 handover 补丁（M11/M12/M13，电压环 Ilim 输入，充电控制器 5 元状态）之后。板上固件（四个 IP、bitstream）在 v5/v6 之间没有改动。

## 1. 检测（不依赖 v6 模型；数据集与基准运行来自 v5 及更早模型）

| 论文数字 | 值 | 原始文件 | 脚本 | 备注 |
|---|---|---|---|---|
| 数据集运行数 / hold-out | 291 / 73（54 攻击） | `results/emi/dataset/labels.csv`（311 行 = 291 + 20 随机）；`EMI_DET_FPGA/data/cycles_v3_all.npz` | `detector_eval_unified.py` | v5 写 288，已改 |
| 基准 104 次：any / exact / superset / partial / miss | 98.1 % (102) / 38.5 % (40) / 54 / 8 / 2 | `runs/detector_unified/unified.csv`, `unified_breakdown.csv` | `detector_eval_unified.py` | 部署 ONNX，出厂阈值 |
| 每周期精度 / 召回 | 76.9 / 82.2 % | 同上 | 同上 | |
| 分通道精度 / 召回 | 93.5 88.2 86.6 91.4 43.7 / 93.3 93.3 70.0 62.1 93.3 % | 同上 | 同上 | |
| 延迟 | 40 ms（99/104），最大 120 ms；随机集中位 34 ms | 同上 | 同上 | 延迟 = 与攻击重叠的周期数至判定周期 |
| 随机 20 例 | any 100 %，4 个攻击前误报周期（3 个在一次良性运行） | 同上 | 同上 | |
| 同划分量化对比 | float 65.4 / 70.6 / 48.1 vs HGQ 68.3 / 58.8 / 51.9 % exact | `runs/detector_unified/unified_samesplit.csv` | `quantise_unified.py` | seed-0 划分 |
| 部署检查点重标定 | 45.2 % exact / 96.2 % any | `unified.csv`（recal 行） | `detector_eval_unified.py` | |
| 残差基线 | any 46 / 48 %，Vdc/Vac 召回 92 / 93 % | `unified.csv`（residual 行） | 同上 | |
| 训练参数 | RF 400 树、min_samples_leaf 2、balanced_subsample；软标签 0.5·y + 0.5·p_rf；BCE + 0.3·masked MSE；Adam 1e-3，300 epochs，早停（val_loss，patience 40）；HGQ 微调 Adam 3e-4，80 epochs（patience 20） | `scripts/train_detector_v5.py` | — | |
| 误报分母 | 基准 520 = 104 × 5 预攻击周期；随机集 248 = 142（攻击运行的预攻击周期）+ 106（3 个良性运行的全部周期） | `data/cycles_v3_all.npz`, `detector_eval_unified.py`（pre 定义） | 本次计算 | |
| 蒸馏 vs 普通标签 | 71 % exact / 78 FA vs 67 % / 0 | `unified.csv` | 同上 | |

## 2. 硬件实现与板上时间（与模型版本无关）

| 论文数字 | 值 | 原始文件 | 备注 |
|---|---|---|---|
| 四个 IP 的 LUT/FF/BRAM/DSP | Table VII | `runs/hil_report/incremental_cost.csv`；Vivado 布线后报告 | |
| latency 策略 315k LUT = 1.37× 器件 | 315k / 230 400 | hls4ml 综合报告（EMI_DET_FPGA/hls4ml_prj_latency） | v5 写 "四倍"，已改 |
| 特征核 2 423 周期 = 24.2 µs；31 µs 单任务调用 | | `hil_report/latency.csv`（feat 行）、HLS 报告 | |
| 检测网络 2.6 µs 核时间；27 µs 调用 | | 同上 | |
| tick 逻辑 2.4 µs（中位 2.6，最大 2.9）；C 循环 3.7–5.4 µs；Python 65 µs | | `hil_report/latency_mpcc_r*.csv`, `paced_*.csv` | |
| 并发重放（h6_run1）：tick 4.0/9.2 µs，124 late（91 dropped），最长 37 拍 1.85 ms；检测 393.6 µs；估计器 19.4/31.2 µs，1 late | | `hil_report/h6_run1/rt_sched_summary.csv`, `rt_sched_mpcc.csv` | 普通优先级绑核（rt_sched.c） |
| 分区对比三次重放（v6 新增） | Table `tab:partition` | `runs/rev_report/r7_sched/{allpl,cpudet,allcpu}_summary.csv` | `rt_sched_cpu.cpp`（同目录）；2026-09-11 |
| CPU 基线（单任务）：特征 60.4 µs，网络 38.9 µs，tick 1.14 µs（最大 21.3） | | `runs/rev_report/cpu_baseline.txt` | 绑核 2，SCHED_FIFO 80 |
| 功率 1.50 / 1.75 / 2.00 W；12 V 10.69/10.80 vs 11.02/11.39 W | | `hil_report/h6_run1/power.csv`, `power2.csv` | PMBus |
| 等价性：det 13/13 Δ=0；est 2/2；mpcc 6/8 tick-eq，8/8 scorecard；full 5/7，7/7；random 2/3；x86 4/7，7/7 | | `hil_report/equivalence.csv` | `mktables_r2.py` → `tab_hil.tex` |

## 3. SIL 结果（v6 运行集；表格由 `attack_window.py` + `rev_report.py` + `make_paper_assets.py` + `mktables_r2.py` 以 `V6MAP=1` 生成）

归档：v5 的派生表在 `EMI_DET_FPGA/runs/rev_report_v5/` 与 `runs/paper_assets_v5/`（2026-09-11 由未改动的 v5 运行文件重新生成，`tab_resilience.tex` 逐字复现）；`runs/rev_report/` 与 `runs/paper_assets/` 在 `regen_v6.sh` 之后为 v6。`attack_window.py` 复现旧表至 0.11 J / 0.12 V 以内（窗口 0.7–1.0 s，右开）。

（运行完成后填写：每一行给出 case × variant 的 `results/emi/<case>_<variant>.csv` 及 `rev_report/attack_window_metrics.csv` 的行。）

| 论文数字 | 值 | 原始文件 | 状态 |
|---|---|---|---|
| 13 例：MPCC-H（MPCC_H6）latched 3 / joint 5 / deficit 7.18 kJ / \|ΔP\| 29.66 pp (11) 29.06 (13) / \|ΔVdc\| 23.99 V / ΔTHD 72.9 pp / t_rec 120 ms / viol 294 ms / peak bus 117 V | 与 v5 一致 | `results/emi/E-*_MPCC_H6.csv` + `ts/`（v6 模型，09:12） | 已完成 |
| 13 例：MPCC-R w/o M11, M14（MPCC_R_REG，437）latched 4 / joint 8 / 2.44 kJ / 0.0004 pp (11) 3.96 (13) / 0.28 V / 1.8 pp / 66 ms / 65 ms / 69 V | 与 v5 一致 | `results/emi/E-*_MPCC_R_REG.csv`（v6 模型） | 已完成 |
| 13 例：MPCC-R（MPCC_R6，18869）latched 2 / joint 10 / 2.49 kJ / 0.0004 pp (11) 3.96 (13) / 0.32 V / 1.7 pp / 57 ms / 65 ms / 69 V | 10:58 | `results/emi/E-*_MPCC_R6.csv` + `ts/`（v6 模型，M11 规则修正后） | 已完成 |
| 配对安全表：both 2 / H only 1 / R only 0 / none 10；峰值电流 E-MUL-01 54.9 A、E-BAT-02c 50.5 A、E-DC-02b 53.3 A | | `mk_safety.py MPCC_H6 MPCC_R_REG MPCC_R6` → `tab_safety.tex` | 已完成 |
| oracle 0 cyc：latched 1 / joint 11 / 0.55 kJ / 0.07 V / 22 ms；oracle 3 cyc：2 / 10 / 2.21 kJ / 0.10 V / 58 ms；检测器 − OR3 = 0.28 kJ 全在 E-BAT-02b（280 J）；OR3 − OR0 = 1.66 kJ（DC-01b 170、DC-01c 551、BAT-02b 211、BAT-02c 568、MUL-01 157 J） | 11:00 | `results/emi/E-*_MPCC_R6_OR{,3}.csv` | 已完成 |
| oracle 1 / 2 cyc：1 / 11 / 1.73 kJ；2 / 10 / 2.07 kJ；P1：3 / 9 / 1.95 kJ；B (M9)：2 / 8 / 3.66 kJ；BR = R6 | 17:33 | `results/emi/E-*_MPCC_R6_{OR1,OR2,P1,B,BR}.csv` | 已完成 |
| 能量亏损 / 限值内时间 / 峰值母线（Table V 全部行） | 见上 | `rev_report/attack_window_metrics.csv`（`attack_window.py`, V6MAP） | 已完成 |
| E-MUL-01、E-BAT-02c 峰值电流与闭锁 | 无 M11/M14：72.6 A @ 75.3 ms、66.0 A @ 116.2 ms（v6 模型 MPCC_R_REG）；部署：54.9 / 50.5 A 无闭锁 | `results/emi/ts/E-MUL-01_MPCC_R_REG.csv`, `..._MPCC_R6.csv`；`tab_safety.tex`, `fig_safety.pdf` | 已完成 |
| 良性 14 例 + 强制标志 | 自然：功率相同、母线 ≤0.03 V、THD 0.12 pp 内（50.5 Hz 例 −0.7 pp）、R 151 / H 177 周期；强制：功率相同、母线 ≤0.20 V、THD ≤+4 pp、OC 一次 | `results/emi/benign/scorecard.csv`, `rev_report/benign_paired.csv`, `benign_forced.csv` | 已完成 |
| 协同攻击 E-MUL-02/03 | v6：1.9 / 28.2 %；oracle 双标志 +107 / +115 V OV | `rev_report/coordinated_drift.csv`（`coordinated.py`, V6MAP） | 已完成 |
| 慢漂移 50/100 V/s | v6：11.1 / 4.4 V（H 11.1 / 22.3 V）；ramp 250/500 V/s 1.7 / 1.1 V 无闭锁 | 同上；`paper/tables/deadline_rows.csv` | 已完成 |
| 保持注入（1.85 ms 突发，7 次） | v6：功率相同、无闭锁、峰值 50–57 A、母线 ≤2.7 V；E-BAT-02b 修正时刻突发使 Vbat 标志提前两周期，轨迹差最大 34 V 持续 52 ms（对修正有利） | `rev_report/hold_injection_v6.csv` | 已完成（17:23） |
| 模型失配（v6）：η=0.95 母线例 plain 18.0 / 17.7 V、BR 0.5 / 0.4 V，均无闭锁；Rint×1.5、L×0.5 复现标称；电池例在 η=0.95 两者都不恢复 | 19:15 | `results/emi/E-*_MPCC_R6{,_BR}_{eff95,eff90,rint150,lchg50}.csv`，`rev_report/mismatch.csv` | 已完成 |

### 3b. 包络族与随机场景（tier3，22:55 完成）
| 论文数字 | 值 | 原始文件 | 状态 |
|---|---|---|---|
| 幅值扫描：母线阶跃 20–100 V 内 ≤0.2 V；−50 V 阶跃两者 OC；Vbat ≥15 V 100 % 无闭锁 | | `results/emi/E-SW-*_MPCC_R6.csv`（H 侧保留 v5 `MPCC_D_H1`），`supp_report/sweep_rows.csv` | 已完成 |
| 增益族：±10 % 母线 → R ≤0.2 V；−10 % 在 16 ms 全部 OC；+10 % Vac 增益 R −7 V（M11 在后果标志上介入）；+5 % Vbat 增益 R 100 % | | `results/emi/E-GN-*_MPCC_R6.csv`，`supp_report/gain_family.csv` | 已完成 |
| ramp 2000/4000 V/s：全部在 26.9/15.7 ms OC；deadline 表 | | `paper/tables/deadline_rows.csv`（`make_extra_figs.py`，V6MAP） | 已完成 |
| CV 段：R 94.6 %、1.1 V、仅 E-DC-02b OV、E-BAT-02c 30 %；H 61.6 % | | `results/emi/E-*_MPCC_R6_cv.csv`，`supp_report/cv_vs_cc.csv` | 已完成 |
| 随机 20 场景：R 96.5 % vs H 86.5 %；5.1 vs 11.9 V；4.7 vs 136 pp；闭锁 3 vs 3；5/0、13/0 | | `results/emi/dataset/D03*_MPCC_{R6,H6}.csv`，`runs/random_sil_report/summary.csv` | 已完成 |
| 保持注入 7 次；良性标志周期 H 177 / R 151 / P1 198 | | `rev_report/hold_injection_v6.csv`，`benign/scorecard.csv` | 已完成 |

## v7 新增（第四轮审稿，2026-09-12；模型 = v6 最终 + 残差开关 v6c，det_src=0 时与 v6 最终逐项相同，见 chk）

| 论文数字 | 值 | 原始文件 | 脚本 | 备注 |
|---|---|---|---|---|
| Table VIII without M11 | 0.34 V / 2.50 kJ / 71 ms / latched 5 / joint 7 | `results/emi/E-*_MPCC_R6_noM11.csv`（掩码 16821） | attack_window.py → `rev_report/attack_window_metrics.csv`（V6MAP）→ mktables_r2.py | E-DC-01b/01c 文件 01:01/01:09（补丁前模型），其余 02:39–04:01 |
| Table VIII without M14 | 2.50/6.1 pp / 4.00 V / 2.81 kJ / latched 2 / joint 10 | `E-*_MPCC_R6_noM14.csv`（2485） | 同上 | 同上 |
| Table VIII MPCC-H, 55 A | 32.16/30.6 pp / 22.82 V / 7.56 kJ / 193 ms / latched 1 / joint 5 | `E-*_MPCC_H6_L55.csv`（mask 0，Limit_V 55） | 同上 | E-DC-01b/01c 01:08/01:15（补丁前），其余 02:48–04:02，快照 `MPCC_H6_L55.mat` 02:35 重生成 |
| Table VIII residual det. | 19.48/20.4 pp / 16.81 V / 5.43 kJ / 309 ms / latched 3 / joint 7 | `E-*_MPCC_R6_RES.csv`（18869，det_src 1） | export_residual.py → `artifacts/residual.json`；同上 | 01:26–02:03 |
| 消融段逐例数字（116/116/75 ms OC；72.5 %，−48 V；117.9 vs 125.9 %，−37 V） | | 同上各文件的 trip / t_trip_ms / power_retention_pct / dVdc_V | 直接读取 | |
| 失配 + 电池攻击 | E-BAT-02b 49.4/49.3 %；E-BAT-02c 4.9 % +85 V OV 9.0 ms / BR 100 % OV 10.9 ms；η=0.90 R 两例 OV，BR 49.9 / 33.6 % | `E-BAT-02{b,c}_MPCC_R6{,_BR}_eff9{5,0}.csv` | rev_report.py → `rev_report/mismatch.csv` | v6 运行 |
| 失配 + 自然误报 | 标志周期 117 / 671 / 710；R：B-CHG-05 OV 9.8 ms、VM10 75.8 %、VM20 67.0 %；BR：八例 ≤0.6 V、三例 ≤3.1 V、VM20 67.6 %、B-CHG-05 THD 16.4 % | `results/emi/benign/B-*_MPCC_R6{,_BR}_eff95.csv`（12 × 2，01:02–02:32） | mk_mmbenign.py → `rev_report/mmbenign_eff95.csv` | BR 快照 `MPCC_R6_BR_eff95.mat`；R6 用标称快照（与 v5 失配协议一致） |
| 检测延迟分层 101 / 100 / 74（最大 60 / 120 / 180 ms） | | `rev_report/flag_latency_benchmark.csv` | rev_report.py | |
| 模型来源表（Table VII） | det_v5 180/60，阈值 0.10/0.05/0.20/0.05/0.05；46/16/11 | `data/cycles_dataset.npz`、det_v5 训练日志、`runs/detector_unified/` | detector_eval_unified.py | D0292–D0300 未运行 |
| 分区表 late/dropped/max | 146/122/863；111/98/26；28/16/197 | `rev_report/r7_sched/{allpl,cpudet,allcpu}_summary.csv` | mk_partition.py | v6 板上测量 |
| 补丁后一致性 | MPCC_R6_chk = MPCC_R6（E-DC-01b、E-BAT-02c） | `E-*_MPCC_R6_chk.csv` | 直接比较 | |
| 随机 HIL scorecard 3/3 | | `results/emi/hil_full/dataset/D030{1,2,3}*` vs `dataset/` | 直接比较 | |
