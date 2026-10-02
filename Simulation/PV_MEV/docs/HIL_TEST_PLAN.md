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
| 2026-09-05 17:30 | 上板：ZCU104（PYNQ 3.0.1，Linux 5.15，2 GB）SSH / Jupyter 可达；bit、驱动、自检脚本、csim 向量复制到 `/home/xilinx/mpcc_r/` | 驱动修两处：PYNQ 3 的寄存器表来自 `ip_dict[ip]["registers"]`（数组参数名为 `Memory_<arg>`），以及 `mmio.array` 的 numpy 切片拷贝在 AXI-Lite 窗口上触发 SIGBUS（AArch64 memcpy 的非对齐 16 字节访问），改为逐字 32 位访问 |
| 2026-09-05 18:50 | **H1 板级自检通过**（`EMI_DET_FPGA/runs/hil_report/selftest_h1.log`） | emi_feat 100 周期相对误差 ≤ 1.1e-2（容差内 0 超限）；detector 200 周期 max Δlogit 4.8e-6、标志字 0 不一致；estimator 200 窗 Δenc = 0；mpcc_r 800 拍与 float32 参考相对差 ≤ 1e-7（判据改为相对：电流过零点未饱和的 D ≈ 5e5，一个 ulp 就是 0.03）。PS 侧 ap_start→ap_done（Python 轮询）：mpcc_r 22 µs、feat 53 µs、det 22 µs、est 36 µs |
| 2026-09-05 19:05 | **H6 实时性 + H7 功耗**（DDR 重放 E-DC-01b 记录：13 998 拍、34 周期缓冲、2721 窗；`runs/hil_report/h6_run1/`、`latency.csv`、fig16 / fig17） | PL：axi_timer 测 mpcc_r ap_start→ap_done 2.4 µs（中位 2.6，max 2.9，与综合 0.7 到 2.6 µs 一致）。PS 用 C（`PS_notebook/rt_loop_mpcc_r.c`，mmap /dev/mem）：每拍 5.4 µs（18 个寄存器全写）/ 3.7 µs（只写变化的寄存器），**20 kHz 连续 20 s 400 000 拍**，普通优先级下迟到 63 / 超一拍 29（Linux 抢占，max 25 µs），`chrt -f` 反而因 RT 节流迟到 2 万拍。PS 用 Python（PYNQ mmio）：mpcc_r 每拍 65 µs（20 kHz 全部迟到，不可用）；检测器每周期 3.7 ms（2400 字缓冲写 3.5 ms）50 Hz 0 迟到；估计器每窗 144 µs，4 kHz 80 000 窗迟到 8、丢 0。功耗（PMBus）：INT 轨 1.75 W（bit 已载、空闲）→ 2.0 W（三路满负荷），12 V 输入 11.2 W 整板 |
| 2026-09-05 19:10 | `build_hil.m` 应用到模型（修：instrumentlib 块路径 `TCP//IP Send`；det_chan / det_amp 是 20 ms 信号，加 Rate Transition 与 single 转换后再进帧 Mux）；`init_paras` 经 `HIL` 结构体传开关；`run_injection` 增加 `opts.hil`（mpcc / det / est / host / dir） | 两个发现：(1) instrumentlib 块的 Host 是字面量，不能写变量名，`prepare` 在运行时把 `HIL_HOST` 写入块参数；(2) **注释掉 TCP 块会改变模型结构、使 ModelOperatingPoint 快照失效**，因此有 HIL 目标时六个 TCP 块全部保持有效（开关只是 Constant 值），并用同一结构另取 `<variant>_hil.mat` 快照（开关全 0，物理状态与 SIL 快照一致：MPCC_R_hil 经 x86 模拟器 399.9 V / 6.903 kW / THD50 2.82%，与 SIL 快照相同）。SIL 快照（MPCC_R、MPCC_D_H1）在新模型上重做，指标不变 |
| 2026-09-05 19:40 | 板端 PS 服务 `PS_notebook/ps_server_mpcc_r.py`（三条通路各一线程、逐帧日志、运行结束按需重载 bit）；修一处：发送端连上而接收端未连（Simulink 初始化失败）会把通路卡死，改为带超时的成对 accept | 板上 mpcc 通路每帧 PS 服务 0.59 ms（Python），TCP 帧间隔由仿真步速决定（约 27 ms）；H0（x86，P1 × MPCC_R）与板端 H2 / H3 / H4 批次启动 |
| 2026-09-05 19:50 | 首批 HIL 运行全部在第一拍失败：`instrument.system.TCPIPSend.stepImpl` "Dot indexing is not supported"——instrumentlib 的 TCP System object 从 ModelOperatingPoint 恢复后丢失客户端句柄（`TCPIPObj` 不再是对象），x86 与板端一样 | **改为 `build_hil('v2')`**：每条通路一个 MATLAB Function 块，`coder.extrinsic` 调 `hil_tcp.m`（持久 `tcpclient` 在模型之外；开关 `ENABLE_HIL*` 与 `HIL_HOST` 从 base 读；关时返回零、不连网）。结构对 SIL / HIL 相同，不再注释块、不再需要 `_hil` 快照；`run_injection` 每次运行前后 `hil_tcp('reset')`，并把每通路帧数 / 往返均值 / 最大值写进记分卡（`tcp_<path>_rtt_mean_ms` 等）。本机回环单元测试：mpcc 4.0 ms / 帧、估计器 2.0 ms / 帧（MATLAB tcpclient 的读延迟，离线仿真可接受）。MPCC_R / MPCC_D_H1 快照按 v2 结构重做 |
| 2026-09-05 20:20 | 首批等价结果（E-DC-01b） | 板端检测器通路（H3，MPCC_D_H1）：D 逐拍 max Δ = 0、标志字 0 不一致、幅值差 4.9e-4、记分卡逐位相同；板端 mpcc 通路（H2，MPCC_D_H1）：14 000 拍中 1 拍 ΔD = 3.1e-5、其余 ≤ 1e-5、母线轨迹 Δ = 0、记分卡逐位相同；x86 全链路（H0，MPCC_R）：功率 100% / 母线 +0.110 V（SIL +0.111）/ THD50 3.257%（SIL 3.250）、检出周期相同，但 D 逐拍差达 1.0（电流过零处饱和方向翻转）且从 0.6 s 起 ~半数拍 > 1e-5——全链路的特征流水线（Python / PL 特征 vs Simulink emi_features，相对差 ~1e-3）改变幅值估计，因此全链路只能用记分卡级判据（§4.1 最后一行），逐拍判据只适用于单通路 |
| 2026-09-05 20:30 | **HIL 发现 IP 缺陷**：x86 全链路 E-DC-01c（+100 V）MPCC_R 母线 +90.7 V、THD 15.5%、OV 触发（SIL：−0.5 V、无触发）；对照逐周期记录，分歧在 0.72 s 即检测前——外环把 Iref 压到 −100 A 时，Simulink `D_predict` 保留符号（负参考 → D → 0），而 `mpcc_hls` / `mpcc_r_hls` 用 `line_sign * |i_ref|`（负参考被当作 +100 A 满功率升压） | 修 `HLS_PRJ/mpcc_r/mpcc_r_hls.cpp`、`HLS_PRJ/mpcc/mpcc_hls.cpp`（`i_ref_signed = line_sign * i_ref`）、`x86_pl_emulator.py` 与自检参考；mpcc_r 重新 csim / csynth / 导出，Vivado 重建 bit（20:33 启动）。已有板端 H2 / H3 / H4 结果不受影响（这些用例 Iref 不为负）；H5 与 E-DC-01c 类用例等新 bit |
| 2026-09-05 21:10 | **H2 完成**（板端 mpcc 通路，E-DC-01b / E-AC-01b / E-AC-02b / E-BAT-02b × {MPCC_D_H1, MPCC_R}，`results/emi/hil_mpcc/`，`runs/hil_report/mpcc/equivalence.csv`） | 记分卡对 SIL：功率保持差 0、母线差 ≤ 0.005 V、THD50 差 ≤ 0.02 pp、触发集合相同（全 0）；检出周期相同。逐拍：IP 走恒等路径的 6 次（MPCC_D_H1 全部、MPCC_R 的 E-DC-01b / E-BAT-02b）14 000 拍中 1 到 2 拍 ΔD ≤ 4e-5、其余 0、母线轨迹 Δ = 0；M2 / M4 在 IP 内生效的 2 次（MPCC_R E-AC-01b / E-AC-02b）ΔD 达 1.0（过零饱和翻转）、1951 到 3694 拍 > 1e-5、母线 Δ ≤ 0.2 V——IP 的 float32 前馈重构 / 相量保持与 Simulink Mitigation 的 double 计算差 ~1e-7 经 PWM 放大，记分卡级仍等价。TCP：每次 14 001 帧，往返均值 1.9 到 2.1 ms、最大约 210 ms（每次运行一次，连接建立）；仿真墙钟 +30 s（+8%）。x86 修正后 E-DC-01c × MPCC_R：母线 −0.5 V、功率 100%、THD50 3.64%、无触发，与 SIL 一致；新 bit（i_ref 符号修正）20:57 生成，时序满足，LUT 80.1k 不变，待 H3 结束后上板 |
| 2026-09-05 21:15 | **H0 完成**（x86 回环三路全开，P1 7 用例 × MPCC_R，E-DC-01c 用修正后的参考重跑；`results/emi/hil_x86/`，`runs/hil_report/x86/`） | 记分卡对 SIL：功率保持差 0（7 / 7）、母线差 ≤ 0.003 V、THD50 差 ≤ 0.02 pp、触发集合相同（E-DC-02b 检测前 OV 两边都有）、检出周期全部相同（0.74 / 0.76 s）。逐拍：E-AC-01a / E-BAT-01b / E-BAT-02b / E-DC-01c 与 SIL 逐拍相同（1 拍 ≤ 4e-5）；E-DC-01b / E-DC-02b / E-AC-02b 从检出后分歧（幅值头输出差 0.02 到 0.03 → M0 校正量差、M4 相量保持时刻差），母线轨迹差 ≤ 0.28 V。TCP 往返（MATLAB tcpclient，本机回环）：mpcc 1.0 到 1.3 ms、检测器 2.0 到 2.5 ms、估计器 1.7 到 2.0 ms；每次 14 001 + 36 + 2801 帧，墙钟 404 到 438 s（SIL 约 390 s） |
| 2026-09-05 21:40 | **H3 完成**（板端检测器通路，13 用例 × MPCC_D_H1，`results/emi/hil_det/`，`runs/hil_report/det/`）；**H4 完成**（板端估计器通路，E-AC-01b / E-DC-01b × MPCC_D_H1，`hil_est/`） | H3：13 / 13 用例 D 逐拍与 SIL 完全相同（max ΔD = 0）、母线轨迹相同、记分卡与触发（E-BAT-01n BOC、E-BAT-02c、E-DC-02b OV）逐位相同；板上标志字与 Simulink 判决 13 × 36 周期 0 不一致；检出周期全部相同；板上 logit 对 SIL ONNX：第 2 周期起 max Δ 0.019 到 0.034（< 0.05），第 1 周期 0.203（复位周期，差分特征从零状态起算，与 H0 准备时的离线校验一致）；板上幅值对 SIL ≤ 2.6e-3（归一化单位）。TCP 每周期 5.7 到 6.6 ms（2400 值帧 + PS 侧 4 ms 缓冲写）。H4：两次 D 逐拍与 SIL 完全相同（板上 enc 与 ONNX 逐值相同 → 谐波补偿相同），TCP 每窗 2.0 到 2.1 ms、2801 窗。新 bit 21:37 上板：自检再次 PASS（mpcc_r 与保号参考相对差 ≤ 1e-7），H5 启动 |
| 2026-09-05 22:50 | **H5 完成**（板端三路全开，P1 7 用例 + 随机种子 301 到 303 × MPCC_R，修正后的 bit；`results/emi/hil_full/`（`dataset/` 为随机运行），`runs/hil_report/full/`、`full_random/`，fig15） | 记分卡对 SIL：P1 7 / 7 功率保持差 0、母线差 ≤ 0.003 V、THD50 差 ≤ 0.02 pp、触发集合相同（E-DC-02b 检测前 OV）；E-DC-01c 在修正后的 IP 上母线 −0.5 V、功率 100%、无触发（修正前 x86 复现为 +90.7 V、OV）。随机 3 / 3：D0301 功率 101.46% / THD 3.934% / 触发 5，D0302 98.53% / −2.599 V / 3.065%，D0303 84.27% / +7.184 V / 3.160%，与 SIL 逐位相同。逐拍：E-AC-01a / E-BAT-01b / E-BAT-02b / E-DC-01b / E-DC-01c、D0302 / D0303 与 SIL 逐拍相同（1 拍 ≤ 4e-5）；E-AC-02b（M4 相量保持）、E-DC-02b、D0301 从检出后分歧、母线轨迹差 ≤ 0.25 V。板上 logit 对 SIL ONNX（轨迹相同的运行）：除复位周期外绝大多数周期 Δ = 0，个别周期 0.06 到 0.135（过零采样归属，与 csim 已知差异同源），标志 0 不一致 |

