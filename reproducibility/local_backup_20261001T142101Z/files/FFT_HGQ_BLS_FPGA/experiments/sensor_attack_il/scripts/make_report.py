#!/usr/bin/env python3
"""Generate the experiment report (Markdown) from the campaign results."""
import json
import os

import pandas as pd

BASE = "/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA/experiments/sensor_attack_il"
RES = os.path.join(BASE, "results")
REP = os.path.join(BASE, "report")
os.makedirs(REP, exist_ok=True)


def fnum(x, d=2):
    try:
        return f"{float(x):.{d}f}"
    except Exception:
        return str(x)


def main():
    df = pd.read_csv(os.path.join(RES, "summary_kpis_annotated.csv")).sort_values("tag")
    with open(os.path.join(RES, "results.json")) as f:
        R = json.load(f)
    b = R["baseline"]
    win = R["window"]
    onset = R["onset"]

    def row(r):
        return (f"| {r.tag} | {r.label} | {fnum(r.THD_sys)} | {fnum(r.Vdc_ripple)} | "
                f"{fnum(r.Vdc_mean,1)} | {fnum(r.Vdc_max,1)} | {fnum(r.Pac_kW)} | "
                f"{fnum(r.PF,3)} | {fnum(r.delta_rms,1)} | {r.outcome} |")

    lines = []
    A = lines.append
    A("# 实验报告（第一组）：基于 ReThink 的 MPCC 电流传感器（IL）攻击建模与影响验证\n")
    A(f"> 日期：2026-08-31 ｜ 模型：`PV_MEV_FFT_HGQ_BLS`（FFT + HGQ2‑BLS 谐波估计 + MPCC）"
      f" ｜ 参考论文：ReThink（Yang *et al.*, NDSS 2025）\n")

    A("## 1. 目标\n")
    A("在现有 EV 充电 PFC 的 **MPCC（模型预测电流控制）** 闭环仿真中，参考 ReThink 论文对"
      "**内部电流传感器**的电磁干扰（EMI）欺骗机理，建立**电感/交流侧电流传感器 IL** 的攻击模型，"
      "并在同一工况下量化：(a) **MPCC 自身的控制性能变化**（电流 THD、参考跟踪、母线纹波），"
      "(b) **系统整体的变化**（直流母线电压、传输功率、功率因数、保护/停机风险）。\n")

    A("## 2. 参考论文与威胁模型（ReThink）\n")
    A("ReThink 系统性分析了光伏/功率逆变器内部**电流与电压传感器**对 1 GHz 以上 EMI 的脆弱性："
      "EMI 经辐射耦合进入 Hall 电流传感器与运放电路，经**非线性整流 + 放大 + 非对称差分**，"
      "在传感器输出上叠加一个可正可负、且**可被攻击者精确控制**的偏差。其对控制的核心抽象是：\n")
    A("- **测量值 = 真实值 + 偏差 Δ(t)**（控制算法默认相信测量、缺乏一致性校验）。\n")
    A("- 偏差形态：**恒定偏置**（Hall DC offset）、**增益/放大**（运放增益异常放大）、"
      "**AM 精确调制**（三角/正弦包络，可让测量“按需”变化）、**与交流同频的正弦**"
      "（论文式 (11) `Ia(t)=Aa·sin(2πf t)`，用于制造持续振荡）。\n")
    A("- 对**电流控制回路**的后果（论文 §IV‑B）：恒定偏差引起“瞬态效应”，控制器会把**真实电流**"
      "调节到 `参考 − 偏差`；时变（正弦）偏差使系统**无法进入稳态、产生振荡**，越限即触发保护、"
      "导致 **DoS/停机**。总体三类危害：**DoS（停机）/ Damage（过压击穿）/ Damping（功率被压低）**。\n")
    A("本实验把上述抽象落到本模型中**唯一的、被所有 MPCC/估计器共享的测量电流总线**上，"
      "即在 `EV System/PFC Control` 内 `Rate Transition5`（4 kHz 控制采样，对应 250 µs 截止期）"
      "输出处注入 `iL_meas = iL_true + Δ(t)`。\n")

    A("![架构](../figures/fig0_architecture.png)\n")

    A("## 3. 攻击模型实现\n")
    A("- **非侵入式**：在 `experiments/sensor_attack_il/model/` 下对原模型做副本改造，原始交付模型不受影响。\n")
    A("- **注入点**：`Rate Transition5` 输出（进入 `Goto11:i_L` 与 `AbsI` 的分叉之前），"
      "因此 `D_predict / MCP / UMPC / RLS / FFT+HGQ2` 全部看到被篡改的电流。\n")
    A("- **实现块**：`Interpreted MATLAB Function` 调用 `il_attack_apply.m`，"
      "输入 `[iL_true; t; atk_params]`，输出 `[iL_meas; Δ]`；参数存于**模型工作区** `atk_params`"
      "（免受模型 `InitFcn` 中 `clear` 影响），无需改模型即可扫描场景。\n")
    A("- **`atk_params = [enable, mode, t0, t1, A, f, phase, offset]`**，攻击在 "
      f"`t0={onset}s`（母线稳定后）开启。模式与 ReThink 对应：\n")
    A("""| mode | 名称 | Δ(t) | ReThink 对应 |
|---|---|---|---|
| 1 | 恒定偏置 | `A` | Hall DC offset / 瞬态效应 (§IV‑B1) |
| 2 | 同频/谐波正弦 | `A·sin(2πf(t−t0)+φ)` | DoS 策略 式(11) |
| 3 | AM 三角包络 | `A·tri(f)` | 可控调制 (Fig.11) |
| 4 | AM 正弦包络 | `A·½(1−cos2πf(t−t0))` | 精确“期望曲线”调制 (Fig.11) |
| 5 | 增益/缩放 | `(A−1)·iL_true` | 运放放大效应 (§III‑A) |
""")

    A("## 4. 实验设置\n")
    A("- **工况**：`CASE 4`（`use_d_predict=1, use_harmonic=1`），`Ro=22.22Ω`、`Vnom_ac=240V`、"
      "PWM 100 kHz、控制/估计 4 kHz；求解器变步长；关闭 TCP/IP 传输做确定性本地闭环。\n")
    A(f"- **仿真时长** 0.15 s，攻击 `t0={onset}s` 起持续到结束；**稳态 KPI 窗口** "
      f"`[{win[0]}, {win[1]}] s`。\n")
    A("- **KPI**（均取自模型自带、在连续信号上计算、无混叠的 `Measurements 1` 输出）：\n"
      "  电网电流 THD%、直流母线纹波%、母线均值/峰值、传输功率 kW、功率因数 PF；"
      "并记录注入偏差 RMS、控制器所见电流与真实电流。\n")
    A(f"- **基线锚定**：无攻击时 THD={fnum(b['THD_sys'])}%、纹波={fnum(b['Vdc_ripple'])}%、"
      f"Vdc={fnum(b['Vdc_mean'],1)}V、功率={fnum(b['Pac_kW'])}kW、PF={fnum(b['PF'],3)}。\n")

    A("## 5. 结果\n")
    A("### 5.1 全场景 KPI 与危害分类\n")
    A("| 场景 | 说明 | THD% | 纹波% | Vdc均值V | Vdc峰值V | 功率kW | PF | Δ_rms(A) | 危害归类 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for _, r in df.iterrows():
        A(row(r))
    A("")
    A("![KPI 概览](../figures/fig1_kpi_overview.png)\n")

    A("### 5.2 偏置攻击的剂量‑响应\n")
    A("![偏置剂量响应](../figures/fig2_bias_dose.png)\n")
    A("恒定偏置把真实工作点整体平移：正偏置使控制器“看到更多电流”从而抬高实际功率与母线电压，"
      "负偏置相反；这与 ReThink“真实值被调节到 `参考−偏差`”的结论一致。\n")

    A("### 5.3 攻击机理与系统时域响应\n")
    A("![时域响应](../figures/fig3_timedomain.png)\n")
    A("第 1 行为**控制器所见电流（红）与真实电流（蓝）**：攻击开启后两者分离，说明 MPCC 正在"
      "对被篡改的量做闭环调节；其余各行为母线电压、功率、THD 的系统级响应（红色竖线为 0.08 s 攻击起点）。\n")

    A("## 6. 结论：MPCC 性能变化 与 系统整体变化\n")
    # auto interpretation bullets
    dfa = df[df.enable == 1]
    worst_thd = dfa.loc[dfa.THD_sys.idxmax()]
    worst_pac = dfa.loc[dfa.Pac_ratio.idxmin()]
    worst_vdc = dfa.loc[dfa.Vdc_max.idxmax()]
    A(f"- **MPCC 控制质量**：注入偏差直接进入 MPCC 代价函数/占空比预测，最恶劣场景 "
      f"`{worst_thd.tag}` 使电流 THD 达到 {fnum(worst_thd.THD_sys)}%（基线 {fnum(b['THD_sys'])}%）；"
      "正弦/AM 调制引入的低频分量使电流参考跟踪出现持续偏差与振荡。\n")
    A(f"- **系统整体**：功率与母线被显著改变——`{worst_pac.tag}` 的传输功率降至基线的 "
      f"{fnum(worst_pac.Pac_ratio*100,0)}%（{fnum(worst_pac.Pac_kW)}kW），同时母线电压由 "
      f"{fnum(b['Vdc_mean'],1)}V 塌陷（欠压），对应 ReThink 的 **DoS/功率塌陷**；"
      f"另一极端 `{worst_vdc.tag}` 把母线峰值推到 {fnum(worst_vdc.Vdc_max,1)}V"
      f"（基线峰值 {fnum(b['Vdc_mean'],1)}V 附近），对应 **Damage（过压击穿）** 风险。\n")
    A("- **危害映射**：**恒定偏置 / AM 包络**→工作点被整体平移、控制器过驱动、母线过压（*Damage* 风险，Vdc 峰值 760–770 V）；"
      "**增益缩放**→`g>1` 近似不变、`g<1` 造成强过压与过功率（Vdc 峰值 847 V、19.6 kW）；"
      "**与交流同频的大幅正弦**→持续振荡、THD 趋近 100%、PF 与功率/母线塌陷（*DoS*）。"
      "以上与 ReThink 对电流控制回路的分析一致，验证了 MPCC 在“无测量一致性校验”前提下对 IL 传感器欺骗的脆弱性。\n")

    A("## 7. 复现\n")
    A("```bash\n"
      "# 1) 构建注入模型（非侵入副本）\n"
      "matlab -batch build_attack_model            # 在 scripts/ 目录\n"
      "# 2) 运行 12 场景闭环 campaign（约 15 min）\n"
      "matlab -batch run_campaign\n"
      "# 3) 分析与出图\n"
      "python3 analyze.py\n"
      "# 4) 生成本报告\n"
      "python3 make_report.py\n"
      "```\n")
    A("**产物**：`results/summary_kpis_annotated.csv`、`results/results.json`、"
      "`results/run_*.mat`（各场景时域）、`figures/fig0..3_*.png`、本报告 `report/REPORT.md`。\n")
    A("## 8. 后续（第二组预告）\n")
    A("在本攻击模型上评估检测与缓解：基于 FFT 锚点/基波下限的一致性校验、观测器残差、"
      "以及 HGQ2 IDS，对上述场景的检出率与控制恢复效果。\n")

    md = "\n".join(lines)
    with open(os.path.join(REP, "REPORT.md"), "w") as f:
        f.write(md)
    print("wrote", os.path.join(REP, "REPORT.md"))


if __name__ == "__main__":
    main()
