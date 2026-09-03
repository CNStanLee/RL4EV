# 阶段二至四实验计划：EMI 注入检测、鲁棒 MPCC 与 ZCU104 上板

阶段一（`EMI_INJECTION_TEST_PLAN.md`）已经在 PV_MEV 上刻画了六种 PFC 策略在五条传感链注入下的行为。本文件规划后续三个阶段：先做一个能识别这些注入的深度学习检测器并卸载到 FPGA 成为线速加速器（阶段二），再根据检测结果给 MPCC 加上应对策略（阶段三），最后把 MPCC 与检测器一起放到 ZCU104 上联调实时性（阶段四）。本文件只是计划，不启动实验。

| 项目 | 内容 |
|---|---|
| 前置条件 | 阶段一 78 次注入运行的记分卡与时序（`results/emi/`），六策略快照，`tests.csv` 与 `Disturbance Injector` |
| 目标器件 | ZCU104（xczu7ev-ffvc1156-2-e），PYNQ 镜像，现有 `Vivado_PRJ/MPCC`（含 `zcu104_base.xsa`） |
| 已有可复用件 | `FFT_HGQ_BLS_FPGA`：HGQ2 训练、Keras→ONNX→Alkaid ALIR bit-exact 导出、Simulink ONNX 包装、FPGA 工程生成脚本；`HLS_PRJ/mpcc`：MPCC HLS IP（14 个 float 入、1 个 float 出，10 ns 时钟）；`PS_notebook`：PYNQ HIL 服务器（TCP 5010 收帧、5011 回 D）与 `tcp_cosim_utils`；`Simulink_con_test`：MATLAB↔FPGA TCP 协议验证 |
| 工具链 | MATLAB R2024b（PV_MEV 模型）/ R2025a（FFT_HGQ_BLS 模型）、Python 3.10 + HGQ2 + Alkaid、Vitis HLS / Vivado 2024.x、PYNQ 3.x；FINN + Brevitas 作为备选路线 |
| 名词 | SIL：检测器 / 新 MPCC 以软件模型（ONNX / C 模型）在 Simulink 闭环中测试；HIL：Simulink 通过 TCP 连接 ZCU104 上的 PL IP 闭环测试 |

---

## 0 总览

| 阶段 | 目标 | 主要交付物 | 通过判据 | 依赖 |
|---|---|---|---|---|
| 二 A 数据与模型 | 从控制器"看得见"的信号识别注入的通道、形状与幅值 | 数据集 `data/emi_det/`、检测模型（HGQ2 或 FINN）、离线评估报告 | 逐类召回 ≥ 95%，良性瞬态误报率 ≤ 1 次 / 100 次运行，检测延迟 ≤ 2 个工频周期 | 阶段一时序文件、`Disturbance Injector` 的随机化 |
| 二 B SIL | 检测器以 ONNX 接入 PV_MEV 闭环，在 `tests.csv` 全部用例上工作 | `PV_MEV` 中的 `EMI Detector` 子系统、SIL 记分卡 | 与离线结果一致；检测时刻早于阶段一记录的保护触发时刻 | 二 A |
| 二 C FPGA 加速器与 HIL | 检测器成为 PL 上的线速 IP，经 TCP 与 Simulink 闭环 | 检测器 IP、bit-true 报告、HIL 记分卡 | 每帧延迟 < 250 µs（4 kHz 一帧），bit-true 与 SIL 逐值一致，HIL 记分卡与 SIL 一致 | 二 B、Alkaid / FINN 工程生成 |
| 三 鲁棒 MPCC | 基于检测输出的条件应对策略，使 MPCC 在注入下保持母线、充电功率和电流质量 | `MPCC_R` 变种（`config.csv` 新行）、策略设计文档、消融记分卡 | 对比 MPCC_D_F1：触发次数减少、功率保持率提高、恢复时间缩短；无注入基线 THD 不劣化超过 0.3 pp | 二 B（检测输出接口） |
| 四 ZCU104 上板 | MPCC_R 与检测器同在 PL，PS 提供 HIL 服务，验证实时性 | 块设计、bitstream、PS 驱动、实时性报告 | PL 内每控制拍延迟 < Ts_Control（20 kHz 时 50 µs），检测器每帧 < 250 µs；HIL 闭环结果与 SIL 一致 | 二 C、三 |

---