## 8 结果汇总（2026-09-05）

| 阶段 | 运行 | 结论 |
|---|---|---|
| H1 自检 | 4 IP × 100 到 200 向量 | PASS（`runs/hil_report/selftest_h1.log`、`selftest_h1_ireffix.log`）：feat 相对误差 ≤ 1.1e-2（容差内）、detector Δlogit 4.8e-6 / 标志全等、estimator Δenc = 0、mpcc_r 相对差 ≤ 1e-7 |
| H0 x86 全链路 | 7 × MPCC_R | 记分卡级等价 7 / 7；逐拍相同 4 / 7 |
| H2 板端 mpcc | 4 用例 × 2 变种 | 记分卡级等价 8 / 8；逐拍相同 6 / 8（IP 恒等路径），M2 / M4 生效的 2 次母线差 ≤ 0.2 V |
| H3 板端检测器 | 13 × MPCC_D_H1 | D 逐拍完全相同 13 / 13；标志字 13 × 36 周期全等；logit Δ（第 2 周期起）≤ 0.034 |
| H4 板端估计器 | 2 × MPCC_D_H1 | D 逐拍完全相同 2 / 2（enc 与 ONNX 逐值相同） |
| H5 板端全链路 | 7 P1 + 3 随机 × MPCC_R | 记分卡级等价 10 / 10；逐拍相同 7 / 10 |
| H6 实时性 | DDR 重放 | PL：mpcc_r 2.4 µs / 拍（timer）；PS C 循环 3.7 到 5.4 µs / 拍，20 kHz 连续 20 s（迟到 0.016%）；Python 65 µs / 拍不满足 20 kHz；检测器 3.7 ms / 周期、估计器 144 µs / 窗满足 |
| H7 资源功耗 | 实现报告 + PMBus | LUT 80.1k（34.8%）、DSP 803（46%）、时序满足；INT 轨 1.75 W 空闲 → 2.0 W 满负荷 |

**判据对照（§4.1）**：D 序列 max |ΔD| ≤ 1e-5 —— 在 IP 恒等路径与检测器 / 估计器通路上成立（1 到 2 拍 ≤ 4e-5 是 float32 舍入，其余 0）；在 M2 / M4 或检测幅值参与内环的运行上不成立（float32 与 double 的 ~1e-7 差经 PWM 放大成 D 的饱和翻转），这类运行按记分卡判据（功率 ±1%、母线 1 V、THD 0.2 pp、触发集合）全部通过。检测器 logit < 0.05 在 H3 成立、在 H5 的个别周期超出（≤ 0.135，零交叉采样归属），标志字全等。检测延迟全部 2 周期、与 SIL 相同。TCP 往返只作记录：板端 mpcc 1.9 到 2.1 ms、检测器 5.7 到 6.6 ms、估计器 2.0 ms。

