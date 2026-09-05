# HIL 联调测试计划：MPCC_R 与 EMI 检测 / 谐波估计 IP 上 ZCU104

2026-09-05 起草。承接 `RESILIENT_MPCC_AND_OFFLOAD_PLAN.md`（§8 为 SIL 结果与 FPGA 构建结果）与 `EMI_DETECTION_PHASES_2-4_PLAN.md` §4。目标：把已实现的四个 PL IP（`mpcc_r_hls`、`emi_feat_hls`、`emi_detector_axi`、`harmonic_estimator_axi`，`Vivado_PRJ/MPCC_R/out/mpcc_r.bit`）接进 PV_MEV 闭环，证明 (a) 板上判决与占空比同 SIL 逐周期 / 逐拍一致，(b) PL 内延迟满足实时预算，(c) 韧性结论（§8.1）在板上复现。**上板动作等指令；本文件先把方案、数据与预期写死，H0 到 H1 的 x86 部分不需要板子即可开始。**

---

## 1 现状与接口

| 项 | 内容 |
|---|---|
| 板 | ZCU104（xczu7ev-ffvc1156-2-e），PYNQ 3.x，以太网 134.226.86.100（现有 `mpcc_hil.ipynb` 用此地址），MATLAB 主机同网段 |
| 已验证的 HIL 通路 | `PS_notebook/mpcc_hil.ipynb`：MATLAB 每控制拍把 14 个 little-endian `single` 发到 5010，PS 调 `mpcc_hls` 后把 1 个 `single`（D）回 5011；Simulink 侧 `PFC Control/HIL TCP Send1 / Receive1`（instrumentlib TCP/IP，Ts_Control，超时 10 s），`ENABLE_HIL = 1` 时 `Switch3` 用 HIL 的 D |
| 新 overlay | `PS_notebook/hardware/mpcc_r.bit / .hwh`；驱动 `PS_notebook/libs/mpcc_r_overlay.py`（按 hwh 寄存器名访问，四个 IP 各带 ap_start→ap_done 计时）；自检 `PS_notebook/board_selftest_mpcc_r.py` |
| IP 接口 | `mpcc_r_hls`：14 个 MPCC 输入 + flags、amp_iac、mask、t_ramp → D、dbg[6]。`emi_feat_hls`：buf[200×12] + reset → feat[48]。`emi_detector_axi`：feat[48] + reset → logit[5]、amp[5]、flags（持续 2 周期 + 滞回在 IP 内）。`harmonic_estimator_axi`：wave[80] → enc[8]、peak（legacy 7 维在 PS 解码） |
| 地址 | 0xA000_0000 GPIO，0xA001_0000 mpcc_r，0xA002_0000 emi_feat，0xA003_0000 detector，0xA004_0000 estimator，0xA005_0000 axi_timer |
| HLS 综合延迟（100 MHz） | mpcc_r 0.7 到 2.6 µs；emi_feat 24 µs；detector 2.6 µs；estimator 7.6 µs |
| SIL 参照 | `results/emi/scorecard.csv` 中 MPCC_R / MPCC_D_H1 各 13 行，`results/emi/ts/<case>_<variant>_det.csv`（逐周期特征、logit、标志、幅值、Mitigation 状态），`ts/<case>_<variant>.csv`（10 kHz 波形含 D） |

## 2 测试架构

```
Simulink PV_MEV (MATLAB 主机)                  PS (PYNQ, Python)                         PL
 PFC Control ─ 每拍 (50 µs):  18 single ──TCP 5010──► mpcc_r 帧解析 ──AXI-Lite──► mpcc_r_hls ──► D ──TCP 5011──► Switch3
 EMI Detector ─ 每周期 (20 ms): 2400 single ──TCP 5020──► emi_feat_hls ─► emi_detector_axi ─► [5 logit, 5 amp, flags] ──TCP 5021──► emi_decide(HIL)
 One Cycle Model ─ 每 5 ms: 80 single ──TCP 5030──► harmonic_estimator_axi ─► enc[8], peak ─► PS 解码 legacy[7] ──TCP 5031──► model_1_amp/phase
```

