#!/usr/bin/env python3
"""Build a reviewable Chinese DOCX: corrected report + charts + next-phase plan."""
import json
import os

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

BASE = "/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA/experiments/sensor_attack_il"
RES = os.path.join(BASE, "results_MPCC")
FIGM = os.path.join(BASE, "figures_MPCC")
FIGMODE = os.path.join(BASE, "figures_modes")
FIG0 = os.path.join(BASE, "figures", "fig0_architecture.png")
OUT = os.path.join(BASE, "report", "IL传感器攻击实验报告_第一组.docx")

CJK = "Microsoft YaHei"
ACCENT = RGBColor(0xC1, 0x36, 0x2E)
INK = RGBColor(0x20, 0x20, 0x20)
MUT = RGBColor(0x66, 0x66, 0x66)


def set_cjk(doc):
    st = doc.styles["Normal"]
    st.font.name = CJK
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), CJK)
    for s in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        try:
            doc.styles[s].font.name = CJK
            doc.styles[s].element.rPr.rFonts.set(qn("w:eastAsia"), CJK)
        except Exception:
            pass


def cjk_run(run):
    run.font.name = CJK
    r = run._element
    r.rPr.rFonts.set(qn("w:eastAsia"), CJK)


def para(doc, text, size=10.5, color=INK, bold=False, italic=False, align=None, space_after=6):
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.font.color.rgb = color
    r.bold = bold
    r.italic = italic
    cjk_run(r)
    p.paragraph_format.space_after = Pt(space_after)
    return p


