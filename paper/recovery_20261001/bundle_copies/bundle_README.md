# HIL-SAR 打包说明

本包含论文 `hil_sar_v7.pdf`（第七版，2026-09-12）的工程源码、绘图脚本，以及全部图表所依赖的数据。
打包日期 2026-09-12，对应仓库 `RL4EV` 的当前状态。

---

## 目录结构

| 目录 | 内容 |
|---|---|
| `00_paper/` | 论文 LaTeX 工程全文：`main.tex`、`sections/`、`tables/`、`tikz/`、`figures/`（已编译的 PDF 图）、`pyfig/`（绘图脚本）、`docs_v6/`（变更日志、数字溯源表、实验状态、复核清单）、构建脚本 `qa.sh` / `regen_v6.sh` / `package_v7.sh`，以及表格生成脚本 `mktables_r2.py` / `mk_partition.py` / `mk_safety.py` / `mk_mmbenign.py` |
| `01_analysis_scripts/` | 数据分析脚本：`attack_window.py`（攻击窗口指标）、`rev_report.py`（主报告，生成 rev_report 下全部 CSV）、`supp_report.py`、`coordinated.py`、`export_residual.py`、`make_paper_assets.py`、`random_sil_report.py`、`detector_eval_unified.py` 等 |
| `02_derived_results/` | 图表直接读取的派生结果层：`rev_report/`、`paper_assets/`、`detector_unified/`、`supp_report/`，以及 `hil_report/` 的四个关键 CSV |
| `03_run_scorecards/` | 每次仿真运行的评分卡，一行一次运行：`attack/`（770 个攻击运行）、`benign/`（163 个无攻击扰动运行） |
| `04_figure_waveforms/` | 图 6、图 7、图 9(e)、图 10(c) 直接画出来的时域波形，每个文件 7001 个采样点、25 列 |
| `05_board_traces/` | ZCU104 实测：`h6_run1/`（调度轨迹、延迟、PMBus 功耗）、`r7_sched/`（三种处理器-逻辑划分的 20 s 重放汇总） |
| `06_matlab_harness/` | 仿真侧：`PV_MEV.slx`（Simulink 模型）、`run_injection.m`（注入与评分主程序）、`init_paras.m`（参数初始化）、`config.csv`（变体与掩码定义）、`docs/`（测试计划） |
| `07_detector_artifacts/` | 检测器与残差基线的部署参数：`detector.json`（阈值与量化网络导出）、`residual.json`、`detector_report.json` |
| `HIL_SAR_raw_data.xlsx` | **单独发送，不在本包内**（受上传体积限制）。复核用工作簿，47 个 sheet：`00_索引` 按图/表编号列出对应 sheet，`01_数据表来源` 给出每个 sheet 的原始文件路径。其内容全部来自本包 `02_derived_results/`、`03_run_scorecards/`、`04_figure_waveforms/`、`05_board_traces/` 中的同名 CSV |
| `hil_sar_v7.pdf` | 论文正文，19 页 |
| `response_r4.pdf` | 第四轮审稿回复信 |

---

## 每张图表到数据的对应关系

完整对照见 `HIL_SAR_raw_data.xlsx` 的 `00_索引` sheet。概要：