## 1 阶段一结果如何进入后续阶段

### 1.1 检测器只能看到控制器内部量

注入的定义是内部量 y\* = y + Δy，检测器和控制器处在同一侧，看不到真实量。它必须从内部量之间的不一致来推断注入，这决定了输入特征的选择。阶段一实测给出了每类注入在内部量上的可见特征：

| 注入类别 | 阶段一实测现象（内部量侧） | 可用于检测的特征 | 与良性瞬态的区分点 |
|---|---|---|---|
| Vdc 正偏（E-DC-01b/c） | 内部 Vdc 回到 400 V（+50 V）或停在 436 到 450 V（+100 V，外环饱和 Iref = −100 A）；真实母线 350 / 336 V | Iref 与 Vdc_int 的关系：Vdc_int ≥ 参考却 Iref 持续为负；电流幅值与功率平衡（Vbat·Ibat 对 Vac·Iac）不匹配；D 均值偏离 1 − \|Vac\|/Vdc_int | 负载阶跃时 Iref 也会瞬时变负，但 20 ms 内恢复；功率平衡在负载阶跃下仍成立 |
| Vdc 负偏（E-DC-02b） | 内部 Vdc 跟随 400 V，真实 500 V；Iref 上升，D 均值下降 | D 均值与 Vdc_int 的隐含关系 D ≈ 1 − \|Vac\|/Vdc 失配 | 同上 |
| Vac 直流偏差（E-AC-01a/b） | MPCC_D 系列真实电流出现 −4 / −8 A 直流分量；MPCC_P、CRPR 基本不受影响 | Vac_int 的周期均值（应为 0）；Iac_int 的周期均值；PLL 相位与 Vac 过零的偏差 | 电网电压跌落不产生直流分量 |
| Iac 直流偏差（E-AC-02b） | 内部 Iac 均值为 0，真实电流 −5 A；2 次谐波 3 到 6% | Iac_int 与 Iref·\|sin θ\| 的对称性：正负半周幅值差；2 次谐波幅值 | 负载阶跃引起的幅值变化两个半周对称 |
| Iac 正交正弦（E-AC-02s） | PF 0.985 到 0.990，THD 基本不变 | Iac_int 相对 θ 的相位；PF 估计 | 电网频率偏移时 PLL 会跟随 |
| Hall 模型（E-AC-02h） | THD 21 到 26%，直流 −1.9 到 −2.7 A，100 Hz 分量 | 2 次谐波幅值、直流分量 | 无良性来源 |
| Vbat 正偏（E-BAT-02b/c） | 提前 CV，功率 3.4 / 0 kW；02c 下 PFC 空载：MPCC 系列母线 445 V、电流退化为脉冲，CRPR 母线 726 V 且 OC | 充电级：CC→CV 切换时 Vbat_int 跳变（+10 V 台阶）；PFC 侧：负载功率突降 | 电池真实到达 CV 时 Vbat 是缓变的，不会阶跃 |
| Ibat 偏差（E-BAT-01b/01n） | 功率 74% / 126%，01n 触发 BOC | Ibat_int 阶跃而 D_dcdc 反向变化；功率平衡 Idc·Vdc 对 Vbat·Ibat_int | 充电电流参考斜坡是已知输入 |
| 多通道（E-MUL-01） | THD 上升大于两单通道之和 | 上述特征组合 | — |

结论：检测器的输入应包含 Vdc_int、Vac_int、Iac_int、Iref、D、θ_pll 六个 PFC 内部量，充电级再加 Vbat_int、Ibat_int、D_dcdc、state；单靠电流波形不够，Vdc 链注入主要靠外环与功率平衡的失配来发现。

### 1.2 阶段一数据作为种子

`results/emi/ts/` 中 78 条注入运行和 6 条基线的 10 kHz 时序（0.6 到 1.3 s）与 1 MHz Iac，直接作为检测器的测试集（不参与训练），其标签是 `tests.csv` 的 channel / shape / amp / t_on。训练集另行生成（第 2.3 节），保证测试集是"没见过的"。

---

## 2 阶段二：EMI 注入检测模型与 FPGA 线速加速器

### 2.1 目标与输出定义

检测器每个工频周期（20 ms，4 kHz 下 80 点）给出一次判决，也可以每半周期滑动更新。输出三部分：