**HIL 发现的缺陷**：`mpcc_hls` / `mpcc_r_hls` 对电流参考取绝对值，与 Simulink `D_predict` 的保号语义不同，负参考（+100 V 母线量测阶跃后外环饱和）被当作满功率升压，母线冲到 OV；已修正并重建 bit（20:57），板上复验通过。SIL 中不可能发现（SIL 用的是 Simulink 的 D_predict）。

**改动清单**：`Simulation/PV_MEV/{build_hil.m, hil_tcp.m, init_paras.m, run_injection.m, PV_MEV.slx}`；`HLS_PRJ/{mpcc, mpcc_r}/*.cpp`（i_ref 符号）；`Vivado_PRJ/MPCC_R/{build_bd.tcl（注释）, out/, timing_impl.rpt, util_impl.rpt}`；`PS_notebook/{libs/mpcc_r_overlay.py, board_selftest_mpcc_r.py, ps_server_mpcc_r.py, ddr_replay_mpcc_r.py, rt_loop_mpcc_r.c, x86_pl_emulator.py, hardware/mpcc_r.bit/.hwh}`；`EMI_DET_FPGA/scripts/{hil_report.py, make_hil_replay_data.py}`；产物 `EMI_DET_FPGA/runs/hil_report/`（equivalence.csv 汇总、各阶段子目录、latency.csv、fig15 到 fig17、h6_run1/、pslogs/）与 `Simulation/PV_MEV/results/emi/hil_{x86,mpcc,det,est,full}/`。其他变种（CRPR、MPCC_P、MPCC_D、消融）的快照仍是 build_hil 之前的结构，再跑 SIL 前需 `run_injection('baseline', ...)` 重做。

## 9 论文补充实验（2026-09-06 起）

| 日期 | 事项 | 结果 |
|---|---|---|
| 2026-09-05 23:20 | 模型改动 `build_supp.m`（已应用、编译通过；快照全部重做）：(1) 注入形状 8 = 乘性增益（生成器加入真实量输入，`y_int = (1+amp)·y_real`，库块 `MyLibrary/Disturbance Injector` 改动覆盖 5 个链接实例）；(2) 措施位 M9 = 512：Vdc / Vbat 校正量经斜率限制（1000 / 200 V/s）引入与撤除（bumpless），变种 `MPCC_R_B`（掩码 949）；(3) `det_force = 2` oracle：标志由注入定义给出（`inj_channel/inj_shape/inj_t_on/inj_dwell` 常量输入到 Mitigation 与 chg_corr，噪声槽排除），变种 `MPCC_R_OR`、`MPCC_R_B_OR`。`tests.csv` 新增增益族 7 例（优先级 G）与幅值扫描 16 例（S）；`run_injection` 支持 `opts.op = 'cv'`（文件后缀 `_cv`）与任意优先级标签 | 待运行 |
| 2026-09-05 23:25 | 离线检测器分析 `EMI_DET_FPGA/scripts/detector_ablation.py` → `runs/detector_ablation/`（ablation.csv、confusion_matrix.csv、latency.csv、float_vs_quantised.csv、fig18）。数据 `cycles_v3_all`（308 次运行、11 263 周期），按运行分组 25% 测试，随机森林多输出，1% 注入前误报预算，2 周期持续 | 全 48 特征：通道集合完全正确 94.8%、任一通道 98.3%，延迟中位 1 周期（p90 1）、注入前误报 6 周期、良性运行 0 报警。特征组：仅功率平衡（6 维）75.9%，仅频谱（10 维）63.8%，两者合并 91.4%，仅时域统计（32 维）93.1%，去掉功率平衡 93.1%，去掉频谱 93.1%——三组互补，任一单组都达不到全集。单残差基线（同持续与预算）：功率比 10.3%、母线 / 充电级交叉校验 24.1%（只对 Vdc 链 87.5%）、Vbat 失配 20.7%（只对 Vbat 链）、电流直流分量 0%、母线误差 1.7%、Vac 均值 12.1%——单一残差只能覆盖它对应的通道且延迟 1 到 5.5 周期。量化代价（v5 训练报告）：float 与 HGQ2 量化在留出 52 / 56、阶段一 72 / 78 检出相同，注入前误报 25 vs 25（规则后），撤除后 49 vs 41 |
| 2026-09-05 23:30 | 增量 FPGA 代价 `runs/hil_report/incremental_cost.csv`（实现后分层报告） | MPCC-only（mpcc_r + 互连）LUT 11.9k（5.2%）、DSP 54；加检测（emi_feat + detector）+44.3k LUT（19.2%）、+36.8k FF、+23 RAMB36 + 12 RAMB18、+290 DSP（16.8%）；加谐波估计器 +24.0k LUT、+459 DSP（26.6%）；整体 80.1k LUT（34.8%）、803 DSP（46.5%） |
| 2026-09-05 23:50 | M9 首版（物理估计路径也限斜率 1000 V/s）在 E-DC-01b 上反而 OV：注入撤除后物理估计 dV 在 5 ms 内归零，而斜率限制让 30 V 的陈旧校正多留 50 ms，外环把真实母线抬到 463 V。**修正 M9 只对幅值头回退路径限斜率**（母线 500 V/s、电池 100 V/s），物理估计路径不变；MPCC_R_B 批次重启。增益路径验证通过：E-GN-01（Vdc 链 +10 %）MPCC_D_H1 真实母线 −36.4 V、功率保持、无触发 | 运行中 |
| 2026-09-06 05:30 | **补充 SIL 批次完成**（约 150 次运行，`results/emi/`：E-GN-*、E-SW-*、`*_cv`、`benign/`；报告 `EMI_DET_FPGA/scripts/supp_report.py` → `runs/supp_report/`：sweep_rows.csv、fig19、gain_family.csv、paired_MPCC_R_vs_*.csv、cv_vs_cc.csv、benign.csv） | 见下表 |

### 9.1 补充实验结果

**幅值扫描（fig19，MPCC_D_H1 vs MPCC_R，CC 段）**：Vdc 链 +20 到 +100 V：MPCC_D_H1 母线偏差随幅值线性下降到 −64 V、≥ 75 V 充电停止（THD 466 %）；MPCC_R 母线 |Δ| ≤ 0.5 V、功率 100 %，全部幅值；−50 V（真实 450 V）两者都 OC 触发。Vac 链 8 到 45 V：MPCC_D_H1 THD50 上升 0.4 到 8.0 pp 随幅值单调增加，MPCC_R 保持 ≤ 0（M2 前馈重构）。Iac 链：1 A 与 2.5 A **未检出**（检测下限在 2.5 到 5 A 之间），5 到 10 A 检出但 Iac 链无补偿（M3 有害已关），两者 THD 相同。Vbat 链：≥ 15 V 时 MPCC_D_H1 充电停止、母线 +46 V、THD 480 %，MPCC_R 功率 100 %、母线 −1 V，但仍 OC 触发（校正引入瞬态，oracle 下消失）。Ibat 链：两者相同（充电控制器决定，M6 关）。

**增益攻击族（7 例，检测器未用增益样本训练）**：全部 2 周期检出，通道归属含后果通道（如 Vdc 增益 → Vdc+Vbat+Ibat，由 Vdc 优先规则处理）。Vdc ±10 %：MPCC_D_H1 真实母线 −36 / +45 V（−10 % 时 OV 触发），MPCC_R 0.0 V。Vac +10 %、Iac ±20 %：两者功率与母线均正常，MPCC_R THD 略低。Vbat +5 %：MPCC_D_H1 充电停止（THD 481 %），MPCC_R 100 %（两者 OC 瞬态触发）。Ibat −20 %：两者 126 % 功率并 BOC（充电级）。

**oracle 标志（MPCC_R_OR）**：19 个用例中 MPCC_R 的 7 次触发（E-BAT-02c、E-DC-02b、E-MUL-01、E-GN-01b、E-GN-04、E-BAT-01n、E-SW 未含）在 oracle 下只剩 E-BAT-01n（充电控制器 BOC，与控制器无关）；功率与 THD 与检测驱动版相同、母线偏差 ≤ 0.1 V。结论：剩余失效全部是 2 周期检测延迟的代价，不是措施本身的上限；E-DC-02b 的"检测前 OV"随延迟消失。