- **图 1、图 2**：TikZ 原理图，无数值数据，源码在 `00_paper/tikz/`
- **图 3**：TikZ 原理图，资源占比取自 `02_derived_results/hil_report/incremental_cost.csv`
- **图 4**：`02_derived_results/paper_assets/tables/T1_attack_impact_controllers.csv` 与 `T3b_resilience_per_case.csv`
- **图 5**：`02_derived_results/rev_report/unified_{summary,breakdown,channels,confusion}.csv` 与 `detector_unified/runs_mlp_q_deployed_*.csv`
- **图 6**：`04_figure_waveforms/E-DC-01b_*.csv` 加 `rev_report/attack_window_metrics.csv`
- **图 7**：`04_figure_waveforms/E-MUL-01_*.csv`、`E-BAT-02c_*.csv`（三种控制器各一份）
- **图 8**：`02_derived_results/supp_report/sweep_rows.csv`
- **图 9**：`paper/tables/deadline_rows.csv`（在 `00_paper/`）、`rev_report/benign_paired.csv`、`benign_forced.csv`、`mismatch.csv`、`coordinated_drift.csv`
- **图 10**：`02_derived_results/hil_report/equivalence.csv` 与 `04_figure_waveforms/E-DC-01c_*.csv`（SIL / 修复前 / 修复后三份）
- **图 11**：`hil_report/incremental_cost.csv`、`latency.csv`、`rev_report/rt_sched.csv`、`det_path.csv`、`power_baseline.csv`、`05_board_traces/h6_run1/`
- **表 VI**：`rev_report/unified_summary.csv` 等四份
- **表 VIII、IX**：`rev_report/attack_window_metrics.csv`、`paper_assets/tables/T3*.csv`
- **表 X**：`hil_report/equivalence.csv`
- **表 XI**：`hil_report/incremental_cost.csv` + `rev_report/power_baseline.csv`
- **表 XII**：`05_board_traces/r7_sched/{allpl,cpudet,allcpu}_summary.csv`
- **表 I、III、VII**：规范性表格，无独立测量文件，定义在 `00_paper/tables/` 与 `00_paper/docs_v6/provenance.md`

---

## 重建流程

编译论文（需要 tectonic 与 IEEEtran）：

```bash
cd 00_paper
./qa.sh            # 编译 main.tex 并输出页数、溢出框、未解析引用等检查
```

重画全部图（需要 Python 3 + matplotlib + pandas；脚本内的绝对路径指向原仓库，移植时需改 `ROOT`）：

```bash
cd 00_paper/pyfig
python3 fig_impact.py && python3 fig_detect.py && python3 fig_resilience.py
python3 fig_robust.py                      # 同时输出 fig_envelope 与 fig_robust
python3 fig_hil.py && python3 fig_cost.py
python3 fig_safety.py MPCC_R6 MPCC_H6 MPCC_R_REG
```

重新生成表格：

```bash
cd 00_paper
V6MAP=1 python3 mktables_r2.py    # 表 VI、VIII、X
python3 mk_partition.py           # 表 XII
python3 mk_safety.py              # 表 IX
python3 mk_mmbenign.py            # 失配 + 良性扰动统计
```

从原始运行重算派生结果（需要完整的 `results/emi`，见下方"未包含"）：

```bash
cd 01_analysis_scripts
V6MAP=1 python3 attack_window.py
V6MAP=1 python3 rev_report.py
```

---

## 未包含的内容及原因

为控制体积，以下原始数据未打包，需要时从原仓库 `RL4EV` 取：

| 未包含 | 体积 | 路径 |
|---|---|---|
| 全部时域波形（1470 次运行） | 3.4 GB | `Simulation/PV_MEV/results/emi/ts/` |
| 检测器数据集的 291 次原始运行 | 1.1 GB | `Simulation/PV_MEV/results/emi/dataset/` |
| 工作点快照（`.mat`） | 480 MB | `Simulation/PV_MEV/results/emi/snapshots/` |
| 板上原始日志与 x86 对照运行 | 约 50 MB | `EMI_DET_FPGA/runs/hil_report/{pslogs,det,mpcc,full,x86}/` |
| 原生 C 循环的其余三种模式轨迹 | 25 MB | `hil_report/h6_run1/rt_c_mode0_fifo.csv`、`rt_c_mode1*.csv`（本包只含 `rt_c_mode0.csv`） |
| Vivado 工程与比特流 | — | `Vivado_PRJ/` |

本包内 `03_run_scorecards/` 已包含全部 933 次运行的逐次评分卡（每次一行），论文里除波形图以外的每一个数字都可以从这些评分卡加 `02_derived_results/` 复算出来；只有重画时域波形图才需要上面的 `ts/` 全集。

---

## 已知的验证边界

`00_paper/docs_v6/barriers.md` 列出全部未闭合项，其中与数据复核相关的三条：

1. 第四轮新增的消融配置（去掉 M11、去掉 M14、MPCC-H 加 55 A 限幅、残差检测器在线）只在仿真中跑过，没有上板验证。
2. 实时性证据是"仿真闭环 + 板上单独重放 + 时序拼接注入"，不是带被控对象的真实实时闭环。
3. 交接限幅按基线参考残差释放、失配与负载暂态同时发生的组合测试，均未实现。