| 输出 | 形式 | 说明 |
|---|---|---|
| 类别 | 10 类 softmax：无注入、Vdc+、Vdc−、Vac 直流、Iac 直流、Iac 正交、Iac Hall、Vbat、Ibat、多通道 | 多通道可以改为多标签（每通道一个 sigmoid），第一版先用 10 类 |
| 幅值 | 回归，按通道量纲归一（Vdc 除以 100 V，Iac 除以 20 A 等） | 供阶段三做补偿；容许误差 ±20% |
| 置信度与持续计数 | 类别概率与连续判决次数 | 应对策略只在连续 2 次同类判决后动作，抑制误报 |

延迟目标：从注入起始到首次正确判决 ≤ 2 个工频周期（40 ms）。阶段一中最快的保护触发是 E-DC-01c CRPR 的 OC（23 ms）和 E-DC-02b 的 OV（40 ms），检测必须与之同量级或更快，因此第二版考虑半周期滑动窗（10 ms 更新）。

### 2.2 输入特征与两条模型路线

两条路线并行准备，先做 B，A 作为第二版：

| 路线 | 输入 | 模型 | 规模估计 | 优点 | 风险 |
|---|---|---|---|---|---|
| B 周期特征 + 小 MLP | 每周期计算 16 到 24 个标量特征：Vac_int 均值 / 幅值、Iac_int 均值 / 正负半周幅值差 / 2 次与 3 次谐波比 / 与 Iref·\|sin θ\| 的相关系数、Vdc_int 均值 / 纹波 / 与参考差、Iref 均值 / 符号、D 均值 / 与 1 − \|Vac\|/Vdc 的差、功率平衡残差、充电级 4 个量；取当前与前一周期两组 | HGQ2 MLP 3 层 32 到 64 宽（`build_mlp`） | < 10 k 参数，8 bit | 特征可解释，FPGA 资源极小，特征本身就是阶段三补偿的输入 | 特征提取要在 PL 上另做一个模块（累加器与 Goertzel 2 / 3 次） |
| A 原始窗口 + 1D CNN / Residual-BLS | 80 点 × 6 通道（PFC 内部量）窗口，归一化同 `contract.json` | HGQ2 Residual-BLS（`build_residual_bls`，已有 ALIR 导出）或 1D CNN；FINN 路线用 Brevitas QNN | 30 到 60 k 参数 | 复用现有 HGQ2 估计器的输入缓冲与导出链，形状类识别更强 | 对 Vdc 链注入的可见性依赖跨周期信息，可能需要 2 周期输入 |

FINN 与 HGQ2 的取舍：HGQ2 已经打通 Keras→ONNX→ALIR bit-exact 与 Simulink ONNX 包装，MLP / Residual-BLS 直接可用；FINN 适合 CNN 的数据流架构，但需要新建 Brevitas 训练、FINN 编译流程和 Simulink 接口。计划以 HGQ2 为主线，FINN 只在路线 A 的 CNN 资源或延迟不达标时启用，届时对比两者的 LUT / DSP / 延迟。

### 2.3 数据集生成

训练数据由 `run_injection` 的随机化模式生成（新增 `run_injection('dataset', N)`），每次运行从六策略快照起跑 0.7 s，注入参数按拉丁超立方采样：

| 维度 | 取值范围 |
|---|---|
| 策略 | 六种均匀 |
| 通道 | 5 通道 + 无注入 + 双通道，无注入占 25% |
| 形状 | step 50%、ramp 15%、sine 15%、hall 10%、pulse / tri 10%（后两者只作训练多样性） |
| 幅值 | Vdc ±20 到 ±120 V，Vac ±5 到 ±40 V，Iac 1 到 20 A，Vbat 2 到 25 V，Ibat 1 到 8 A，含负号 |
| 起始 / 驻留 | t_on 0.65 到 0.90 s，驻留 0.1 到 0.3 s |
| 良性瞬态（负样本） | 充电电流参考阶跃 20→10→20 A、Vref 阶跃 ±20 V、电网电压 ±10% 跌落 / 抬升、频率 49 到 51 Hz、测量白噪声（1% 量程） |
| 电池工作点 | CC 20 A、CC 10 A、CV 段（Voc 345 V 快照，新增） |