**bumpless（MPCC_R_B，仅幅值头回退路径限斜率）**：消除 E-MUL-01、E-GN-04 的触发，但 E-DC-01c（充电停止 → 物理估计不可用 → 回退路径变慢）功率 67 %、母线 −30 V，E-BAT-02c 96 % 仍触发；其余用例与 MPCC_R 相同。MPCC_R_B_OR（bumpless + oracle）在 4 个触发用例上全部无触发。首版对物理估计路径也限斜率时 E-DC-01b 反而 OV（见上）。结论：平滑校正不是解，缩短检测延迟才是。

**CV 段（Voc 345 V，3.5 kW，13 用例 × 2）**：MPCC_D_H1 在 CV 段更脆弱——E-BAT-02b 从功率 49 % 变为充电停止（THD 479 %），E-DC-01b 从 64 % 变为 0.6 %（THD 96 %），E-MUL-01 从 61 % 变为 0.3 %；Vac 链 THD 上升约翻倍（+34 V：7.8 → 17.0 %）。MPCC_R 在 CV 段仍保住 Vdc / Vac / 多通道用例（功率 100 %、母线 ≤ 1.3 V），但 E-BAT-02c 降到 48 %（CV 下充电级校正的物理估计条件不满足），THD 整体高于 CC（基线本身 3.58 % vs 2.82 %）；检测器在 CV 段的通道归属更散（多标志），E-AC-02s（正交正弦）在 CV 未检出；CC 段的 3 次触发在 CV 段均未出现（电流更低）。

**良性扰动误报（12 类 × 2 变种，`benign/`）**：本地事件——充电电流阶跃 1 到 3 周期、Vref −20 V 4 周期（Iac 通道）、Vref +20 V 与 Vac / Iac 噪声 0、Vdc 噪声 1 周期；**电网工况变化——±10 % / −20 % 幅值阶跃与 ±0.5 Hz 频率偏移引起持续置位**（Vac 通道 34 / 35 周期，频率偏移还置 Iac 23 到 25 周期，+10 % 幅值还置 Vdc / Ibat）：检测器只在额定电网下训练，无法区分真实电网幅值 / 频率变化与 Vac 链偏置。误报对 MPCC_R 无害：功率 100 %、母线 ≤ 0.08 V、THD 与 MPCC_D_H1 相同或更低（M2 用 PLL 幅值重构，跟随真实电网）。改进方向：训练集加入电网工况变化，或加 PLL 幅值 / 频率一致性特征。

### 9.2 论文可用的新数据点

- 检测下限：Iac 链 2.5 到 5 A（其余通道最小幅值均检出）；增益攻击 7 / 7 检出（未训练形状）。
- 检测延迟的代价：oracle 消除 6 / 7 触发；bumpless 平滑无效甚至有害（E-DC-01c）。
- 工作点泛化：CV 段 MPCC_R 保住 Vdc / Vac / 多通道，电池电压链退化到 48 %。
- 误报边界：本地瞬态 ≤ 4 周期；电网工况变化持续误报但不改变控制结果。
- 特征互补（§9 表）、单残差基线、量化零代价、增量 FPGA 代价。

**未完成 / 限制**：MPCC_R_B、MPCC_R_OR 的增益用例各 6 / 7（E-GN-05 被中止），随机种子 312 / 313 的 MPCC_R_B 未跑（批次重排时取消）；CV 段只跑了 MPCC_D_H1 与 MPCC_R；电网变化用的是常量参数阶跃而非可编程源。
| 2026-09-06 09:20 | **补跑完成**：E-GN-05 × {MPCC_R_B, MPCC_R_OR}、随机 312 / 313 × MPCC_R_B、CV 段扩到 CRPR / MPCC_P / MPCC_D / MPCC_R_OR（快照 + 13 用例各）；`supp_report` 与 `make_paper_assets.py` 已按完整数据重生成 | oracle 对照 20 用例：MPCC_R 7 次触发 → oracle 2 次（E-BAT-01n、E-GN-05 都是充电控制器的 BOC，与 PFC 无关）。CV 段 13 用例均值（功率 / 母线 / THD / 触发）：CRPR 74.9 % / 64 V / 122 % / 6，MPCC_P 61.5 % / 23 V / 391 % / 1，MPCC_D 61.6 % / 23 V / 161 % / 1，MPCC_D_H1 61.6 % / 23 V / 160 % / 1，MPCC_R 96.0 % / 0.4 V / 8.0 % / 1，MPCC_R_OR 96.0 % / 0.2 V / 7.9 % / 0——CV 段所有无防护控制器都比 CC 段差，MPCC_R 仍保持 96 %（唯一损失 E-BAT-02c 48 %，oracle 下同样 48 %，是充电级校正在 CV 段的真实上限）。随机 D0312 / D0313 MPCC_R_B：见 dataset 目录 |
| 2026-09-06 09:25 | 电网源替换 `build_supp('grid')`：三相可编程电压源（120 kV，内阻抗移到串联 RL 支路）替代原三相源，快照用 VariationEntity = None，运行时由 `GRID` 结构体（entity / step / t0 / h5 / h7）设置幅值或频率阶跃与 5 / 7 次谐波注入（在 0.7 s 发生，注入前 0.6 到 0.7 s 为干净基线）；良性表新增 B-GRID-H5（5 次 3 %）与 B-GRID-H57（5 次 3 % + 7 次 2 %）。MPCC_R / MPCC_D_H1 快照重做后重跑 7 类电网良性用例 | 运行中 |
| 2026-09-06 11:00 | **可编程电网源良性用例完成**（7 类 × 2 变种，`results/emi/benign/`，取代 §9.1 中"参数阶跃"版本的电网行）。两处教训：(1) 可编程源的 VariationEntity / HarmonicGeneration 下拉项改变块内部结构，运行点只能部分加载（0.6 s 出现 92 A 冲击），因此快照里把它们冻结（Amplitude、谐波开、幅值 0），每次运行只改数值参数；(2) 模型 InitFcn 每次仿真都重跑 `init_paras` 并清空基工作区，直接 assignin 的电网变量被复位为 0（阶跃从未发生），改为经 `GRID` 结构体透传（同 INJ / HIL） | 幅值 −10 % / −20 % / +10 % 在 0.7 s 阶跃（基线 0.6 到 0.7 s 干净）：检测器 0.74 s 起持续置位 Vac（29 周期），+10 % 还置 Vdc / Ibat（MPCC_D_H1 70 周期，MPCC_R 48）；两种控制器功率 100 %、无触发、THD 与基线相当。5 次 3 % 与 5 + 7 次谐波注入：**0 误报**。频率 ±0.5 Hz（从运行起始）：−0.5 Hz 3 到 4 周期、+0.5 Hz 19 到 22 周期（Vac + Iac）；该两例的 THD50 指标（固定 50 Hz 傅里叶）失效，不作电能质量结论。合计 28 次良性运行、18 次有报警、304 / 980 周期，其中本地事件 ≤ 4 周期 |

**§9.1 良性段落更正**：以上表为准——电网幅值变化是持续误报源，背景谐波与本地事件不是；误报对 MPCC_R 无害的结论不变。

### 9.3 论文产出