- 三条 TCP 通路相互独立，可以单独启用（`ENABLE_HIL`、`ENABLE_HIL_DET`、`ENABLE_HIL_EST` 三个开关），不启用的通路保持 SIL 路径，便于逐条对照。
- 估计器在 SIL 里是 4 kHz 滑动窗；HIL 首版保持 4 kHz 逐样本（`build_hil.m` 的接收块采样时间同 SIL，TCP 帧率 4 kHz，仿真墙钟约 ×3），等价性比较不需要对照变种；若墙钟不可接受，改为 5 ms 抽稀并在 SIL 侧加 `MPCC_D_H1_5ms` 对照。
- MPCC_R 帧在原 14 个之后追加 flags、amp_iac、mask、t_ramp 四个 single（flags 与 mask 按整数值传），PS 侧解析为 `mpcc_r_overlay.mpcc_r(frame[:14], int(flags), amp_iac, int(mask), t_ramp)`。M0 / M5（母线与充电级校正）留在 Simulink 侧（它们属于外环与充电控制器，见 §4.2 目标架构），板上 IP 只做内环的 M2 / M3 / M4 / M7。
- 实时性不靠 TCP 证明：PL 延迟由 `axi_timer` 与各 IP 的 ap_done 计数给出，另用 DDR 重放（把 SIL 记录的逐周期缓冲与逐拍帧放进 PS 内存，PS 以定时器节拍连续驱动 PL，不经 TCP）测吞吐与抖动。

## 3 阶段与实验方案

| 阶段 | 内容 | 需要板子 | 预计机时 |
|---|---|---|---|
| H0 x86 回环 | 用 Python 在 MATLAB 主机上起三个"伪 PS"服务器（`PS_notebook/x86_pl_emulator.py`，已写：mpcc_r 用 float32 参考模型、检测器与估计器用位精确 ONNX），Simulink 三条 TCP 通路全开跑 P1 的 7 条用例 × MPCC_R；验证帧格式、时序对齐、开关逻辑，得到"TCP 路径本身"的等价性基线 | 否 | 7 次 × 约 8 min |
| H1 板级自检 | `board_selftest_mpcc_r.py`：四个 IP 用 csim 向量自检；每个 IP 200 次调用的 PS 侧延迟 | 是 | 10 min |
| H2 MPCC_R 内环 HIL | `ENABLE_HIL = 1`：E-DC-01b、E-AC-01b、E-AC-02b、E-BAT-02b 与基线（无注入）共 5 次 × {MPCC_D_H1（flags 恒 0）, MPCC_R}；对照 SIL 的 D 序列与记分卡 | 是 | 10 次 × 约 9 min |
| H3 检测器 HIL | `ENABLE_HIL_DET = 1`（其余 SIL）：13 用例 × MPCC_D_H1（检测器对它是纯观测，最干净的逐周期对照） | 是 | 13 次 |
| H4 估计器 HIL | `ENABLE_HIL_EST = 1`：基线 + E-AC-01b + E-DC-01b × MPCC_D_H1 | 是 | 3 次 |
| H5 全链路 HIL | 三条通路全开：P1 的 7 条用例 + 随机 3 次（seeds 301 到 303）× MPCC_R；这是韧性结论的板上复现 | 是 | 10 次 |
| H6 实时性 | DDR 重放：从 SIL 记录导出 E-DC-01b 的 35 个周期缓冲、560 个估计窗、14 000 个控制拍帧；PS 定时驱动，读 PL 计数；1000 帧延迟分布；连续 20 s 无丢帧检查 | 是 | 30 min |
| H7 资源与功耗 | `report_utilization -hierarchical`（已有）、`report_power`；板上 PL 功耗用 PYNQ 的 PMBus 读数（ZCU104 支持） | 是 | 15 min |