数量与耗时：每次运行约 15 min（3 进程并行有效 5 min）。第一版 240 次（每策略 40 次）约 20 h，加 CV 段快照 6 次。第二版按离线评估结果补充薄弱类别。所有运行沿用 `results/emi/ts/` 的格式，另加标签文件 `labels.csv`（run_id, variant, channel, shape, amp, t_on, dwell, benign_event）。

训练 / 验证 / 测试划分按运行切分；OOD 测试集为：未见过的幅值区间、留出一种策略（如 MPCC_D_R）、以及阶段一的 78 条实测运行。

### 2.4 离线评估指标

| 指标 | 定义 | 目标 |
|---|---|---|
| 逐类精确率 / 召回率 | 以周期为单位，注入起始后第 3 个周期起计 | ≥ 95% |
| 检测延迟 | 首次正确判决时刻 − t_on | 中位数 ≤ 1 周期，最大 ≤ 2 周期 |
| 误报率 | 无注入与良性瞬态运行中的错误判决数 | ≤ 1 次 / 100 次运行（每次 35 周期） |
| 幅值误差 | 回归输出与真值的相对误差 | 中位数 ≤ 20% |
| 撤除识别 | 注入结束后回到"无注入"的延迟 | ≤ 2 周期 |
| 量化损失 | HGQ2 8 bit 与 float 模型的指标差 | 召回下降 ≤ 1 pp |

### 2.5 SIL：Simulink 闭环

1. 在 `PFC Control` 内新增 `EMI Detector` 子系统：4 kHz 缓冲（复用 HGQ 估计器的 80 点缓冲）、特征提取（路线 B）或直接窗口（路线 A）、ONNX Model Predict（Simulink 包装同 `export_simulink.py`）、判决后处理（阈值、连续计数）。输出 `det_class`、`det_amp`、`det_conf` 写入 Goto，记录到 `run_injection` 的时序文件。
2. 在 `tests.csv` 全部 13 条 × 6 策略上重跑（78 次，约 6.8 h），得到 SIL 记分卡：每次运行的首次判决时刻、类别、幅值估计，与保护触发时刻对照。
3. 判据：SIL 检测延迟和类别与离线一致；对阶段一 78 条实测数据的召回 ≥ 90%（它们是未见过的测试集）。
4. bit-exact 链：Keras → ONNX → ALIR 三者在 1000 个样本上逐值一致（沿用 `check_alkaid.py`）。

ONNX Model Predict 需要 Python 环境，PV_MEV 中 MPCC_D_M1 / M05 的 ONNX 子系统当前是注释掉的；SIL 前先恢复该环境（`init_paras.m` 的 `pyenv` 行）。

### 2.6 FPGA 加速器与 HIL

| 步骤 | 内容 | 判据 |
|---|---|---|
| IP 生成 | `generate_fpga_project.py --part xczu7ev-ffvc1156-2-e --clock-ns 10`（Alkaid）或 FINN 编译；路线 B 的特征提取用 Vitis HLS 写成 `emi_feat_hls`（周期累加、Goertzel、功率平衡），与检测 IP 用 AXI-Stream 串接 | 综合通过，LUT < 30%、DSP < 40%、Fmax ≥ 100 MHz |
| 线速 | 每 4 kHz 帧一次推理：特征提取 II = 1 逐样本流水，MLP 延迟 < 10 µs；路线 A 的 Residual-BLS 延迟 < 100 µs | 每帧总延迟 < 250 µs，吞吐 4 kHz 无积压 |
| bit-true | C/RTL 协同仿真与 Keras 输出逐值比对 | 1000 样本全等 |
| HIL | 复用 `PS_notebook` 的 TCP 服务器：MATLAB 每个 4 kHz 帧发送 80 点 × 通道（或特征向量）到 5020 口，PL 推理后回 [class, amp, conf] 到 5021 口；Simulink 侧的 `EMI Detector` 用 TCP 版替换 ONNX 版；在 P1 7 条用例 × 六策略上闭环 | HIL 记分卡与 SIL 逐周期一致；记录 TCP 往返时间（预期 1 到 3 ms，仿真侧阻塞等待，不是实时约束） |

### 2.7 交付物

`FFT_HGQ_BLS_FPGA` 同级新建 `EMI_DET_FPGA/`：`data/`（labels.csv 与运行索引，时序留在 `results/emi/`）、`src/emi_det/`（特征、模型、训练、导出）、`artifacts/`（keras、onnx、alir、contract.json）、`hls/emi_feat_hls/`、`reports/`（离线、SIL、bit-true、HIL 四份记分卡）；PV_MEV 中新增 `EMI Detector` 子系统与 `run_injection('dataset')`、`run_injection('sil')`、`run_injection('hil')` 模式。