`EMI_DET_FPGA/scripts/make_paper_assets.py` → `EMI_DET_FPGA/runs/paper_assets/`：`tables/T1..T11*.csv`（21 张表，`tables.md` 为 markdown 渲染）、`figures/`（17 张图：fig9 到 fig12b 韧性与随机、fig15 到 fig17 HIL 与实时性、fig18 检测器消融、fig19 幅值扫描、fig20 通道混淆、fig21 HIL 逐拍差、fig22 四控制器对比、fig23 良性误报、估计器 THD）、`README.md` 索引（每个文件的来源）。
| 2026-09-06 16:10 | 论文补充：斜坡斜率扫描 E-RP-250/500/2000/4000（V/s，加已有 1000）× {MPCC_D_H1, MPCC_R, MPCC_R_P1}；单周期持续变种 `MPCC_R_P1`（config 列 `det_persist` = 1，13 用例 + 良性集）；板端 C 语言检测器通路 `PS_notebook/rt_loop_det.c`；x86 上复现修正前 IP（`MPCC_ABS_IREF=1`，`results/emi/hil_x86_bug/`）；论文图 fig24 到 fig28（资源、oracle、PS 开销、期限、缺陷）与 TikZ 架构 / 检测链 / 时序 / 信任边界图（`paper/`） | 期限：MPCC_D_H1 全部触发（250 / 500 / 1000 V/s OV 于 171 / 90 / 41 ms，2000 / 4000 V/s OC 于 27 / 16 ms）；MPCC_R 250 / 500 V/s 无触发（首次置位 80 / 60 ms），1000 V/s 置位与 OV 同时（40 ms），≥ 2000 V/s OC 早于任何可能的置位；P1 把延迟减半（20 ms）但 1000 V/s 仍在 41 ms OV（积分器已饱和；oracle 0 ms 才能避免）。P1 在 13 用例上与 MPCC_R 指标相同（触发相同 4 次，恢复 66 → 62 ms），但良性集误报周期 139 → 205（13 次）且 ±0.5 Hz 频率偏移两例 OC 触发——单周期标志把 PLL 暂态期间的物理估计送进 M0 校正，破坏失效安全。板端 C 检测器通路每周期 369 µs（缓冲 311、特征 31、检测 27）对 Python 3.7 ms |

## 10 审稿修订（2026-09-07 起，DAES 大修意见 10 条）

### 10.1 新增实验与脚本

| 项 | 内容 | 产物 |
|---|---|---|
| 统一检测口径 | `EMI_DET_FPGA/scripts/detector_eval_unified.py`：RF teacher / MLP float / MLP 蒸馏 / 部署量化 ONNX / 联合六残差 logistic，同一判决规则（2 周期、0.6 迟滞、Vdc 优先）、同一阈值标定、三个测试集（hold-out 73 运行、基准 104 运行、随机 20 运行）；延迟定义：与攻击重叠的周期数（含判决周期），ms 为攻击起点到旗标 | `runs/detector_unified/unified.csv`, `runs_*.csv` |
| PS 并发调度 | `PS_notebook/rt_sched.c`：SCHED_FIFO 三线程（tick 50 µs / 估计器 250 µs / 检测 20 ms），20 s，记录释放抖动、IP 执行、服务、端到端、late/dropped | `runs/hil_report/h6_run1/rt_sched_summary.csv` |
| 功耗基线 | controller-only 位流 vs 完整位流，空闲 vs 运行（PMBus） | `h6_run1/power2.csv` |
| 固定延迟 oracle | MPCC_R_OR1/OR2/OR3（det_force 2.1/2.2/2.3）× 13 例 | scorecard 行 |
| 模型失配 | `build_supp('mismatch')` + `opts.mm`：chg_eff 0.95/0.90、Rint×1.5、L_chg×0.5 × {E-DC-01b, E-DC-01c, E-BAT-02b, E-BAT-02c} × MPCC_R；结果文件后缀 `_<tag>`，scorecard 新列 `mm` | scorecard |
| 频率良性重跑 | 49.5/50.5 Hz 稳态快照 `*_fm05/_fp05.mat`，B-GRID-FM05/FP05 × {MPCC_D_H1, MPCC_R, MPCC_R_P1} | benign/scorecard |
| M10 基线参考物理估计 | `apply_m10.m`（scratchpad）：M0/M5 的残差在无旗标时以 0.2 s 慢滤波跟踪（变化 <5 V / 3 V 才更新），旗标期间冻结并从估计中扣除；变体 MPCC_R_BR（mask 1461），13 例 + 失配 16 例 + 良性 12 例 | scorecard |
| 汇总 | `EMI_DET_FPGA/scripts/rev_report.py` → `runs/rev_report/*.csv`；`paper/make_tables_rev.py` → `paper/tables/t_*.tex` | |

### 10.2 已得结果（2026-09-07 夜）

- 部署量化检测器，104 基准运行：any 98.1 %，exact 38.5 %，superset 51.9 %，partial 7.7 %，miss 1.9 %（两例 E-BAT-02b 被 Vdc 优先规则压掉）；中位延迟 2 周期 / 40 ms，最大 120 ms；攻击前 520 周期零误报；逐周期精度 76.9 % / 召回 82.2 %；Ibat 精度仅 43.7 %（过度归因通道）。修订 2 的"94.8 % exact"实为 teacher 在"真集 ⊆ 旗标集"口径下的数字；同口径下部署模型为 90.4 %。
- 蒸馏换来零误报（float 普通标签 78 个攻击前误报周期 vs 蒸馏 0）；量化使 exact 由 67 % 降至 39 %（几乎全部变为 superset），any / 延迟 / 误报不变。联合残差基线 any 46 %（基准）/ 48 %（hold-out），只覆盖 Vdc、Vac 链。
- 并发调度：tick 服务中位 4.0 µs、p99 9.2 µs、最大 126 µs；late 124/400 001（310 ppm）、dropped 91（228 ppm），端到端最大 1 714 µs 全为释放抖动；估计器 1 次 late；检测 0。PL 计时"最大 122 µs"为 PS 抢占在 ap_done 轮询与计时器读取之间造成的观测值。
- 功耗：PL 核心轨 controller-only 1.50/1.50 W（空闲/运行），完整 1.75/2.00 W → 增量 0.25 W 静态、0.50 W 运行；12 V 输入增量 0.33/0.59 W。
- 功率保持绝对误差：11 个可补偿案例 MPCC_R 全部在 0.01 pp 内（MPCC_H 6 个）；E-BAT-01b/01n 各 −25.5 / +25.9 pp，所有控制器相同（Ibat 链不补偿）。
- 保护语义：监视器仅锁存首次越限（UV/OV/BOV 需持续 2 ms，OC/BOC 立即），不关 PWM；MPCC_R 的两处"100 % 且 OC"是校正瞬态（母线先跌 62 V，随后电流 >65 A 数个采样）后完全恢复。
- 无负载 THD 绝对值：E-DC-01c/E-BAT-02c 下三种 MPCC 基波仅数 mA、谐波 10–30 mA；PR 为基波 13–18 A、谐波 40–43 A。
- 初步失配结果（eff95，MPCC_R）：E-DC-01b 母线偏差 +21 V（5 % 损耗被当作 20 V 偏置补偿），E-DC-01c 锁存 OV → 促成 M10。

### 10.3 链结果（2026-09-08 凌晨，全部完成）

- 固定延迟 oracle（13 例）：功率保持在 0/1/2/3 周期延迟下完全相同；锁存越限 1/2/4/4（检测器 4）。E-DC-02b OV 与 E-MUL-01 OC 需 1 周期内旗标；E-BAT-02c OC 只有起点旗标能避免（延迟 ≥1 周期均在 116 ms 锁存，充电器已离开 CC）。检测器驱动变体与 2 周期 oracle 在锁存与母线均值上完全一致 → 通道归因不额外付出代价。
- 频率良性重跑（稳态快照）：三配置均无锁存；49.5 Hz 1 个误报周期（P1 为 5）；50.5 Hz 几乎每周期误报 Vac/Iac（200 样本窗不再整周期），功率 6.90 kW、母线 <0.1 V、MPCC_R THD 更低。修订 2 中"P1 导致频率跳闸"的说法撤回。
- 失配（MPCC_R）：Rint×1.5、L×0.5 与标称三位小数一致；η=0.95：母线案例偏差 21/20 V、E-DC-01c OV；E-BAT-02b 49 %、E-BAT-02c 5 %（+102 V，OV）；η=0.90 更差。
- M10（MPCC_R_BR，失配快照在失配对象上标定）：标称 13 例与 MPCC_R 完全一致，良性 12 例结果一致、误报 109 vs 117；η=0.95 母线案例 0.6/0.1 V、无锁存；η=0.90 5.9/−2.6 V、E-DC-01c 一次 OC；电池电压案例受检测器归因限制（交叉校验特征未做基线参考：失配下每个攻击前周期都出现 Vdc 误报，10 V Vbat 偏置在 η=0.95 下未被归因为 Vbat → 49 %；20 V 案例被校正但瞬态 +78 V 锁存 OV）。检测侧对应修正（特征基线参考 + 重训）列为后续工作。
- 论文 revision 3（38 页，无 pending）、回复信、源码包：`paper/hil_sar_draft.pdf`, `paper/response_letter.pdf`, `paper/hil_sar_rev3_src.zip`。未提交 git。