Simulink 侧需要的改动（脚本已写，待应用）：`build_hil.m` 在 `EMI Detector` 与 `One Cycle Model Prediction` 内各加一对 TCP Send / Receive 与开关（与现有 `Switch3` 同款），`init_paras` 增加 `ENABLE_HIL_DET`、`ENABLE_HIL_EST`、`HIL_HOST`；`run_injection` 增加 `opts.hil`（选择开关组合、记录往返时间）与 `'hil'` 汇报模式（读 `<run>_det.csv` 与 SIL 同名文件做逐周期比较）。

## 4 判据与预期数据

### 4.1 功能等价（H0 到 H5）

| 量 | 比较对象 | 判据 | 预期 |
|---|---|---|---|
| D 序列（mpcc_r） | HIL 的 D 与 SIL 的 D，逐拍 | max \|ΔD\| ≤ 1e-5（float 帧往返无损，IP 与 C 参考逐位相同） | ≤ 2e-6，来自 MATLAB 侧 single 转换 |
| 检测器 logit | PL 与 Simulink 记录的 raw01..05，逐周期 | max \|Δlogit\| < 0.05 | ≈ 5e-6（csim 数值） |
| 检测器标志字 | PL flags 与 SIL chan_1..5，逐周期 | 不一致周期 ≤ 2 / 用例（只允许出现在特征值贴近阈值的周期） | 0 到 1 |
| 检测延迟 | 首次置位周期 | 与 SIL 相同（中位 2 周期） | 2 周期 |
| 估计器 enc | PL enc 与 ONNX | ≤ 2 LSB（0.0625） | 0（csim 逐值相同） |
| 记分卡 | H5 的 MPCC_R 与 SIL MPCC_R | 功率保持、母线偏差、THD50 上升逐用例差 ≤ 1%、1 V、0.2 pp；触发用例集合相同 | 与 §8.1 表相同 |
| TCP 往返 | 每帧 | 记录中位 / p99；不作为通过判据 | 中位 1 到 2 ms，p99 < 10 ms（现有 MPCC HIL 经验） |

### 4.2 实时性（H6）

| 量 | 测法 | 预算 | 预期 |
|---|---|---|---|
| mpcc_r 单拍 | ap_start → ap_done（PL 计数） | < 50 µs（20 kHz），目标 < 10 µs | 0.7 到 2.6 µs |
| 检测器每周期（特征 + 判决） | emi_feat + detector 串联 | < 250 µs | 24 + 2.6 ≈ 27 µs |
| 估计器每窗 | ap_done | < 250 µs（4 kHz 每样本一次时 < 250 µs；5 ms 更新时更宽裕） | 7.6 µs |
| PS 侧调用开销 | `mpcc_r_overlay` 计时（含 AXI-Lite 读写） | 每拍 < 50 µs 才能不靠 DMA 跑 20 kHz | mpcc_r 约 15 到 25 µs（18 写 + 7 读）；检测器约 1 到 2 ms（2400 个缓冲字的 AXI-Lite 写是瓶颈，仍远小于 20 ms 周期）；估计器约 60 µs |
| 抖动 | 1000 帧延迟标准差 / 均值 | < 5% | PL 侧 0（固定延迟）；PS 侧受 Linux 调度影响，预计 5 到 20% |
| 吞吐 | 20 s 连续重放 | 0 丢帧 / 丢拍 | 0 |
| 端到端（TCP 路径） | MATLAB 发帧到收到 D | 只报告，不作判据 | 1 到 3 ms |

结论形式：PL 内每控制拍 < 3 µs、每检测周期 < 30 µs、每估计窗 < 8 µs，均比 20 kHz / 50 Hz / 4 kHz 的节拍低两个数量级；不靠 TCP 的 DDR 重放证明 PL 能以真实节拍持续运行；TCP 只证明功能等价。若 PS 侧 AXI-Lite 写缓冲的 1 到 2 ms 成为问题（例如把检测周期缩到 10 ms），下一版用 AXI DMA 送缓冲。

### 4.3 资源（H7）

