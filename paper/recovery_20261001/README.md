# 2026-09-05 之后未入库工作的恢复记录

RL4EV 在 2026-09-05 15:47（UTC，提交 `e2b41c3`）之后的工作——上板 HIL、`i_ref` 修正、最终版（v6）模型与脚本、
分析脚本——都在工作目录 `/mnt/data6/playground/OLD_BRANCH/RL4EV` 中完成，从未提交，该目录后来被删除。
2026-10-01 从两处来源恢复：

1. **本机会话记录**。按时间顺序重放其中记录的 2444 条文件操作（整文件写入、heredoc、纯文本替换、`sed -i`、复制），
   以 `e2b41c3` 的文件树为起点，跳过失败的操作。
2. **论文仓库历史中的打包副本**（`DAES_Special_Issue` 提交 `1e48d62`，2026-09-12 的 HIL_SAR 打包）。
   `bundle_copies/PROVENANCE.txt` 列出取用文件的 SHA-256 与原路径。

重放的可靠性：有独立打包副本的 9 个文件（`hil_report.py`、`rev_report.py`、`make_hil_replay_data.py`、
`attack_window.py`、`detector_ablation.py`、`detector_eval_unified.py`、`quantise_unified.py`、
`make_board_components.py`、`hls4ml_sweep.py`）重放结果与副本逐字节相同，其中两个经历了几十次记录在案的修改。

## 各文件状态

| 文件 | 来源 | 状态 |
|---|---|---|
| `HLS_PRJ/mpcc/mpcc_hls.cpp`、`HLS_PRJ/mpcc_r/mpcc_r_hls.cpp`（`i_ref` 符号） | 重放 | 完整；重建后的实现资源与论文资源表逐项相同 |
| `Vivado_PRJ/MPCC_R/build_bd.tcl` | 重放 | 完整（仅注释行） |
| `PS_notebook/{ps_server_mpcc_r.py, ddr_replay_mpcc_r.py, rt_loop_mpcc_r.c, rt_loop_det.c, rt_sched.c, pwr_loop.c, pmbus_sample.py}` | 重放 | 完整；语法检查通过，板上运行未重新验证 |
| `PS_notebook/{libs/mpcc_r_overlay.py, board_selftest_mpcc_r.py, x86_pl_emulator.py}` | 重放 | 完整 |
| `PS_notebook/cpu_partition/*` | 重放；`rt_sched_cpu.cpp` 与打包副本相同 | 完整 |
| `EMI_DET_FPGA/scripts/` 中 7 个有打包副本的脚本 | 重放 | 与打包副本逐字节相同 |
| `EMI_DET_FPGA/scripts/{coordinated.py, export_residual.py, make_paper_assets.py}` | 重放 | 全部操作重放成功，无独立副本；`make_paper_assets.py` 的仓库根路径改为相对路径 |
| `Simulation/PV_MEV/{PV_MEV.slx, run_injection.m, init_paras.m, config.csv}`、`docs/HIL_TEST_PLAN.md` | 打包副本 | 最终版（v6） |
| `Simulation/PV_MEV/{build_hil.m, hil_tcp.m, tests.csv}` | 重放 | 完整 |
| `Simulation/PV_MEV/build_supp.m` | 重放 | 2026-09-07 的一处修改未能重放，可能不是最终版；模型本身已含它所做的改动 |
| `incomplete/supp_report.py` | 重放 | 不完整（`v6map` 相关的两处修改未能重放），未放回原位 |

最终版仿真工程的验证（MATLAB R2025a）：模型可加载、可编译，无未解析的库链接；重新生成 `MPCC_R6` 基线快照并运行
`E-DC-01b`，记分卡与论文所用记录逐位相同（功率保持 100 %、母线偏差 0.083051485280464 V、THD50 2.79127523344664 % → 2.72897951886657 %、无闭锁）。

## 本目录内容

- `bundle_copies/`：打包说明、v6 数字溯源表、板上测量汇总（并发调度三种划分、延迟、功耗、HIL 等价性）。
  完整的 40 万行控制拍轨迹（10.7 MB）留在论文仓库历史 `figures/compact/hardware_tables/data/rt_sched_mpcc.csv`。
- `session_scripts/`：当时用过的一次性脚本，仅作记录：`hls/`（原始 HLS Tcl 与导出脚本，现由 `HLS_PRJ/build_hls.tcl` 取代）、
  `matlab/`（对模型逐步施加修改的 `apply_*.m` / `fix_*.m`，含 M10 / M11 / M14、残差检测器、保持掩码）、
  `board/`（批量运行与换 bit 的脚本）。其中的 `<RL4EV>`、`<SCRATCH>` 是原绝对路径的占位符。
- `incomplete/`：未能完整恢复的文件。

## 未能恢复

运行快照（`results/emi/snapshots/`，由 `run_injection('baseline', ...)` 重新生成）、仿真原始结果与板上日志、
`results/emi/holdmasks.mat`（保持掩码）、最终版之后改动过的 `MyLibrary.slx`（当前库可正常编译运行基准用例）、
以及论文第四版的 LaTeX 工程。
