#!/usr/bin/env python3
"""Assemble a self-contained HTML report (figures embedded as data URIs)."""
import base64
import json
import os

import pandas as pd

BASE = "/mnt/data6/playground/RL4EV/FFT_HGQ_BLS_FPGA/experiments/sensor_attack_il"
FIG = os.path.join(BASE, "figures")
RES = os.path.join(BASE, "results")
OUT = os.path.join(BASE, "report", "report.html")


def b64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def sev(outcome):
    o = outcome.lower()
    if "dos" in o:
        return "crit", "DoS 塌陷"
    if "damage" in o or "over-voltage" in o:
        return "warn", "过压 Damage"
    if "damping" in o:
        return "warn", "Damping"
    if "marginal" in o or "recovered" in o:
        return "ok", "边际/恢复"
    return "base", "基线"


def main():
    df = pd.read_csv(os.path.join(RES, "summary_kpis_annotated.csv")).sort_values("tag")
    with open(os.path.join(RES, "results.json")) as f:
        R = json.load(f)
    b = R["baseline"]
    figs = {k: b64(os.path.join(FIG, v)) for k, v in {
        "arch": "fig0_architecture.png", "kpi": "fig1_kpi_overview.png",
        "bias": "fig2_bias_dose.png", "td": "fig3_timedomain.png"}.items()}

    rows = []
    for _, r in df.iterrows():
        cls, badge = sev(r.outcome)
        rows.append(f"""<tr>
<td class="mono">{r.tag.replace('_','&#8203;_')}</td><td>{r.label}</td>
<td class="num">{r.THD_sys:.1f}</td><td class="num">{r.Vdc_ripple:.2f}</td>
<td class="num">{r.Vdc_mean:.0f}</td><td class="num strong">{r.Vdc_max:.0f}</td>
<td class="num">{r.Pac_kW:.2f}</td><td class="num">{r.PF:.3f}</td>
<td class="num">{r.delta_rms:.0f}</td>
<td><span class="chip {cls}">{badge}</span></td></tr>""")
    table = "\n".join(rows)

    modes = [
        ("1", "恒定偏置", "A", "Hall DC offset / 瞬态效应 §IV-B1"),
        ("2", "同频·谐波正弦", "A·sin(2πf(t−t₀)+φ)", "DoS 策略 式(11)"),
        ("3", "AM 三角包络", "A·tri(f)", "可控调制 Fig.11"),
        ("4", "AM 正弦包络", "A·½(1−cos2πf(t−t₀))", "精确“期望曲线” Fig.11"),
        ("5", "增益 / 缩放", "(A−1)·iL_true", "运放放大效应 §III-A"),
    ]
    mrows = "\n".join(
        f'<tr><td class="mono">{m}</td><td>{n}</td><td class="mono small">{d}</td>'
        f'<td class="muted small">{c}</td></tr>' for m, n, d, c in modes)

    html = f"""<title>MPCC 电流传感器攻击</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{{
  --bg:#eef1f5; --surface:#ffffff; --surface2:#f6f8fb; --ink:#15212e; --muted:#5c6b7a;
  --line:#d5dde6; --accent:#d8382f; --measure:#1f7d8c; --ok:#2f8a57; --okbg:#e6f2ea;
  --warn:#b7791f; --warnbg:#f7ecd6; --crit:#c1362e; --critbg:#f7dfdc; --basebg:#e6ebf1;
  --shadow:0 1px 2px rgba(20,33,46,.06),0 8px 24px rgba(20,33,46,.06);
}}
:root:not([data-theme="light"]) {{ }}
@media (prefers-color-scheme: dark){{
  :root:not([data-theme="light"]){{
    --bg:#0c141c; --surface:#131f2a; --surface2:#0f1a24; --ink:#e7eef4; --muted:#93a4b4;
    --line:#243545; --accent:#ef5b52; --measure:#57b6c6; --ok:#57b681; --okbg:#123024;
    --warn:#e0a13c; --warnbg:#2e2413; --crit:#f0675e; --critbg:#331916; --basebg:#1b2836;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }}
}}
:root[data-theme="dark"]{{
  --bg:#0c141c; --surface:#131f2a; --surface2:#0f1a24; --ink:#e7eef4; --muted:#93a4b4;
  --line:#243545; --accent:#ef5b52; --measure:#57b6c6; --ok:#57b681; --okbg:#123024;
  --warn:#e0a13c; --warnbg:#2e2413; --crit:#f0675e; --critbg:#331916; --basebg:#1b2836;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  line-height:1.65;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:940px;margin:0 auto;padding:clamp(20px,4vw,52px) clamp(16px,4vw,40px) 80px}}
.mono{{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}}
.small{{font-size:.82rem}} .muted{{color:var(--muted)}}
header.head{{border-left:3px solid var(--accent);padding-left:18px;margin-bottom:34px}}
.eyebrow{{font-family:"IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.16em;
  font-size:.72rem;color:var(--accent);font-weight:600;margin:0 0 10px}}
h1{{font-size:clamp(1.55rem,3.6vw,2.25rem);font-weight:700;line-height:1.15;margin:0 0 14px;
  text-wrap:balance;letter-spacing:-.01em}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 10px;font-size:.8rem}}
.meta span{{background:var(--surface);border:1px solid var(--line);border-radius:999px;
  padding:4px 11px;color:var(--muted)}}
.meta b{{color:var(--ink);font-weight:600}}
h2{{font-size:1.28rem;font-weight:700;margin:46px 0 8px;letter-spacing:-.01em;
  display:flex;align-items:baseline;gap:12px}}
h2 .n{{font-family:"IBM Plex Mono",monospace;font-size:.9rem;color:var(--accent);font-weight:600}}
h3{{font-size:1.02rem;font-weight:600;margin:26px 0 6px;color:var(--ink)}}
p{{margin:.55em 0;max-width:68ch}}
a{{color:var(--measure)}}
code{{font-family:"IBM Plex Mono",monospace;font-size:.86em;background:var(--surface2);
  border:1px solid var(--line);border-radius:5px;padding:.06em .38em}}
.lead{{font-size:1.06rem;color:var(--ink)}}
ul{{padding-left:1.1em;max-width:68ch}} li{{margin:.32em 0}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);overflow:hidden;margin:16px 0}}
.card figure{{margin:0}} .card img{{display:block;width:100%;height:auto}}
.card figcaption{{padding:11px 16px;font-size:.82rem;color:var(--muted);
  border-top:1px solid var(--line);background:var(--surface2)}}
.card figcaption b{{color:var(--ink)}}
.tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;
  box-shadow:var(--shadow);margin:14px 0}}
table{{border-collapse:collapse;width:100%;font-size:.84rem;background:var(--surface);min-width:720px}}
th,td{{padding:8px 11px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}
thead th{{background:var(--surface2);font-weight:600;font-size:.75rem;text-transform:uppercase;
  letter-spacing:.05em;color:var(--muted);position:sticky;top:0}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:var(--surface2)}}
.num{{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}}
.num.strong{{font-weight:600;color:var(--accent)}}
.chip{{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:.72rem;font-weight:600;
  padding:2px 9px;border-radius:999px;white-space:nowrap}}
.chip.crit{{background:var(--critbg);color:var(--crit)}}
.chip.warn{{background:var(--warnbg);color:var(--warn)}}
.chip.ok{{background:var(--okbg);color:var(--ok)}}
.chip.base{{background:var(--basebg);color:var(--muted)}}
.verdicts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:18px 0}}
.v{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;
  box-shadow:var(--shadow);border-top:3px solid var(--vc,var(--accent))}}
.v .tag{{font-family:"IBM Plex Mono",monospace;font-size:.72rem;font-weight:600;color:var(--vc);
  text-transform:uppercase;letter-spacing:.08em}}
.v .big{{font-size:1.7rem;font-weight:700;margin:6px 0 2px;font-variant-numeric:tabular-nums;letter-spacing:-.02em}}
.v .sub{{font-size:.82rem;color:var(--muted)}}
.kpibar{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}
.kpibar .k{{background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:10px 14px;min-width:120px;box-shadow:var(--shadow)}}
.kpibar .k b{{display:block;font-size:1.25rem;font-weight:700;font-variant-numeric:tabular-nums}}
.kpibar .k span{{font-size:.74rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
pre{{background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:14px 16px;
  overflow-x:auto;font-family:"IBM Plex Mono",monospace;font-size:.8rem;line-height:1.6}}
hr{{border:none;border-top:1px solid var(--line);margin:40px 0}}
.footnote{{font-size:.8rem;color:var(--muted);margin-top:8px}}
</style>

<div class="wrap">
<header class="head">
  <p class="eyebrow">实验报告 · 第一组 / Group 1</p>
  <h1>基于 ReThink 的 MPCC 电流传感器（IL）攻击建模与影响验证</h1>
  <div class="meta">
    <span>日期 <b>2026-08-31</b></span>
    <span>模型 <b>PV_MEV_FFT_HGQ_BLS</b></span>
    <span>控制 <b>MPCC + FFT/HGQ2-BLS</b></span>
    <span>参考 <b>ReThink, NDSS&#8217;25</b></span>
    <span>场景 <b>12</b></span>
  </div>
</header>

<p class="lead">在现有 EV 充电 PFC 的 <b>MPCC（模型预测电流控制）</b> 闭环仿真中，参考 ReThink 论文对内部
电流传感器的电磁干扰（EMI）欺骗机理，建立<b>电感/交流侧电流传感器 IL</b> 的攻击模型，量化 MPCC
控制性能与系统整体在攻击下的变化。核心抽象：<code>测量值 = 真实值 + Δ(t)</code>——控制器默认相信被篡改的测量。</p>

<div class="kpibar">
  <div class="k"><b>{b['THD_sys']:.1f}%</b><span>基线 THD</span></div>
  <div class="k"><b>{b['Vdc_ripple']:.2f}%</b><span>基线母线纹波</span></div>
  <div class="k"><b>{b['Vdc_mean']:.0f} V</b><span>基线 Vdc</span></div>
  <div class="k"><b>{b['Pac_kW']:.2f} kW</b><span>基线功率</span></div>
  <div class="k"><b>{b['PF']:.3f}</b><span>基线 PF</span></div>
</div>

<h2><span class="n">01</span> 威胁模型（ReThink）</h2>
<p>ReThink 揭示功率逆变器内部电流/电压传感器对 &gt;1 GHz EMI 的脆弱性：EMI 经辐射耦合进入 Hall 传感器与
运放电路，经<b>非线性整流 + 放大 + 非对称差分</b>在输出上叠加一个可正可负、且可被攻击者精确控制的偏差。
对<b>电流控制回路</b>的后果（§IV-B）：恒定偏差引起“瞬态效应”，控制器把<b>真实电流</b>调节到
<code>参考 − 偏差</code>；时变（正弦）偏差使系统无法进入稳态、产生振荡、越限触发保护。三类危害：
<b>DoS（停机）/ Damage（过压击穿）/ Damping（功率被压低）</b>。</p>
<div class="card"><figure><img alt="攻击注入架构" src="{figs['arch']}">
<figcaption><b>图 0.</b> IL 电流传感器攻击注入结构：篡改被所有 MPCC/估计器共享的测量电流总线；闭环使
<b>真实电流跟踪被欺骗的测量值</b>。</figcaption></figure></div>

<h2><span class="n">02</span> 攻击模型实现</h2>
<p>非侵入式：在 <code>experiments/sensor_attack_il/model/</code> 下对交付模型做副本改造。注入点为
<code>EV System/PFC Control</code> 内 <code>Rate Transition5</code>（4 kHz 控制采样，250 µs 截止期）输出，
即 <code>Goto11:i_L</code> 与 <code>AbsI</code> 分叉之前，使 <code>D_predict / MCP / UMPC / RLS / FFT+HGQ2</code>
全部看到被篡改的电流。实现块为 <code>Interpreted MATLAB Function</code> 调用 <code>il_attack_apply.m</code>，
参数存于<b>模型工作区</b> <code>atk_params = [enable, mode, t₀, t₁, A, f, φ, offset]</code>（免受 <code>InitFcn</code>
中 <code>clear</code> 影响），无需改模型即可扫描场景。攻击在 <code>t₀ = 0.08 s</code>（母线稳定后）开启。</p>
<div class="tablewrap"><table>
<thead><tr><th>mode</th><th>名称</th><th>Δ(t)</th><th>ReThink 对应</th></tr></thead>
<tbody>{mrows}</tbody></table></div>

<h2><span class="n">03</span> 实验设置</h2>
<ul>
<li><b>工况</b> CASE 4（<code>use_d_predict=1, use_harmonic=1</code>），<code>Ro=22.22 Ω</code>、
<code>Vnom_ac=240 V</code>、PWM 100 kHz、控制/估计 4 kHz；变步长求解器；关闭 TCP/IP 做确定性本地闭环。</li>
<li><b>时长</b> 0.15 s，攻击 <code>t₀=0.08 s</code> 持续至结束；<b>稳态 KPI 窗口</b> <code>[0.10, 0.15] s</code>。</li>
<li><b>KPI</b> 取自模型自带、在连续信号上计算（无混叠）的 <code>Measurements 1</code>：电网电流 THD%、
母线纹波%、母线均值/峰值、传输功率 kW、功率因数 PF；并记录注入偏差 RMS 与控制器所见/真实电流。</li>
</ul>

<h2><span class="n">04</span> 结果</h2>
<h3>4.1 全场景 KPI 与危害分类</h3>
<div class="tablewrap"><table>
<thead><tr><th>场景</th><th>说明</th><th>THD%</th><th>纹波%</th><th>Vdc̄ V</th><th>Vdc↑ V</th>
<th>功率 kW</th><th>PF</th><th>Δ rms A</th><th>危害</th></tr></thead>
<tbody>{table}</tbody></table></div>
<p class="footnote">Vdc↑ = 稳态窗口内母线峰值；基线母线峰值约 {b['Vdc_mean']:.0f} V 附近。危害分类由功率比、
母线越限/塌陷阈值自动判定。</p>
<div class="card"><figure><img alt="KPI 概览" src="{figs['kpi']}">
<figcaption><b>图 1.</b> 各场景稳态 KPI（虚线为基线）。<b>sine A120 f50</b> 使 THD 冲至 98%、功率降至 3.8 kW、
PF 跌到 0.65；<b>scale g0.6</b> 把功率推到 19.6 kW、纹波 4.5%。</figcaption></figure></div>

<h3>4.2 偏置攻击剂量-响应</h3>
<div class="card"><figure><img alt="偏置剂量响应" src="{figs['bias']}">
<figcaption><b>图 2.</b> 恒定偏置的 V 形响应：任意方向的直流偏置都抬高实际功率与母线电压——控制器被“骗”得
过驱动，与 ReThink“真实值被调节到 参考 − 偏差”一致。</figcaption></figure></div>

<h3>4.3 攻击机理与系统时域响应</h3>
<div class="card"><figure><img alt="时域响应" src="{figs['td']}">
<figcaption><b>图 3.</b> 行 1 为<b>控制器所见电流（红）与真实电流（蓝）</b>：0.08 s 攻击开启后两者分离，
MPCC 对被篡改量做闭环调节。sine-120 使母线 650→490 V、功率塌陷（DoS）；scale-0.6 把母线推到 840 V（Damage）。</figcaption></figure></div>

<h2><span class="n">05</span> 结论：MPCC 与系统整体变化</h2>
<div class="verdicts">
  <div class="v" style="--vc:var(--crit)"><div class="tag">DoS / 塌陷</div>
    <div class="big">3.83 kW</div><div class="sub">sine 120 A@50 Hz：功率降至基线 39%，THD→98%，PF 0.65，母线欠压塌陷</div></div>
  <div class="v" style="--vc:var(--warn)"><div class="tag">Damage / 过压</div>
    <div class="big">847 V</div><div class="sub">scale ×0.6：母线峰值 847 V（基线 ~661 V），过压击穿风险</div></div>
  <div class="v" style="--vc:var(--measure)"><div class="tag">Damping / 平移</div>
    <div class="big">±60 A</div><div class="sub">偏置/AM：工作点整体平移、过驱动，功率 9.9→14.7 kW</div></div>
</div>
<ul>
<li><b>MPCC 控制质量</b>：注入偏差直接进入代价函数/占空比预测；最恶劣场景电流 THD 由 71.2% 升至 98.1%，
正弦/AM 引入的低频分量使参考跟踪出现持续偏差与振荡。</li>
<li><b>系统整体</b>：功率与母线被显著改变——sine-120 功率塌陷至 39% 且母线欠压（DoS）；
另一极端 scale-0.6 把母线峰值推到 847 V（Damage 过压）。</li>
<li><b>危害映射</b>：恒定偏置 / AM 包络 → 工作点平移、过驱动、母线过压（Damage，Vdc 峰值 760–770 V）；
增益缩放 → <code>g&gt;1</code> 近似不变、<code>g&lt;1</code> 强过压过功率；同频大幅正弦 → 持续振荡、
THD→100%、功率/母线塌陷（DoS）。均与 ReThink 对电流控制回路的分析一致，验证 MPCC 在“无测量一致性校验”下
对 IL 传感器欺骗的脆弱性。</li>
</ul>

<h2><span class="n">06</span> 复现</h2>
<pre>matlab -batch build_attack_model   # 构建注入模型（非侵入副本）
matlab -batch run_campaign         # 12 场景闭环（约 15 min）
python3 analyze.py                 # KPI + 分类 + 出图
python3 make_report.py             # Markdown 报告
python3 build_html_report.py       # 本 HTML 报告</pre>
<p class="footnote">产物：<code>results/summary_kpis_annotated.csv</code>、<code>results.json</code>、
<code>run_*.mat</code>（各场景时域）、<code>figures/fig0..3_*.png</code>、<code>report/REPORT.md</code>。</p>

<hr>
<p class="footnote"><b>后续（第二组）</b>：在本攻击模型上评估检测与缓解——FFT 锚点/基波下限一致性校验、
观测器残差、HGQ2 IDS，对上述场景的检出率与控制恢复效果。</p>
</div>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print("wrote", OUT, f"({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