### 10.4 一致性复核（2026-09-08 上午）

审稿意见落实后做的全文/数据复核与修正：

- `supp_report.py` 与 `make_paper_assets.py` 增加 `mm` 过滤，失配运行不再进入标称主表（重算后除良性表与消融表外，其余主表逐字节不变，确认无污染）。
- 良性误报图改为三配置成对版本 `fig23b_benign_paired.png`（rev_report 生成），替换 9-6 的旧图；统一评估图与延迟 oracle 图重新拷贝（此前是中途版本）。
- 消融表补回五列逐通道召回（审稿次要意见 1），表注同步。
- 正文修正：良性段"任一持续判据下最多 4 个误报周期"限定为 2 周期判据（P1 在 B-CHG-05 为 14 周期）；良性 14 例 MPCC-R 与 MPCC-H 的一致性改为实测口径（功率完全相同、母线 ≤0.03 V、THD ≤0.02 pp）；两处校正瞬态过流补入实测峰值（E-BAT-02c 65.7 A、E-MUL-01 72.3 A，母线跌至 337/338 V）。
- 引用检查：Table 1–29、Figure 1–17 全部有定义与引用，无 `??`，无 pending。

## 11 第二轮审稿修订与 v4/v5 重排（2026-09-10）

### 11.1 补充实验（全部完成，脚本与数据）

| 项 | 内容 | 产物 |
|---|---|---|
| 协同攻击 | E-MUL-02（Vdc +50 V 与 Vbat +43 V = 50·D_dc，恒等式残差抵消）、E-MUL-03（Vbat +22 V，半抵消）× {MPCC_D_H1, MPCC_R, MPCC_R_OR} | `rev_report/coordinated_drift.csv` |
| 慢漂移 | E-RP-50 / E-RP-100（−100 V 斜坡，50 与 100 V/s，停留期内到 −15/−30 V）× {MPCC_D_H1, MPCC_R, MPCC_R_BR} | 同上 |
| 强制误报 | MPCC_R_ON（五通道旗标全程强制置位）× 14 个良性扰动，含 49.5/50.5 Hz 专用快照 | `rev_report/benign_forced.csv` |
| 同一划分量化对比 | `scripts/quantise_unified.py`：seed-0 划分上蒸馏浮点 MLP 与其 HGQ 副本（权重 2–7 b、激活 4–7 b）同规则标定阈值 | `runs/detector_unified/unified_samesplit*.csv` |
| 部署模型阈值重标定 | 部署 ONNX 在统一规则下重标定阈值：exact 38.5 → 45.2 %，any 98.1 → 96.2 % | 见 FACTS.md |
| 原生 CPU 基线 | 同一 HLS C++（特征核、float32 网络、mpcc_r tick）g++ -O2 编译到板上 A53，绑核 SCHED_FIFO | `rev_report/cpu_baseline.txt` |
| 调度抖动注入 | 模型新增 `tick_hold`（D_predict 之后，按 HOLDMASK 保持上一拍占空比）；掩码来自实测 rt_sched 的 124 个迟到 tick（最长 37 连续 = 1.85 ms），对齐到攻击起点 / 修正生效点 / 原样 | `results/emi/holdmasks.mat`，scorecard `hold` 列 |
| 攻击窗全程指标 | 0.7–1.0 s 能量缺额、峰值母线偏差、越限持续时间、联合成功（功率 ±1 pp 且无锁存） | `rev_report/attack_window_metrics.csv` |

### 11.2 关键结论

- 时间线统一：旗标在第二个受攻周期末决出（40 ms），经速率转换在下一周期边界生效（60 ms）；部署配置的修正起点等于 3 周期 oracle。
- 联合成功 5/8/11（H/R/oracle-0），能量缺额 7.18/2.44/0.54 kJ，越限时长 294/65/43 ms。
- 同一划分下量化对 exact-set 影响 −12…+3 pp；部署检查点的 38.5 % 属检查点本身（阈值重标定后 45.2 %）。
- 强制误报：14 例功率全部不变、母线 ≤0.19 V、THD ≤+4 pp，−20 % 跌落时 M2 上一周期幅值过时导致一次 OC 锁存。
- 协同攻击（保持恒等式）：检测到（Vbat 14/15 周期）但不能校正，结果等于未防护；oracle 双旗标反而 OV 锁存 → 威胁模型边界，设计规则：双旗标且残差在噪声带内时撤销 M0/M5。
- A53 基线：特征核 60 µs、float32 网络 39 µs、tick 1.1 µs（最大 21 µs；共享内核下 1.7 ms 突发）vs 逻辑 2.4 µs 固定、最大 2.9 µs。
- 训练集与随机集均不含 gain 形状（rev3 附录写错，已改）。

### 11.3 论文 v4 → v5（`paper/v4/`）

双栏（IEEEtran；Springer 类离线不可得，正文类无关）、无附录、16 页。新图：电路图（circuitikz）、系统图（电路符号 + 波形插图）、SoC 布局图（块面积 ∝ LUT 占比）+ 检测数据通路、调度图；六张多面板矢量数据图；相关工作对比表；三个算法块；表格全部数字化（每格 ≤3 词、脚注一行）；贡献四条单行；无 limitation 段。质检脚本 `paper/v4/qa.sh`，图件测试 `figtest.sh`。
- 调度抖动注入：1.85 ms 突发对齐到攻击起点 / 修正生效点，E-DC-01b、E-BAT-02b、E-AC-01b 结果不变（功率相同、母线偏差 ≤0.8 V、无锁存、电流峰值 57–63 A；原样对齐时轨迹差仅 0.15 V），突发期间母线轨迹差 ≤2.7 V（`rev_report/hold_injection.csv`）。

## 12. 第三轮修订（v6，2026-09-11）：安全语义修复、分区对比、证据审计

### 12.1 模型补丁（`PV_MEV.slx`，脚本 `scratchpad/matlab/apply_m11.m`，备份 `PV_MEV_pre_m11.slx`）
- `Speed Regulator2`（电压外环 PI）：新增第 3 输入 `Ilim`；`Constant1/2 (±Limit_wreg)` 与 `Saturation2` 由 `Ilim`、`neg (-1)`、`Saturation Dynamic` 取代，抗饱和比较器以 `Ilim` 为界；积分器自身饱和仍为 ±Limit_wreg。
- `Mitigation` 图：新增输入 `Ilim0`（常量 `Limit_V`）、输出 `Ilim`（→ Speed Regulator2:3）；`dbg` 扩为 7 元（第 7 元 = Ilim）。掩码位：M11 (2048) M0 或 M5 激活（g(1)>0 或 g(4)>0）时 `Ilim = 55 A`（最初的 any g>0 规则在 E-BAT-01n 上把合法的 53.5 A 需求压住，已改，`apply_m11b.m`）；M13 (8192) Vdc 标志上升后 0.1 s 内母线修正以 1000 V/s 进入（退出即时）；新增持久量 `t_rise`。
- 充电控制器 `ctrl`：`pc(13) = k_soft`（init_paras 按掩码位 M12 (4096) 设为 400 A/s，否则 0）；状态向量 `x = [st tmr xv xi Iref_prev]`（`xc` 初值 `zeros(1,5)`）；`Iref ≤ Iref_prev + k_soft·Ts`。
- 结构改动使全部旧快照失效：MPCC_R / MPCC_R_ON / MPCC_R_BR / MPCC_H6 / MPCC_R6_P1 重新生成，其余按"0.6 s 前行为相同"复制（MPCC_R.mat → R6/R6_OR*/R_REG/H1..H3；MPCC_R_ON → R6_ON；MPCC_R_BR → R6_BR；MPCC_H6 → MPCC_H6_S）。
- 回归：MPCC_R_REG（437，新模型）vs 存档 MPCC_R（E-MUL-01）：功率、闭锁码与时刻相同；从 0.6 s 起 |ΔVdc| ≤ 0.27 V、THD 差 0.011 pp（快照本身不同，scorecard 级一致，tick 级不一致）。

