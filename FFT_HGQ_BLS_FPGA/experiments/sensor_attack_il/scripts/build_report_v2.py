#!/usr/bin/env python3
"""Corrected two-mode experiment report (Markdown + self-contained HTML).
Reads results_MPCC (calibrated MPCC attack campaign) + mode-baseline diagnostics."""
import base64
import json
import os

import pandas as pd

BASE = "/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA/experiments/sensor_attack_il"
RES = os.path.join(BASE, "results_MPCC")
FIGM = os.path.join(BASE, "figures_MPCC")
FIGMODE = os.path.join(BASE, "figures_modes")
FIG0 = os.path.join(BASE, "figures", "fig0_architecture.png")
REP = os.path.join(BASE, "report")


def b64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def sevkey(o):
    o = o.lower()
    if "dos" in o:
        return "crit", "DoS 塌陷"
    if "damage" in o or "over-voltage" in o:
        return "warn", "过压 Damage"
    if "damping" in o:
        return "warn", "Damping"
    if "quality" in o:
        return "warn", "质量劣化"
    if "marginal" in o or "recovered" in o:
        return "ok", "边际/恢复"
    return "base", "基线"


def load():
    df = pd.read_csv(os.path.join(RES, "summary_kpis_annotated.csv")).sort_values("tag")
    with open(os.path.join(RES, "results.json")) as f:
        R = json.load(f)
    return df, R


def f(x, d=2):
    try:
        return f"{float(x):.{d}f}"
    except Exception:
        return str(x)


# --- diagnostic mode table (measured earlier) ---
MODES = [
    ("普通 PFC / CRPR", "flags=0", "50 µs", "284 / 170", "3.9", "~400", "不稳定，欠压、无法升压"),
    ("MPCC-D（校准）", "d=1", "50 µs", "7.4 → 8.3", "14.7", "~800", "✅ 工作点，低 THD"),
    ("MPCC-D", "d=1", "10 µs", "71.8", "10.0", "650", "失配（Ts 太快）→ 高 THD"),
    ("MPCC-D + 谐波(CASE4)", "d=1,h=1", "50 µs", "11 → 16", "14.8", "773", "ONNX 谐波在批处理未生效"),
    ("MPCC-D + 谐波", "d=1,h=1", "10 µs", "71.9", "10.0", "651", "失配 → 高 THD"),
]