def bullet(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    r = p.add_run(text)
    r.font.size = Pt(size)
    cjk_run(r)
    return p


def fig(doc, path, caption, width=Cm(16)):
    if not os.path.exists(path):
        para(doc, f"[缺图: {os.path.basename(path)}]", color=MUT, italic=True)
        return
    doc.add_picture(path, width=width)
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    c = para(doc, caption, size=9, color=MUT, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)
    return c


def sevbadge(o):
    o = o.lower()
    if "dos" in o:
        return "DoS 塌陷", RGBColor(0xC1, 0x36, 0x2E)
    if "damage" in o or "over-voltage" in o:
        return "过压 Damage", RGBColor(0xB7, 0x79, 0x1F)
    if "damping" in o:
        return "Damping", RGBColor(0xB7, 0x79, 0x1F)
    if "quality" in o:
        return "质量劣化", RGBColor(0xB7, 0x79, 0x1F)
    if "marginal" in o or "recovered" in o:
        return "边际/恢复", RGBColor(0x2F, 0x8A, 0x57)
    return "基线", MUT


def style_table(t):
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER


def hdr_cell(cell, text):
    cell.text = ""
    r = cell.paragraphs[0].add_run(text)
    r.bold = True
    r.font.size = Pt(9)
    cjk_run(r)


def cell_txt(cell, text, size=9, color=INK, bold=False):
    cell.text = ""
    r = cell.paragraphs[0].add_run(str(text))
    r.font.size = Pt(size)
    r.font.color.rgb = color
    r.bold = bold
    cjk_run(r)


def main():
    df = pd.read_csv(os.path.join(RES, "summary_kpis_annotated.csv")).sort_values("tag")
    with open(os.path.join(RES, "results.json")) as f:
        R = json.load(f)
    b = R["baseline"]
    onset = R["onset"]
    dfa = df[df.enable == 1]
    wthd = dfa.loc[dfa.THD_sys.idxmax()]
    wpac = dfa.loc[dfa.Pac_ratio.idxmin()]
    wvdc = dfa.loc[dfa.Vdc_max.idxmax()]

    doc = Document()
    set_cjk(doc)
    for s in doc.sections:
        s.top_margin = Cm(2); s.bottom_margin = Cm(2)
        s.left_margin = Cm(2.2); s.right_margin = Cm(2.2)

    # Title
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = tp.add_run("EV 充电 PFC 中 MPCC 电流传感器（IL）攻击建模与影响验证")
    tr.bold = True; tr.font.size = Pt(17); tr.font.color.rgb = ACCENT; cjk_run(tr)
    sp = doc.add_paragraph(); sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sp.add_run("第一组实验报告（修正版）｜ 参考论文：ReThink (NDSS 2025)")
    sr.font.size = Pt(11); sr.font.color.rgb = MUT; cjk_run(sr)
    mp = doc.add_paragraph(); mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    mr = mp.add_run("日期：2026-09-01 ｜ 模型：PV_MEV_FFT_HGQ_BLS ｜ 主模式：校准 MPCC-D (Ts=50 µs)")
    mr.font.size = Pt(9); mr.font.color.rgb = MUT; cjk_run(mr)
    doc.add_paragraph()

    # 摘要
    doc.add_heading("摘要", level=1)
    para(doc, "本实验在现有 EV 充电 PFC 的模型预测电流控制（MPCC）闭环仿真中，参考 ReThink 论文对逆变器"
              "内部电流/电压传感器的电磁干扰（EMI）欺骗机理，建立了电感/交流侧电流传感器 IL 的攻击模型"
              "（测量值 = 真实值 + Δ(t)），并量化了 MPCC 控制性能与系统整体在攻击下的变化。经核对配置注释，"
              "将基线修正到真正的校准 MPCC 工作点（Ts_Control=50 µs，THD≈7.6%），在此干净基线上完成 12 个"
              "攻击场景的闭环验证，覆盖 ReThink 的 DoS / Damage / Damping 三类危害。")

    # 0 修正说明
    doc.add_heading("0  控制模式与工作点（重要修正）", level=1)
    para(doc, "上一版误将 71% THD 当作基线。核对 init_paras.m 的配置注释与实测后确认：71% 是 MPCC 运行在"
              "错误采样率 Ts_Control=10 µs 下的失配工作点（init_paras 早段 Fc=100e3 设定 Ts_Control=1/Fc，"
              "后段 Fc=20e3 未重算，遗留 10 µs）。注意 Fc 并非模型变量，仅在初始化里换算 Ts_Control；真正的"
              "控制旋钮是 Ts_Control。六配置实测如下：")
    modes = [
        ("模式", "标志", "Ts_Control", "THD %", "功率 kW", "Vdc V", "说明"),
        ("普通 PFC / CRPR", "flags=0", "50 µs", "170–284", "3.9", "~400", "不稳定：欠压、无法升压"),
        ("MPCC-D（校准）", "d=1", "50 µs", "7.6", "14.7", "~800", "✔ 工作点，低 THD"),
        ("MPCC-D", "d=1", "10 µs", "71.8", "10.0", "650", "失配（Ts 太快）→ 高 THD"),
        ("MPCC-D + 谐波(CASE4)", "d=1,h=1", "50 µs", "11–16", "14.8", "773", "ONNX 谐波批处理未生效"),
        ("MPCC-D + 谐波", "d=1,h=1", "10 µs", "71.9", "10.0", "651", "失配 → 高 THD"),
    ]
    t = doc.add_table(rows=1, cols=7); style_table(t)
    for i, h in enumerate(modes[0]):
        hdr_cell(t.rows[0].cells[i], h)
    for row in modes[1:]:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cell_txt(cells[i], v)
    doc.add_paragraph()
    para(doc, f"结论：校准 MPCC 工作点 = MPCC-D 预测电流控制、Ts_Control=50 µs（20 kHz），"
              f"基线 THD≈{b['THD_sys']:.1f}%、功率 {b['Pac_kW']:.1f} kW、Vdc {b['Vdc_mean']:.0f} V"
              f"（对应文档 CASE 3 的 6.1%）。普通 PFC/CRPR 在当前模型参数下不稳定，不能作为干净基线，"
              f"本报告据实标注，攻击分析以校准 MPCC 为主。", bold=False)
    fig(doc, os.path.join(FIGMODE, "fig_mode_baselines.png"),
        "图 0. 两控制模式基线（无攻击）：校准 MPCC 稳定工作（~8% THD、Vdc 升压至 ~800 V）；普通 CRPR 无法升压/稳定。")

    # 1 威胁模型
    doc.add_heading("1  威胁模型与攻击注入", level=1)
    para(doc, "ReThink 揭示逆变器内部电流/电压传感器对 >1 GHz EMI 的脆弱性：EMI 经辐射耦合进入 Hall 传感器"
              "与运放电路，经非线性整流、放大、非对称差分，在传感器输出叠加可正可负、可精确控制的偏差。"
              "对电流控制回路的后果（论文 §IV-B）：恒定偏差引起“瞬态效应”，控制器把真实电流调节到"
              "“参考 − 偏差”；时变（正弦）偏差使系统无法进入稳态、产生振荡、越限触发保护。三类危害：DoS（停机）、"
              "Damage（过压击穿）、Damping（功率被压低）。")
    para(doc, "本实验在模型中唯一、被所有 MPCC/估计器共享的测量电流总线上注入：即 PFC Control 内 "
              "Rate Transition5（4 kHz 控制采样）输出、Goto11:i_L 与 AbsI 分叉之前，施加 iL_meas = iL_true + Δ(t)。"
              "五种攻击模式与论文对应：①恒定偏置(Hall DC offset)；②同频/谐波正弦(式11 DoS)；"
              "③AM 三角包络、④AM 正弦包络(Fig.11 可控调制)；⑤增益/缩放(运放放大)。")
    fig(doc, FIG0, "图 1. IL 电流传感器攻击注入结构：闭环使真实电流跟踪被欺骗的测量值。")

    # 2 设置
    doc.add_heading("2  实验设置（校准 MPCC）", level=1)
    para(doc, f"MPCC-D、Ts_Control=50 µs、Ro=22.22 Ω、Vnom_ac=240 V、PWM 100 kHz；仿真 0.22 s，"
              f"攻击 t₀={onset:.2f} s 起持续到结束，稳态 KPI 窗口 [0.16, 0.22] s；攻击幅值按本模式电流量级"
              f"（Iref rms≈70 A）标定。所有 KPI 取自模型自带、在连续信号上计算（无混叠）的 Measurements 1："
              f"电网电流 THD%、母线纹波%、母线均值/峰值、传输功率 kW、功率因数 PF。")

    # 3 结果
    doc.add_heading("3  实验结果与数据图表（校准 MPCC 下的攻击）", level=1)
    para(doc, f"基线：THD={b['THD_sys']:.2f}% ｜ 纹波={b['Vdc_ripple']:.2f}% ｜ Vdc={b['Vdc_mean']:.0f} V ｜ "
              f"功率={b['Pac_kW']:.2f} kW ｜ PF={b['PF']:.3f}", bold=True)
    cols = ["场景", "说明", "THD%", "纹波%", "Vdc̄V", "Vdc↑V", "功率kW", "PF", "Δrms", "危害"]
    t = doc.add_table(rows=1, cols=len(cols)); style_table(t)
    for i, h in enumerate(cols):
        hdr_cell(t.rows[0].cells[i], h)
    for _, r in df.iterrows():
        badge, bc = sevbadge(r.outcome)
        cells = t.add_row().cells
        vals = [r.tag.replace("S", "").split("_", 1)[-1] if "_" in r.tag else r.tag,
                r.label, f"{r.THD_sys:.1f}", f"{r.Vdc_ripple:.2f}", f"{r.Vdc_mean:.0f}",
                f"{r.Vdc_max:.0f}", f"{r.Pac_kW:.2f}", f"{r.PF:.3f}", f"{r.delta_rms:.0f}"]
        for i, v in enumerate(vals):
            cell_txt(cells[i], v)
        cell_txt(cells[-1], badge, color=bc, bold=True)
    doc.add_paragraph()
    fig(doc, os.path.join(FIGM, "fig1_kpi_overview.png"),
        f"图 2. 各场景稳态 KPI（虚线为校准基线 {b['THD_sys']:.1f}% THD）。")
    fig(doc, os.path.join(FIGM, "fig2_bias_dose.png"),
        "图 3. 偏置攻击剂量-响应：直流偏置抬高实际功率与母线电压（控制器被骗过驱动）。")
    fig(doc, os.path.join(FIGM, "fig3_timedomain.png"),
        "图 4. 攻击机理与系统时域响应：行 1 为控制器所见电流（红）vs 真实电流（蓝），攻击开启后分离。")

    # 4 结论
    doc.add_heading("4  结论：MPCC 与系统整体变化", level=1)
    bullet(doc, f"MPCC 控制质量：干净基线 THD 仅 {b['THD_sys']:.1f}%；攻击后最恶劣场景 "
                f"{wthd.tag} 升至 {wthd.THD_sys:.1f}%（约 ×{wthd.THD_sys/max(b['THD_sys'],1e-6):.1f}），"
                f"电流参考跟踪被破坏。")
    bullet(doc, f"系统整体：{wpac.tag} 功率降至基线 {wpac.Pac_ratio*100:.0f}%（{wpac.Pac_kW:.2f} kW）；"
                f"{wvdc.tag} 母线峰值 {wvdc.Vdc_max:.0f} V（基线 {b['Vdc_max']:.0f} V）→ 过压 Damage 风险。")
    bullet(doc, "危害映射（ReThink）：偏置/AM→工作点平移与过压（Damage）；缩放→功率被压低/抬升；"
                "同频正弦→振荡、THD 恶化、功率/母线塌陷（DoS）。")
    bullet(doc, "相比失配的 71% 工作点，从干净的 ~8% 基线出发，攻击导致的相对劣化更清晰、结论更可靠，"
                "且与 ReThink 对电流控制回路的分析一致，验证了 MPCC 在“无测量一致性校验”下对 IL 传感器欺骗的脆弱性。")

    # 5 下一阶段计划
    doc.add_heading("5  下一阶段实验计划", level=1)
    doc.add_heading("第二组：攻击检测与缓解（IDS）", level=2)
    bullet(doc, "一致性校验：基于 FFT 锚点 + 基波下限的测量一致性检查（真实/测量电流的残差门限、基波幅值下限保护）。")
    bullet(doc, "观测器/残差检测：基于 L_PFC、C_PFC 电路模型的电流观测器，比较预测电流与测量电流的残差，识别偏置/正弦/缩放注入。")
    bullet(doc, "AI-IDS：接入已有 src/sensor_ids 框架（HGQ2 检测器），对本报告 12 个场景做窗口级分类。")
    bullet(doc, "评价指标：检出率 (TPR)、误报率 (FPR)、检测延迟、以及缓解后控制恢复（THD/Vdc/功率回到基线的时间与残差）。")
    doc.add_heading("第三组：普通 PFC/CRPR 稳定基线与对照", level=2)
    bullet(doc, "先整定 CRPR 电压环（Vref/PI/Limit_V）使其稳定升压至额定母线，复现文档 CASE 1 (~70% THD) 的可用基线。")
    bullet(doc, "在稳定 CRPR 上重复相同攻击集，对比 MPCC 与传统线性控制对 IL 欺骗的鲁棒性差异。")
    doc.add_heading("第四组：攻击面扩展与联合攻击", level=2)
    bullet(doc, "多传感器协同：IL 与直流母线电压 Vdc、并网电压 Vac 传感器联合欺骗，验证 ReThink 的 many-to-many 场景。")
    bullet(doc, "谐波/AM 精确操控：复现 ReThink “期望曲线”式 AM 注入，评估对 MPCC 谐波补偿(FFT+HGQ2)的针对性攻击。")
    bullet(doc, "扩展到三相并网逆变器（PV System VSC），验证 Clarke/Park 变换下“非对称注入”才生效的结论。")
    doc.add_heading("第五组：硬件在环 / FPGA 验证", level=2)
    bullet(doc, "在 250 µs deadline 约束下，于 PIL/HIL 与 FPGA 部署上复现攻击与检测，评估实时性与资源开销。")

    # 6 复现
    doc.add_heading("6  复现与产物", level=1)
    para(doc, "脚本（experiments/sensor_attack_il/scripts）：build_attack_model.m（注入模型，非侵入副本）→ "
              "baseline_modes.m（六配置基线诊断）→ run_campaign_mode('MPCC')（校准 MPCC 攻击 campaign）→ "
              "analyze_mode.py MPCC（KPI+分类+出图）→ build_docx.py（本文档）。", size=9.5)
    para(doc, "产物：results_MPCC/summary_kpis_annotated.csv、results.json、run_*.mat（各场景时域）、"
              "figures_MPCC/fig1-3、figures_modes/fig_mode_baselines、report/（本 docx + HTML 报告）。", size=9.5)

    doc.save(OUT)
    print("wrote", OUT, f"({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