### 12.2 修复选择（两例 E-MUL-01、E-BAT-02c）
| 候选 | 掩码 | E-MUL-01 | E-BAT-02c |
|---|---|---|---|
| v5（437） | 437 | OC 72.3 A @ 76.7 ms | OC 65.7 A @ 116.5 ms |
| H1 = M11 | 2485 | 无闭锁，60.3 A，Iref 限 55 A，P 100 %，ΔVdc 0.04 V | 无闭锁，50.5 A，P 100 %，ΔVdc 0.08 V，E_def 578 J |
| H2 = M11+M12 | 6581 | 同 H1 | 无闭锁，48.5 A，P 99.8 %，ΔVdc −2.16 V，E_def 791 J |
| H3 = M12+M13（无限幅） | 12725 | 无闭锁，63.4 A（裕度 1.6 A），E_def 186 J | 无闭锁，58.8 A，Iref 66.5 A，E_def 745 J |
| **M11+M14（部署）** | 18869 | 无闭锁，54.9 A，E_def 159 J | 无闭锁，50.5 A，E_def 577 J；E-DC-02b：100 %，−0.29 V，0 J，53.3 A（M11 单独：72.5 %，360 V） |
部署配置先取 2485（仅 M11）；随后 E-DC-02b（−100 V @ 1 kV/s）暴露 M11 单独的缺陷：预测器用带偏的 V_o 建模，实际电流幅值约为参考的 0.75，外环靠 60–90 A 补偿，55 A 限幅使母线停在 360 V、功率 72.5 %。新增 **M14 (16384)**：修正后的母线采样也送入预测器（`Mitigation` 输出 `Vo_ctl` → `D_predict:6`，原 From V_o）。最终部署掩码 **18869** = 437 + 2048 + 16384（脚本 `apply_m14.m`，备份 `PV_MEV_m11_only.slx`）；快照全部重新生成。**注意**：`HIL Input Frame1:6` 仍从 From50（tag V_o）取未修正的母线采样（From11/From15 供 MPCC-P / UMPC 变体，与防御无关）；v6 未做 HIL 运行，下一次 HIL 运行前须把 From50 → HIL Input Frame1:6 改接 `Mitigation:9 (Vo_ctl)`，否则板上 IP 收到的 V_o 与 SIL 不同。根因：修正把外环看到的误差一步改变 50 V（E-MUL-01）或经 M5 使 CV 环把 15 V 误差立即变成 0→20 A 充电阶跃（E-BAT-02c），外环（Kp 0.25 / Ki 80 / 限幅 100 A，相位裕度约 20°）的电流冲击越过 65 A。

### 12.3 v6 运行集（`config.csv` 新增行：MPCC_R6, R6_OR/OR1/OR3, R6_ON, R6_BR, R6_P1, MPCC_H6, MPCC_H6_S, MPCC_R_REG, MPCC_R_H1/H2/H3）
分层队列（`scratchpad/r7/chain_v6.sh` + `chain_x.sh`，≤5 个 MATLAB）：tier0 快照；tier1 R6 13 例、R_REG 13 例、H6 13 例、R6_OR/OR3 13 例、良性 14 × {R6, H6, R6_ON}、R6 的 E-MUL-02/03 与 E-RP-50/100/250/500、R6_OR 的 E-MUL-02/03、H6_S 的 E-BAT-02c；tier2 R6_OR1/BR/P1 13 例、良性 R6_P1/BR、保持注入 7 次、BR 慢漂移；tier2b/c 失配 4 标签 × 4 例 × {R6, R6_BR}（BR 逐标签校准快照）。
tier3（`chain_3.sh`，在 chain_v6 之后）：MPCC_R6 的幅值扫描 S (16)、增益 G (7)、ramp R (4)、CV 段 13（需 `MPCC_R6_cv.mat`）、随机场景 D0301–D0320（MPCC_R6 与 MPCC_H6 各 20）；tier2 另含 R6_OR2 (13)、R6_B (2997, 13)。
报告：`rev_report.py` / `attack_window.py` / `make_paper_assets.py` / `mktables_r2.py` / `random_sil_report.py --base MPCC_H6 --res MPCC_R6` 以 `V6MAP=1` 把 v6 名称映射到论文用名（R6→MPCC_R，H6→MPCC_D_H1，R_REG→MPCC_R_v5）。

### 12.4 板上分区对比（`cpub/rt_sched_cpu.cpp`，`rev_report/r7_sched/`）
同一重放数据（13 998 拍 / 34 缓冲 / 2 721 窗），20 s，三线程绑核普通优先级：all-PL、PL tick + A53 检测、all-A53（估计器均在 PL）。结果见 `tab_partition.tex`：A53 检测周期 105 µs（p99 109，最大 178），A53 tick 1.1 µs（p99 5.4，最大 197），迟到拍 146 / 111 / 28。结论：处理器单独也满足全部截止期；逻辑买到的是与负载无关的计算时间上界，不是吞吐。
注意：`rt_sched.c` 三线程为普通优先级（SCHED_OTHER）绑核 1/2/3，v5 正文 "SCHED_FIFO 80/60/50" 有误，已改。

### 12.5 v6 结果（截至 2026-09-11 11:10，13 例基准，v6 模型）
| 配置 | latched | joint /13 | E_def [kJ] | \|ΔVdc\| [V] | ΔTHD [pp] | t_rec [ms] |
|---|---|---|---|---|---|---|
| MPCC_H6（无保护） | 3 | 5 | 7.18 | 23.99 | 72.9 | 120 |
| MPCC_R_REG（437，无 M11/M14） | 4 | 8 | 2.44 | 0.28 | 1.8 | 66 |
| **MPCC_R6（18869）** | 2（E-DC-02b OV 40.7 ms、E-BAT-01n BOC） | 10 | 2.49 | 0.32 | 1.7 | 57 |
| MPCC_R6_OR（onset） | 1 | 11 | 0.55 | 0.07 | 1.7 | 22 |
| MPCC_R6_OR3（3 周期） | 2 | 10 | 2.21 | 0.10 | 1.7 | 58 |
检测器 − OR3 = 0.28 kJ 全在 E-BAT-02b（Vbat 标志 120 ms）；OR3 − OR0 = 1.66 kJ（DC-01b 170、DC-01c 551、BAT-02b 211、BAT-02c 568、MUL-01 157 J）。配对安全表 both 2 / H only 1 / R only 0 / none 10；峰值电流 E-MUL-01 54.9 A、E-BAT-02c 50.5 A、E-DC-02b 53.3 A。无保护与 437 行与 v5 数字一致。
| MPCC_R6_OR1 / OR2 | 1 / 2 | 11 / 10 | 1.73 / 2.07 | 0.10 / 0.09 | 1.9 / 1.8 | 65 / 65 |
| MPCC_R6_P1（persist 1） | 3（+E-BAT-02c OV 46.9 ms） | 9 | 1.95 | 1.18 | 1.9 | 55 |
| MPCC_R6_B（M9） | 2 | 8 | 3.66 | 3.72 | 1.7 | 57 |
| MPCC_R6_BR（M10） | 2 | 10 | 2.49 | 0.31 | 1.7 | 57 |
补充（22:55 全部完成）：保持注入 7 次无闭锁；失配 η=0.95 母线例 BR 0.49/0.44 V 对 plain 18.0/17.7 V；扫描/增益/CV/随机见 `paper/v4/FACTS.md` 末尾与 `docs_v6/provenance.md` 3b。派生表管线：`paper/v4/regen_v6.sh`（V6MAP=1）。