---

## 3 阶段三：基于检测结果的应对策略（鲁棒 MPCC）

### 3.1 原则

应对策略是条件性的：只在检测器给出稳定判决后启用，无注入时 MPCC_R 与 MPCC_D_F1 行为完全相同。这样阶段一刻画的"原始行为"仍然可复现（关闭检测输出即回到原策略），也避免为鲁棒性牺牲基线电流质量。

### 3.2 按注入类别的策略候选

| 类别 | 阶段一暴露的问题 | 策略候选（按优先级） | 需要的检测输出 |
|---|---|---|---|
| Vdc 正偏 | 外环把真实母线压到整流峰值，充电停止，电流畸变，OC | ① 用检测幅值校正 Vdc_int（Vdc_corr = Vdc_int − Δ̂）；② 外环参考限幅 Iref ≥ 0，禁止负参考（CRPR / MPCC 都不能用负参考做有用功）；③ 用功率平衡 Vbat·Ibat / η ≈ Vac_rms·Iac_rms 反推母线电压作为外环备用反馈；④ 向充电级发降额指令避免降压级脱出调节 | 类别、幅值 |
| Vdc 负偏 | 母线 500 V，OV 40 ms | ① 同上校正；② 检测到 Vdc− 后立即把 Iref 限到当前值的 50% 并按功率平衡估计母线；③ 母线电压变化率限制（dVdc/dt 由 Idc − D·Ibat 估计） | 类别、幅值、时间到 OV 的预测 |
| Vac 直流偏差 | MPCC_D 前馈 D_ff = 1 − \|Vin\|/Vo 引入 −4 到 −8 A 直流 | ① 前馈改用 PLL 重构的 Vin = V̂·sin θ（幅值来自周期 RMS），不用瞬时 Vac_int；② Vac_int 去直流（周期均值扣除）；③ MPCC_P 极性判定改用 θ 而不是 sign(Vin) | 类别（只需一位开关） |
| Iac 直流偏差 | 真实电流 −ΔI 直流，估计器把它当谐波补偿 | ① 预测器输入 i_L 扣除周期均值（直流观测器）；② 检测期间冻结 FFT / RLS 估计器更新，沿用冻结前的谐波相量（估计器已有 watchdog 回退机制可复用）；③ 用检测幅值直接补偿 i_L | 类别、幅值 |
| Iac 正交 / Hall | PF 下降、2 次谐波、THD 21 到 26% | ① 估计器冻结；② 对 i_L 做 100 Hz 陷波（Hall）；③ 参考相位以 θ 为准，忽略电流相位反馈 | 类别 |
| Vbat 正偏 | 提前 CV、功率减半或停止；停止后 PFC 空载：CRPR 母线失控、MPCC 系列电流脉冲化 | ① 充电级：Vbat_int 阶跃且 D_dcdc 未变时判为注入，保持 CC；② PFC：检测到空载时把 Iref 下限设为泄放所需最小值并把 MPCC 切到轻载模式（降低 Fc 或改用 D 预测的最小脉冲）；③ CRPR 明确不适用空载，作为对照 | 类别、充电级状态 |
| Ibat 偏差 | 功率 74% / 126%，BOC | ① 功率平衡校验 Idc·Vdc ≈ Vbat·Ibat_int，残差换算 ΔI 并补偿；② 保持上一有效设定 | 类别、幅值 |
| 多通道 | 非线性叠加 | 按 Vdc → Iac → Vac 顺序逐个处理，每步重新检测 | 多标签输出 |

### 3.3 实现方式

- 新变种 `MPCC_R`：`config.csv` 增加列 `use_detector`、`mitigation_mask`（按类别位掩码），`init_paras.m` 读入；`PFC Control` 内新增 `Mitigation` 子系统，输入检测输出与内部量，输出校正后的 Vdc、Vin、i_L 与 Iref 限幅；只改信号路径，不改 MPCC 预测公式本身，便于后续 HLS 复用。
- 每条策略单独可开关，做消融。

### 3.4 评价