def md(df, R):
    b = R["baseline"]
    onset = R["onset"]
    rows = []
    for _, r in df.iterrows():
        _, badge = sevkey(r.outcome)
        rows.append(f"| {r.tag} | {r.label} | {f(r.THD_sys)} | {f(r.Vdc_ripple)} | {f(r.Vdc_mean,0)} | "
                    f"{f(r.Vdc_max,0)} | {f(r.Pac_kW)} | {f(r.PF,3)} | {f(r.delta_rms,0)} | {badge} |")
    mrows = "\n".join(f"| {n} | `{fl}` | {ts} | {thd} | {p} | {v} | {note} |"
                      for n, fl, ts, thd, p, v, note in MODES)
    dfa = df[df.enable == 1]
    wthd = dfa.loc[dfa.THD_sys.idxmax()]
    wpac = dfa.loc[dfa.Pac_ratio.idxmin()]
    wvdc = dfa.loc[dfa.Vdc_max.idxmax()]
    L = []
    A = L.append
    A("# 实验报告（第一组·修正版）：ReThink IL 电流传感器攻击对 MPCC 与系统的影响\n")
    A("> 日期：2026-09-01 ｜ 模型：`PV_MEV_FFT_HGQ_BLS` ｜ 参考：ReThink (NDSS'25) ｜ "
      "控制模式：**校准 MPCC（工作点）** 为主，附**普通 PFC/CRPR** 对照\n")

    A("## 0. 修正说明（重要）\n")
    A("上一版把基线当成 71% THD——经核对 `init_paras.m` 的配置注释与实测，**71% 是 MPCC 跑在错误采样率 "
      "`Ts_Control=10 µs` 下的失配工作点**（`init_paras` 早段 `Fc=100e3` 设了 `Ts_Control=1/Fc`，后段 "
      "`Fc=20e3` 未重算，留下 10 µs 的遗留值）。注意 **`Fc` 不是模型变量**，只在 init 里换算 `Ts_Control`；"
      "真正的控制旋钮是 `Ts_Control`。各模式实测：\n")
    A("| 模式 | 标志 | Ts_Control | THD% | 功率kW | Vdc | 说明 |")
    A("|---|---|---|---|---|---|---|")
    A(mrows + "\n")
    A(f"**校准 MPCC 工作点 = MPCC-D 预测电流控制、`Ts_Control=50 µs`（20 kHz），基线 THD ≈ "
      f"{f(b['THD_sys'])}%、功率 {f(b['Pac_kW'])} kW、Vdc {f(b['Vdc_mean'],0)} V**（对应文档 CASE 3 的 6.1%）。"
      "普通 PFC/CRPR 在当前模型参数下不稳定（欠压、THD>150%），不能作为干净基线——本报告据实标注，"
      "攻击分析以校准 MPCC 为主。\n")
    A("![两模式基线](../figures_modes/fig_mode_baselines.png)\n")

    A("## 1. 威胁模型与注入（同前）\n")
    A("参考 ReThink：内部电流/电压传感器受 EMI 欺骗，`测量值 = 真实值 + Δ(t)`，控制器把真实电流调节到 "
      "`参考 − 偏差`，时变偏差致振荡/越限。注入点为 `PFC Control/Rate Transition5` 输出（所有 MPCC/估计器"
      "共享的测量电流总线之前），5 种模式：恒定偏置、同频/谐波正弦(式11)、AM 三角/正弦包络(Fig.11)、增益缩放。\n")
    A("![架构](../figures/fig0_architecture.png)\n")

    A("## 2. 设置（校准 MPCC）\n")
    A(f"MPCC-D、`Ts_Control=50 µs`、`Ro=22.22 Ω`、`Vnom_ac=240 V`、PWM 100 kHz；仿真 0.22 s，"
      f"攻击 `t₀={onset:.2f} s` 起，稳态窗口 `[0.16, 0.22] s`；攻击幅值按本模式电流量级"
      f"（Iref rms ≈ 70 A）标定。KPI 取自模型自带、连续信号上计算（无混叠）的 `Measurements 1`。\n")

    A("## 3. 结果（校准 MPCC 下的攻击）\n")
    A(f"基线：THD={f(b['THD_sys'])}% ｜ 纹波={f(b['Vdc_ripple'])}% ｜ Vdc={f(b['Vdc_mean'],0)}V ｜ "
      f"功率={f(b['Pac_kW'])}kW ｜ PF={f(b['PF'],3)}\n")
    A("| 场景 | 说明 | THD% | 纹波% | Vdc̄ V | Vdc↑ V | 功率kW | PF | Δrms A | 危害 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for line in rows:
        A(line)
    A("")
    A("![KPI 概览](../figures_MPCC/fig1_kpi_overview.png)\n")
    A("![偏置剂量响应](../figures_MPCC/fig2_bias_dose.png)\n")
    A("![时域响应](../figures_MPCC/fig3_timedomain.png)\n")

    A("## 4. 结论\n")
    A(f"- **MPCC 控制质量**：干净基线 THD 仅 {f(b['THD_sys'])}%；攻击后最恶劣 `{wthd.tag}` 升至 "
      f"{f(wthd.THD_sys)}%（×{f(wthd.THD_sys/max(b['THD_sys'],1e-6),1)}），电流参考跟踪被破坏。\n")
    A(f"- **系统整体**：`{wpac.tag}` 功率降至基线 {f(wpac.Pac_ratio*100,0)}%（{f(wpac.Pac_kW)}kW）；"
      f"`{wvdc.tag}` 母线峰值 {f(wvdc.Vdc_max,0)}V（基线 {f(b['Vdc_max'],0)}V）→ 过压 Damage 风险。\n")
    A("- **危害映射（ReThink）**：偏置/AM→工作点平移与过压（Damage）；缩放→功率被压低/抬升；"
      "同频正弦→振荡、THD 恶化、功率/母线塌陷（DoS）。相比失配的 71% 工作点，从干净的 8% 基线出发，"
      "攻击导致的相对劣化更清晰、结论更可靠。\n")

    A("## 5. 复现\n")
    A("```bash\n"
      "matlab -batch build_attack_model                 # 注入模型（非侵入副本）\n"
      "matlab -batch \"baseline_modes\"                   # 六配置基线诊断\n"
      "matlab -batch \"run_campaign_mode('MPCC')\"        # 校准 MPCC 攻击 campaign\n"
      "python3 analyze_mode.py MPCC                      # KPI+分类+出图\n"
      "python3 build_report_v2.py                        # 本报告\n"
      "```\n")
    open(os.path.join(REP, "REPORT.md"), "w").write("\n".join(L))
    print("wrote REPORT.md")
    return b, onset, rows, mrows, wthd, wpac, wvdc


def html(df, R, b, onset, wthd, wpac, wvdc):
    figs = {"arch": b64(FIG0), "modes": b64(os.path.join(FIGMODE, "fig_mode_baselines.png")),
            "kpi": b64(os.path.join(FIGM, "fig1_kpi_overview.png")),
            "bias": b64(os.path.join(FIGM, "fig2_bias_dose.png")),
            "td": b64(os.path.join(FIGM, "fig3_timedomain.png"))}
    trows = []
    for _, r in df.iterrows():
        cls, badge = sevkey(r.outcome)
        trows.append(f'<tr><td class="mono">{r.tag}</td><td>{r.label}</td>'
                     f'<td class="num">{f(r.THD_sys)}</td><td class="num">{f(r.Vdc_ripple)}</td>'
                     f'<td class="num">{f(r.Vdc_mean,0)}</td><td class="num strong">{f(r.Vdc_max,0)}</td>'
                     f'<td class="num">{f(r.Pac_kW)}</td><td class="num">{f(r.PF,3)}</td>'
                     f'<td class="num">{f(r.delta_rms,0)}</td><td><span class="chip {cls}">{badge}</span></td></tr>')
    mrows = "\n".join(
        f'<tr><td>{n}</td><td class="mono small">{fl}</td><td class="num">{ts}</td>'
        f'<td class="num">{thd}</td><td class="num">{p}</td><td class="num">{v}</td>'
        f'<td class="{"crit" if "不稳定" in note or "失配" in note or "未生效" in note else "ok"} small">{note}</td></tr>'
        for n, fl, ts, thd, p, v, note in MODES)
    page = f"""<title>MPCC 电流传感器攻击</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{{--bg:#eef1f5;--surface:#fff;--surface2:#f6f8fb;--ink:#15212e;--muted:#5c6b7a;--line:#d5dde6;
--accent:#d8382f;--measure:#1f7d8c;--ok:#2f8a57;--okbg:#e6f2ea;--warn:#b7791f;--warnbg:#f7ecd6;
--crit:#c1362e;--critbg:#f7dfdc;--basebg:#e6ebf1;--shadow:0 1px 2px rgba(20,33,46,.06),0 8px 24px rgba(20,33,46,.06);}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0c141c;--surface:#131f2a;--surface2:#0f1a24;
--ink:#e7eef4;--muted:#93a4b4;--line:#243545;--accent:#ef5b52;--measure:#57b6c6;--ok:#57b681;--okbg:#123024;
--warn:#e0a13c;--warnbg:#2e2413;--crit:#f0675e;--critbg:#331916;--basebg:#1b2836;--shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);}}}}
:root[data-theme="dark"]{{--bg:#0c141c;--surface:#131f2a;--surface2:#0f1a24;--ink:#e7eef4;--muted:#93a4b4;--line:#243545;
--accent:#ef5b52;--measure:#57b6c6;--ok:#57b681;--okbg:#123024;--warn:#e0a13c;--warnbg:#2e2413;--crit:#f0675e;--critbg:#331916;--basebg:#1b2836;--shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);}}
*{{box-sizing:border-box}}body{{background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.65;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:960px;margin:0 auto;padding:clamp(20px,4vw,52px) clamp(16px,4vw,40px) 80px}}
.mono{{font-family:"IBM Plex Mono",monospace}}.small{{font-size:.8rem}}.muted{{color:var(--muted)}}
header.head{{border-left:3px solid var(--accent);padding-left:18px;margin-bottom:26px}}
.eyebrow{{font-family:"IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.16em;font-size:.72rem;color:var(--accent);font-weight:600;margin:0 0 10px}}
h1{{font-size:clamp(1.5rem,3.4vw,2.15rem);font-weight:700;line-height:1.16;margin:0 0 14px;text-wrap:balance;letter-spacing:-.01em}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 10px;font-size:.8rem}}.meta span{{background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:4px 11px;color:var(--muted)}}.meta b{{color:var(--ink)}}
h2{{font-size:1.26rem;font-weight:700;margin:44px 0 8px;letter-spacing:-.01em;display:flex;gap:12px;align-items:baseline}}
h2 .n{{font-family:"IBM Plex Mono",monospace;font-size:.9rem;color:var(--accent)}}
h3{{font-size:1.02rem;font-weight:600;margin:24px 0 6px}}
p{{margin:.55em 0;max-width:70ch}}code{{font-family:"IBM Plex Mono",monospace;font-size:.86em;background:var(--surface2);border:1px solid var(--line);border-radius:5px;padding:.06em .38em}}
ul{{padding-left:1.1em;max-width:70ch}}li{{margin:.32em 0}}
.callout{{background:var(--warnbg);border:1px solid var(--warn);border-left:3px solid var(--warn);border-radius:10px;padding:14px 18px;margin:16px 0;font-size:.92rem}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden;margin:16px 0}}
.card img{{display:block;width:100%;height:auto}}.card figcaption{{padding:11px 16px;font-size:.82rem;color:var(--muted);border-top:1px solid var(--line);background:var(--surface2)}}.card figcaption b{{color:var(--ink)}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);margin:14px 0}}
table{{border-collapse:collapse;width:100%;font-size:.84rem;background:var(--surface);min-width:640px}}
th,td{{padding:8px 11px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}
thead th{{background:var(--surface2);font-weight:600;font-size:.74rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
tbody tr:last-child td{{border-bottom:none}}tbody tr:hover{{background:var(--surface2)}}
.num{{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}}.num.strong{{font-weight:600;color:var(--accent)}}
td.crit{{color:var(--crit)}}td.ok{{color:var(--ok)}}
.chip{{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:.72rem;font-weight:600;padding:2px 9px;border-radius:999px}}
.chip.crit{{background:var(--critbg);color:var(--crit)}}.chip.warn{{background:var(--warnbg);color:var(--warn)}}.chip.ok{{background:var(--okbg);color:var(--ok)}}.chip.base{{background:var(--basebg);color:var(--muted)}}
.kpibar{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}.kpibar .k{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:118px;box-shadow:var(--shadow)}}
.kpibar .k b{{display:block;font-size:1.2rem;font-weight:700;font-variant-numeric:tabular-nums}}.kpibar .k span{{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.verdicts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:18px 0}}
.v{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow);border-top:3px solid var(--vc,var(--accent))}}
.v .tag{{font-family:"IBM Plex Mono",monospace;font-size:.72rem;font-weight:600;color:var(--vc);text-transform:uppercase;letter-spacing:.08em}}
.v .big{{font-size:1.7rem;font-weight:700;margin:6px 0 2px;font-variant-numeric:tabular-nums;letter-spacing:-.02em}}.v .sub{{font-size:.82rem;color:var(--muted)}}
pre{{background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow-x:auto;font-family:"IBM Plex Mono",monospace;font-size:.8rem;line-height:1.6}}
.footnote{{font-size:.8rem;color:var(--muted)}}hr{{border:none;border-top:1px solid var(--line);margin:38px 0}}
</style>
<div class="wrap">
<header class="head"><p class="eyebrow">实验报告 · 第一组（修正版）</p>
<h1>ReThink IL 电流传感器攻击对校准 MPCC 与系统的影响</h1>
<div class="meta"><span>日期 <b>2026-09-01</b></span><span>模型 <b>PV_MEV_FFT_HGQ_BLS</b></span>
<span>主模式 <b>校准 MPCC-D · Ts=50µs</b></span><span>对照 <b>普通 PFC/CRPR</b></span><span>参考 <b>ReThink NDSS&#8217;25</b></span></div></header>

<div class="callout"><b>修正说明：</b>上一版的 71% THD 基线其实是 MPCC 跑在<b>错误采样率 <code>Ts_Control=10 µs</code></b>下的失配工作点
（<code>init_paras</code> 早段 <code>Fc=100e3</code> 设定的遗留值）。<code>Fc</code> 不是模型变量，只用于换算 <code>Ts_Control</code>。
真正的<b>校准 MPCC 工作点为 <code>Ts_Control=50 µs</code>（20 kHz），基线 THD ≈ {f(b['THD_sys'])}%</b>，功率 {f(b['Pac_kW'])} kW、
Vdc {f(b['Vdc_mean'],0)} V。攻击分析以此为主；普通 PFC/CRPR 在当前参数下不稳定，仅作对照。</div>

<div class="kpibar">
<div class="k"><b>{f(b['THD_sys'])}%</b><span>校准基线 THD</span></div>
<div class="k"><b>{f(b['Vdc_ripple'])}%</b><span>母线纹波</span></div>
<div class="k"><b>{f(b['Vdc_mean'],0)} V</b><span>Vdc</span></div>
<div class="k"><b>{f(b['Pac_kW'])} kW</b><span>功率</span></div>
<div class="k"><b>{f(b['PF'],3)}</b><span>PF</span></div></div>

<h2><span class="n">00</span> 控制模式与工作点</h2>
<div class="tablewrap"><table><thead><tr><th>模式</th><th>标志</th><th>Ts_Control</th><th>THD%</th><th>功率kW</th><th>Vdc</th><th>说明</th></tr></thead><tbody>{mrows}</tbody></table></div>
<div class="card"><figure><img alt="两模式基线" src="{figs['modes']}"><figcaption><b>图 0.</b> 两控制模式基线（无攻击）：校准 MPCC 稳定工作（~8% THD、Vdc 升压至 ~800 V、14.7 kW）；普通 CRPR 无法升压/稳定（THD&gt;150%、Vdc 塌至 ~400 V）。</figcaption></figure></div>

<h2><span class="n">01</span> 威胁模型与注入</h2>
<p>参考 ReThink：内部电流/电压传感器受 EMI 欺骗，<code>测量值 = 真实值 + Δ(t)</code>，控制器把真实电流调节到 <code>参考 − 偏差</code>，时变偏差致振荡/越限。注入点为 <code>PFC Control/Rate Transition5</code> 输出（所有 MPCC/估计器共享的测量电流总线之前）；5 种模式：恒定偏置、同频/谐波正弦(式11)、AM 三角/正弦包络(Fig.11)、增益缩放。</p>
<div class="card"><figure><img alt="架构" src="{figs['arch']}"><figcaption><b>图 1.</b> IL 电流传感器攻击注入结构：闭环使真实电流跟踪被欺骗的测量值。</figcaption></figure></div>

<h2><span class="n">02</span> 校准 MPCC 下的攻击结果</h2>
<div class="tablewrap"><table><thead><tr><th>场景</th><th>说明</th><th>THD%</th><th>纹波%</th><th>Vdc̄V</th><th>Vdc↑V</th><th>功率kW</th><th>PF</th><th>Δrms A</th><th>危害</th></tr></thead><tbody>{''.join(trows)}</tbody></table></div>
<div class="card"><figure><img alt="KPI 概览" src="{figs['kpi']}"><figcaption><b>图 2.</b> 各场景稳态 KPI（虚线为校准基线 {f(b['THD_sys'])}% THD）。</figcaption></figure></div>
<div class="card"><figure><img alt="偏置剂量响应" src="{figs['bias']}"><figcaption><b>图 3.</b> 偏置剂量-响应：直流偏置抬高实际功率与母线电压（控制器被骗过驱动）。</figcaption></figure></div>
<div class="card"><figure><img alt="时域响应" src="{figs['td']}"><figcaption><b>图 4.</b> 行 1 为控制器所见电流（红）vs 真实电流（蓝），攻击开启后分离；其余为 Vdc/功率/THD 系统响应。</figcaption></figure></div>

<h2><span class="n">03</span> 结论</h2>
<div class="verdicts">
<div class="v" style="--vc:var(--crit)"><div class="tag">最恶劣 THD</div><div class="big">{f(wthd.THD_sys)}%</div><div class="sub">{wthd.label}：相对干净基线 {f(b['THD_sys'])}% 放大 ×{f(wthd.THD_sys/max(b['THD_sys'],1e-6),1)}</div></div>
<div class="v" style="--vc:var(--warn)"><div class="tag">功率偏移</div><div class="big">{f(wpac.Pac_kW)} kW</div><div class="sub">{wpac.label}：降至基线 {f(wpac.Pac_ratio*100,0)}%</div></div>
<div class="v" style="--vc:var(--measure)"><div class="tag">母线峰值</div><div class="big">{f(wvdc.Vdc_max,0)} V</div><div class="sub">{wvdc.label}：基线 {f(b['Vdc_max'],0)} V → 过压 Damage 风险</div></div></div>
<ul>
<li><b>MPCC 控制质量</b>：干净基线 THD 仅 {f(b['THD_sys'])}%；攻击后最恶劣升至 {f(wthd.THD_sys)}%，参考跟踪被破坏。</li>
<li><b>系统整体</b>：功率与母线被显著改变，母线峰值最高 {f(wvdc.Vdc_max,0)} V（Damage 风险）；正弦型攻击可致功率/母线塌陷（DoS）。</li>
<li><b>相比失配的 71% 工作点，从干净的 8% 基线出发，攻击导致的相对劣化更清晰、结论更可靠</b>，且与 ReThink 对电流控制回路的分析一致。</li>
</ul>
<hr><p class="footnote"><b>后续（第二组）</b>：在本攻击模型上评估检测/缓解（FFT 锚点一致性校验、观测器残差、HGQ2 IDS）在校准 MPCC 下的检出率与恢复。CRPR 若要作为完整第二模式需先整定其电压环使之稳定升压。</p>
</div>
"""
    open(os.path.join(REP, "report.html"), "w").write(page)
    print("wrote report.html", f"({os.path.getsize(os.path.join(REP,'report.html'))/1024:.0f} KB)")


if __name__ == "__main__":
    df, R = load()
    b, onset, rows, mrows, wthd, wpac, wvdc = md(df, R)
    html(df, R, b, onset, wthd, wpac, wvdc)