## 13. 第四轮修订（v7，2026-09-12）：消融、残差检测器、失配+误报
- 新配置：`MPCC_R6_noM11`（16821）、`MPCC_R6_noM14`（2485）、`MPCC_H6_L55`（mask 0、det 0、config 新列 `Limit_V`=55：init_paras 按变体覆盖 Limit_V）、`MPCC_R6_RES`（config 新列 `det_src`=1：`EMI Detector` 子系统新增 `residual_score` MATLAB Function + `det_switch`（u2>0.5 选残差分数）+ 常量 `res_par`/`det_src`；`run_injection` 读 `artifacts/residual.json` 到 `RES`，init_paras 在 det_src=1 时用 RES.thr / RES.par；`clearvars` 例外表加入 RES）。快照：MPCC_R 重新生成并复制到 noM11/noM14/R6_chk，H6_L55 与 R6_RES 单独生成。
- `run_benign` 支持 `opts.mm`：优先取 `<variant>_<tag>.mat` 校准快照，结果文件加 `_<tag>` 后缀；失配 + 良性：12 个非频率例 × {MPCC_R6, MPCC_R6_BR} @ η=0.95。
- 事故：01:00–01:03 期间 init_paras 的 det_src 块暂时插在 cfg_row 之前，使当时启动的用例 FAILED（44 个文件），已删除并补跑。
- 检测延迟分层：`rev_report/flag_latency_benchmark.csv`（first-any / first-correct / first-exact）。
- 模型来源：det_v5 训练 D0001–D0240（180/60），统一 hold-out 73 中 46 在其训练集；D0292–D0300 未运行。
- 结果：见 FACTS.md Review-4 段与 `docs_v6/change_log.md` v7 表。
- 结果（04:02 全部完成，无 FAILED）：without M11 joint 7 / latched 5 / 2.50 kJ（E-DC-01c、E-BAT-02c、E-MUL-01 电网 OC 116/116/75 ms）；without M14 joint 10 / 2.81 kJ（E-DC-02b 72.5 %，母线 −48 V）；MPCC_H6_L55 joint 5 / latched 1 / 7.56 kJ；残差检测器 joint 7 / latched 3 / 5.43 kJ；失配 + 良性（η=0.95）：标志周期 117 → 671 / 710，R6 在 B-CHG-05 OV 闭锁，BR 无闭锁但 −20 % 跌落 67.6 %（限幅 55 A）。
- 模型：残差开关补丁（apply_res.m / apply_res_fix.m，EMI Detector 子系统 residual_score + det_switch，无状态）不改变 det_src=0 变体的结果（MPCC_R6_chk 与 v6 逐项相同）；旧快照仍有效，01:00–01:15 期间的 FAILED 来自 init_paras 编辑，已重跑。
- 未做：限幅按基线参考残差释放（M11 门控改为 BR 残差）；失配 + 攻击 + 负载暂态同跑；PREEMPT_RT / 隔离核重放。

## 14. 最终策略全链路 HIL 补跑与实时调度重测（2026-10-01）

板卡重新联网后，用仓库重建的 `mpcc_r.bit`（带保号修复）和仓库里的板端程序（部署到 `/home/xilinx/mpcc_r_repro/`，
自检 `board_selftest_mpcc_r.py` 通过）补齐最终策略 `MPCC_R6`（mask 18869，含 M11 / M14）的全链路 HIL。

### 14.1 预测器校正进入 HIL 通路（`build_hil('vo')`）
原 HIL 帧（`HIL Input Frame1` 第 6 路）直接取量测母线 `V_o`，绕过了 M14：SIL 的 `D_predict` 用的是
`Mitigation` 输出 9（`Vo_ctl`，校正后的母线）。首次试跑 E-DC-01b 因此与 SIL 不同（母线 +0.184 V、THD50 3.245 %，
SIL 为 +0.083 V、2.729 %；记分卡留在 `results/emi/hil_v6_raw_vo_trial/`）。`build_hil('vo')` 把帧的第 6 路改接
`Mitigation:9`，模型结构变化后重新生成 `MPCC_R6` 快照。

### 14.2 全链路 HIL（三路全开，`results/emi/hil_v6/`）
13 个攻击 + 两个慢斜坡（E-RP-250 / 500）× `MPCC_R6`，每次 14 001 拍占空比、2 801 次谐波估计、36 次检测都由
板卡应答（TCP 往返均值 1.9 / 1.85 / 5.8 ms，主机步进）。同一天在 SIL 重跑了这 15 例，13 个基准例逐项复现归档记分卡。
配对结果见 `hil_v6/equivalence.csv`（`EMI_DET_FPGA/scripts/hil_report.py equivalence`）：

- 功率保持、闭锁代码与闭锁时刻、检测时刻、逐周期标志字：15 / 15 对相同（标志不一致周期 0）。
- 攻击窗记分卡：14 / 15 对逐位相同；E-RP-250 在 0.96 s 起轨迹分离，母线均值差 0.00014 V、THD50 差 0.0065 pp。
- 攻击撤除后另有 4 对轨迹分离（E-AC-02b、E-AC-02h 自 1.10 s，E-DC-02b、E-RP-500 自 1.18 s）：逐拍母线差
  ≤ 0.19 V，恢复段母线均值差 ≤ 0.008 V，THD50 差 ≤ 0.039 pp。
- 板上占空比与 SIL 的差在未分离的各对中为单精度舍入量级（中位 3e-8，首拍 1.2e-4），小于仿真 PWM 的时间分辨率
  （50 ns 步长），所以开关时刻相同、电气量逐位相同；板上检测器 logit 与 ONNX 最大差 0.13 到 3.3，不改变标志。
- 结果：基准 11 例中 10 例联合成功，E-DC-02b（−1000 V/s）功率 100 %、母线 −0.29 V，但 40.7 ms 时 OV 闭锁，
  与 SIL 相同；E-RP-250 / 500 在 SIL 与 HIL 中均无闭锁（母线 +1.67 / +1.07 V）；两个电池电流例与 SIL 相同
  （74.5 %、BOC 闭锁），不在恢复基准内。

### 14.3 实时调度下的并发定时重测
见 `PS_notebook/logs_20261001/README.md`：SCHED_FIFO + 内存锁定下，五次 20 s 重放共 2 000 005 次控制释放、
400 005 次估计释放、5 005 次检测释放均无迟到；控制拍最大响应 48.5 µs。原普通优先级测量的 124 次迟到来自
操作系统抢占。

### 14.4 板上检测器在本文闭环中的判定（`hil_v6/detector_summary.csv`）
`EMI_DET_FPGA/scripts/hil_detector_summary.py` 从每次 HIL 的逐周期记录（板端标志字 `hil_flags`）统计：13 个攻击全部在
攻击期间标出全部被攻击通道，12 例在 40 ms、E-BAT-02b 在 120 ms；标志集合与真值完全一致 6 / 13（其余多标 Ibat 等）；
攻击前 78 个周期无标志；标志集合与检测时刻同 SIL。

### 14.5 起始相位重复（2026-10-02，`tests.csv` 中 `-p05 / -p10 / -p15` 共 33 例）
11 个基准攻击把起始时刻延后 5 / 10 / 15 ms（工频周期与检测窗的 1/4、1/2、3/4），`MPCC_R6`，SIL 与全链路 HIL 各跑一遍
（记录到 1.32 s，每次 14 401 拍）。四个起始相位下联合成功均为 10 / 11（SIL 与 HIL 相同），充电功率全部恢复，
唯一闭锁的仍是 E-DC-02b（OV，40.7 到 44.8 ms）。板上检测时刻 25 到 55 ms（对齐起始为 40 到 120 ms）。
33 对中闭锁、标志、检测时刻全部同 SIL；7 对在攻击窗内轨迹分离，记分卡母线均值差 ≤ 0.010 V、THD50 差 ≤ 0.046 pp。
连同 14.2 的 15 对，共 48 对全链路 HIL：板上检测 48 / 48 命中，攻击前 288 个周期无标志。

### 14.6 板卡功耗
见 `PS_notebook/logs_20261002/README.md`：完整设计运行时 12 V 输入 11.35 W，比仅控制器设计多 0.61 W。