在 `tests.csv` 13 条用例上比较四组：MPCC_D_F1（原始）、MPCC_R 检测关闭、MPCC_R 检测开启、MPCC_R 策略常开（无检测，验证条件触发的必要性）。指标沿用阶段一记分卡，新增：

| 指标 | 定义 | 目标（相对 MPCC_D_F1） |
|---|---|---|
| 触发次数 | OC / OV / UV / BOC 触发的用例数 | 减少 ≥ 50% |
| 功率保持率 | P_charge 注入中 / 基线 | E-DC-01b ≥ 90%，E-BAT 类不变（充电级注入的功率损失是充电控制器的决定，不由 PFC 补） |
| ΔVdc 残差 | 校正后真实母线与 400 V 的差 | ≤ 10 V（Vdc 链） |
| THD50 上升 | 注入中 − 注入前 | ≤ 原策略的 50% |
| 恢复时间 | t_rec | ≤ 原策略 |
| 检测到动作延迟 | 判决时刻到策略生效 | ≤ 1 周期 |
| 良性代价 | 无注入与良性瞬态下 MPCC_R 与 MPCC_D_F1 的 THD50、t_settle 差 | THD ≤ 0.3 pp，t_settle ≤ +10 ms |

运行量：4 组 × 13 用例 = 52 次，加良性瞬态 4 组 × 5 次，约 6 h。

### 3.5 交付物

策略设计文档（每类一节：机理、公式、参数、开关）、`MPCC_R` 模型与配置、消融记分卡与图（与阶段一图 4 / 图 7 同版式，增加 MPCC_R 列）。

---

## 4 阶段四：MPCC 与加速器卸载到 ZCU104，上板联调实时性

### 4.1 现状与接口

| 现有件 | 接口 | 状态 |
|---|---|---|
| MPCC HLS IP（`HLS_PRJ/mpcc`） | 14 float 输入（i_L, i_ref, V_in, Ts, L, V_o, θ, A3/5/7, φ3/5/7, use_harmonic）→ D | 已通过 C 测试与 HIL（`bb04b5c`） |
| PS HIL 服务器（`PS_notebook/mpcc_hil.ipynb`） | TCP 5010 收 14 个 single，5011 回 1 个 single | 已与 Simulink 联调 |
| Simulink 侧（`PFC Control` 的 HIL TCP Send / Receive） | 每控制拍一帧 | `ENABLE_HIL = 1` 时启用 |
| HGQ 估计器 ALIR | 80 点 → 8 相量 | 已 bit-exact，未综合 |
| ZCU104 基础设计 | `Vivado_PRJ/MPCC/zcu104_base.xsa` | 已有 |

### 4.2 目标架构

```
PS (PYNQ)                         PL
TCP 服务器 / DMA  ──AXI-Stream──►  帧解析 ─► 4 kHz 缓冲(80×6) ─► 特征提取 emi_feat_hls ─► 检测器 IP ─┐
                                         │                                                        ▼
                                         └──► 谐波估计器 IP(可选) ──► MPCC_R IP（含 Mitigation） ─► D ─► AXI-Stream ─► PS
```

- MPCC_R IP：在现有 `mpcc_hls` 基础上增加 Mitigation 逻辑与检测输入（class、amp、conf），接口从 14 float 扩为 18 float，保持向后兼容（检测输入为 0 时行为等于原 IP）。
- 检测器 IP 与 MPCC IP 时钟同域（100 MHz），检测器每 250 µs 出一次结果，MPCC 每控制拍读取寄存器中的最新判决。
- 第一阶段的联调仍用 TCP（功能等价性）；实时性用 PL 内部计数器测量，不依赖 TCP 延迟。

### 4.3 步骤