已从实现报告得到：LUT 80.1k（34.8%）、FF 71.3k（15.5%）、BRAM 70（22%）、DSP 803（46%），时序满足；分 IP 数字见 `RESILIENT_MPCC_AND_OFFLOAD_PLAN.md` §8.3。板上补 PL 功耗（预期 1 到 2 W）。

## 5 运行矩阵与产出

| 产物 | 路径 |
|---|---|
| x86 回环与 HIL 记分卡 | `results/emi/hil/scorecard_hil.csv`（与 `scorecard.csv` 同格式，另加 `hil_mode`、`tcp_rtt_median_ms`、`tcp_rtt_p99_ms`） |
| 逐周期 / 逐拍等价性 | `EMI_DET_FPGA/runs/hil_report/`：`equivalence.csv`（每次运行：max ΔD、Δlogit、标志不一致周期数、enc 差）、`fig15_hil_vs_sil.png`（E-DC-01b：SIL 与 HIL 的 D、标志、母线叠画） |
| 实时性 | `runs/hil_report/latency.csv`、`fig16_latency_hist.png`（四个 IP 的 PL 延迟直方图与 PS 侧调用时间）、`fig17_latency_breakdown.png`（TCP / PS / PL 分解） |
| 资源功耗 | `Vivado_PRJ/MPCC_R/util_impl.rpt`、`timing_impl.rpt`、`power.rpt`、板上 PMBus 读数表 |
| 文档 | 本文件 §6 进度记录；阶段二至四计划 §4 的判据逐项打勾 |

机时合计：H0 约 1 h（无板），H1 到 H7 约 4 h 板机时 + 4 h MATLAB。

## 6 风险与对策

| 风险 | 对策 |
|---|---|
| PYNQ 的 `register_map` 不暴露数组寄存器偏移 | 驱动已有 hwh `registers` 回退；再不行用 HLS 生成的 `x<ip>_hw.h` 偏移表 |
| 检测器缓冲经 AXI-Lite 每周期 2400 次写太慢 | 预期 1 到 2 ms，仍在 20 ms 内；若 PS 侧 Python 循环超过 5 ms，改 numpy 批量 `mmio.array` 写或 DMA |
| TCP 阻塞使 Simulink 每拍等待 1 到 3 ms | 仿真已是离线（10 min / 仿真秒），只影响墙钟时间；用 H0 的 x86 回环先把帧格式跑通 |
| 板上 float 与主机 float 计算顺序不同 | mpcc_r 的 C 模型与 IP 已逐位相同；MATLAB 侧 single 转换差 ≤ 2e-6，判据留 1e-5 |
| 检测器在阈值附近的周期标志可能翻转 | 允许 ≤ 2 周期 / 用例，并记录该周期的 logit 距阈值 |
| 主机与板不在同一网段 / 板 IP 变化 | `HIL_HOST` 参数化；先 `ping` 与 5010 端口回环 |

## 7 进度记录

| 日期 | 事项 | 结果 |
|---|---|---|
| 2026-09-05 | 计划起草；bitstream、驱动、自检脚本就绪 | 等上板指令 |
| 2026-09-05 14:10 | H0 准备：`PS_notebook/x86_pl_emulator.py`（三条 TCP 通路的 PS + PL 替身）写好并离线校验：估计器路径与 IP 参考向量逐值相同；检测器路径与参考 logit 的差只出现在运行起始周期（差分特征状态）；mpcc_r 路径与双精度参考差 ≤ 0.04，全部出现在电流过零点附近（`ui_safe` 除法的 float32 与 double 差，IP 本身是 float32）。`Simulation/PV_MEV/build_hil.m`（检测器 / 估计器 TCP 开关、MPCC_R 帧扩到 18 值）与 `init_paras` 的 `ENABLE_HIL_DET / ENABLE_HIL_EST / HIL_HOST` 写好，**未应用到模型**（应用会改结构、需重做快照，等 SIL 随机运行结束后再做） | 待应用 |
