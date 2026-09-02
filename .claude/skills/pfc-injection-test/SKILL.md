---
name: pfc-injection-test
description: 在 PV_MEV 模型上执行"传感链注入"（EMI 等效测量偏差）测试，对比 CRPR / MPCC_P / MPCC_D 系列 PFC 策略；覆盖 PFC 级（Vdc/Vac/Iac）与电池充电级（Vbat/Ibat，CC/CV）。用于实现或运行 E-DC / E-AC / E-MUL / E-BAT 用例、生成 scorecard 与图，或扩展 run_benchmark 的注入功能。
---

# PFC 传感链注入测试

权威规划文档：`Simulation/PV_MEV/docs/EMI_INJECTION_TEST_PLAN.md`（同目录有 PDF 版，图在 `docs/figures/`）。执行前先读它，尤其是第 3 节（注入点、干扰发生器参数、保护阈值、快照、第 3.5 节充电级模型扩展）、第 6 节（用例表 = `tests.csv` 内容）、第 8 节（指标定义）和第 9 节（每张产出表与图的列、预计值）。

## 已有基础设施

- `Simulation/PV_MEV/init_paras.m`：模型 InitFcn，按基础工作区变量 `VARIANT_NAME` 读 `config.csv` 一行，派生 `Ts_Control = 1/Fc`。
- `Simulation/PV_MEV/run_benchmark.m`：无扰基准脚本。可复用其变种循环、信号日志、离线 1 MHz THD 计算和 `results/*.csv` 合并逻辑。
- `Simulation/PV_MEV/results/benchmark_results.csv`：电阻负载下六种策略的基线（文档表 4-1）。
- 模型内 `EV System/Measurements 1` 取真实量；`EV System/PFC Control` 输入 2/3/4（Vdc_PFC、Vac、Iac）是控制器内部量。注入块插在 From16/From18/From19 到 PFC Control 的连线上。
- `docs/figures/fig1..fig6` 为预计示意图，由 scratchpad 的 `make_figs.py` 风格脚本生成；实测图用同样版式替换。

## 实现顺序

1. 在 `MyLibrary.slx` 中新增：`Disturbance Injector`（参数见文档表 3-2）、`Protection Monitor`（表 3-3 五个阈值，只看真实量，默认只记录）、`Charger Stage`（表 3-3 充电级：降压 DC-DC + 电池 Voc/Rint + CC/CV 控制器 + Vbat/Ibat 注入点）。
2. 在 `PV_MEV.slx` 的 EV System 内用 `Charger Stage` 替代 Ro 支路，插入五个注入块；注入参数从基础工作区变量读取（`inj_channel`, `inj_shape`, `inj_amp`, `inj_k`, `inj_f`, `inj_phase`, `inj_period`, `inj_duty`, `inj_t_on`, `inj_dwell`, `K_hall`）；无扰时 `inj_amp = 0`。充电级参数（`Icc`, `Vcv`, `Voc`, `Rint`）加入 `init_paras.m`。
3. 先跑 B0'：六策略在充电级负载下的新基线，并保存 CC 段（Voc 335 V）与 CV 段（Voc 345 V）快照到 `results/emi/snapshots/`。
4. 新建 `Simulation/PV_MEV/tests.csv`，行内容照抄文档表 6-1（26 条，无 PV 用例）。
5. 新建 `run_injection.m`（或扩展 `run_benchmark.m`）：
   - 对 tests.csv × 策略 循环，从对应快照起跑到 1.3 s，按文档第 7 节时序。
   - 按文档第 8 节三个窗口计算指标（含 `P_charge`、`state`、`t_switch`、`D_dcdc`、功率保持率），写 `results/emi/<test_id>_<variant>.csv`，1 MHz Iac 另存 `_iac.csv`，合并到 `results/emi/scorecard.csv`（列见表 9-10）。
   - 生成文档表 9-8 所列的实测图，文件名与 `docs/figures/` 中的预计图对应。
6. 跑 B1 链路验证（E-DC-01b、E-AC-02b、E-BAT-01b 各一次 CRPR），核对文档表 9-2、9-5、9-7 的"预计"值，偏差超过 5% 先查注入块、充电级参数与快照。
7. 再跑 P1（54 次），然后 P2（102 次）。

## 运行约束

- 本机与其他项目共用：并行 MATLAB 进程不超过 3 个，用 `nice -n 10`，先看 `uptime` / `free -g`。
- 单次 0.7 s 仿真约 7 分钟；不要在 InitFcn 里放注入参数默认值以外的逻辑。
- `ENABLE_HIL = 0` 时在内存中注释掉 `EV System/PFC Control` 的 HIL TCP/IP 块（run_benchmark 已有此段），不要保存带临时修改的模型。
- 模型修改后用 `save_system` 保存，提交时附带更新 `docs/EMI_INJECTION_TEST_PLAN.md` 中受影响的表和图。

## 结果回填

仿真完成后，把文档第 9 节表中的 [预] / [待] 值替换为实测值并标 [实]，用实测图替换 `docs/figures/` 中的预计图，同时更新 `docs/EMI_INJECTION_TEST_PLAN.md`；scorecard 是最终对比图的数据源。