| 步骤 | 内容 | 判据 |
|---|---|---|
| 1 IP 集成 | Vivado 块设计接入 MPCC_R、`emi_feat_hls`、检测器 IP，AXI-Lite 寄存器暴露判决与延迟计数器 | 综合 / 实现通过，时序收敛 100 MHz |
| 2 bitstream 与 PS 驱动 | 更新 `mpcc_overlay.py`：帧编码扩到 18 float，新增读取 det_class / det_amp / det_conf 与 PL 延迟计数 | 回环测试通过 |
| 3 HIL 功能等价 | `ENABLE_HIL = 1`，PV_MEV 在 P1 7 条用例 × MPCC_R 闭环，与阶段三 SIL 记分卡对照 | 每周期判决一致，D 序列差 < 1 LSB（8 bit） |
| 4 PL 实时性 | 用 PL 计数器记录：MPCC_R 每拍延迟、检测器每帧延迟、特征提取吞吐；重放阶段一记录的时序（DDR → AXI-Stream）做无 TCP 的自持运行 | MPCC_R < 50 µs（20 kHz）且目标 < 10 µs（100 kHz 备用）；检测器 < 250 µs；无帧丢失 |
| 5 端到端时延 | TCP 往返、PS 处理、PL 延迟分解 | 给出分解表；说明 TCP 部分不是实时路径 |
| 6 资源与功耗 | 三个 IP 的 LUT / FF / DSP / BRAM、PL 功耗 | 报告 |

### 4.4 实时性判据与测量方法

| 量 | 测量 | 目标 |
|---|---|---|
| MPCC_R 单拍延迟 | HLS 报告 + PL 计数器（start 到 D 有效） | < 50 µs，目标 < 10 µs |
| 检测器帧延迟 | 帧最后一个样本到 det 输出有效 | < 250 µs |
| 抖动 | 1000 帧的延迟标准差 | < 5% 均值 |
| 吞吐 | 4 kHz 连续帧无丢帧，20 kHz 控制拍无丢拍 | 0 丢失 |
| 等价性 | 上板 D 与 SIL D 序列 | 逐拍差 < 1 LSB |

### 4.5 交付物

Vivado 工程与 bitstream（`Vivado_PRJ/MPCC_R/`）、`PS_notebook/mpcc_r_hil.ipynb` 与驱动、HIL 记分卡、实时性报告（延迟分解表、抖动直方图、资源表）。

---

## 5 时间、资源与风险

| 阶段 | 估计工作量 | 主要机时 |
|---|---|---|
| 二 A | 3 周 | 数据集 240 次约 20 h 仿真；训练 < 1 h |
| 二 B | 1 周 | SIL 78 次约 7 h |
| 二 C | 2 周 | 综合 1 到 2 h / 次；HIL 42 次约 4 h |
| 三 | 3 周 | 消融 72 次约 6 h |
| 四 | 3 周 | 实现 1 到 2 h / 次；HIL 42 次约 4 h |

| 风险 | 影响 | 对策 |
|---|---|---|
| Vdc 链注入在内部量上与真实负载变化难区分（外环都表现为 Iref 变化） | Vdc 类召回低或误报 | 功率平衡特征（充电级功率对电网功率）是关键；如仍不够，给检测器加充电级信号，并接受"负载阶跃后 1 周期内不判决"的规则 |
| 数据集仿真时间（每次 15 min） | 阶段二 A 拖长 | 先用阶段一 78 条做可行性；数据集分两批，第一批 120 次 |
| ONNX / Python 环境在 R2024b 下不可用 | SIL 受阻 | 备选：用 HGQ2 导出的定点权重在 Simulink 里以 MATLAB Function 实现前向（MLP 极小，可行） |
| TCP HIL 不是实时的 | 无法直接证明实时性 | 实时性由 PL 计数器与 DDR 重放证明，TCP 只证明功能等价 |
| MPCC_R 的策略常开会劣化基线 | 违反"不牺牲基线"原则 | 消融组"策略常开"专门量化这一点，只保留条件触发 |
| 模型版本（PV_MEV R2025a 创建，本机 R2024b） | 保存格式漂移 | 统一用 R2024b 保存，`FFT_HGQ_BLS` 的 R2025a 模型不合并进 PV_MEV |

---

## 6 与阶段一文件的衔接

| 阶段一产物 | 后续用途 |
|---|---|
| `results/emi/ts/*.csv`、`*_iac.mat` | 阶段二测试集；阶段四 DDR 重放源 |
| `results/emi/scorecard.csv` | 阶段三对照基线（MPCC_D_F1 列） |
| `tests.csv`、`Disturbance Injector` | 阶段二数据集生成的模板；阶段三与四的验证矩阵 |
| `Protection Monitor` | 阶段三"触发次数"指标；阶段二检测延迟对照 |
| `run_injection.m` | 扩展 `dataset` / `sil` / `hil` 模式 |
| `make_injection_figs.m` | 图 4 / 图 7 增加 MPCC_R 与检测延迟列 |
