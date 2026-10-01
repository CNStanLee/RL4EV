# 早期电感电流传感器攻击实验

修正后的实验报告是 [`report/REPORT.md`](report/REPORT.md)，数值来源是
`results_MPCC/summary_kpis.csv`。该组 MPCC-D 基线为 THD 7.56%、
母线均值约 780 V、功率 14.75 kW；它和 DAES 的 400 V / 6.90 kW
充电级基准属于不同工况，未合并统计。

`results/` 则是更早的失配采样配置，保留作诊断历史；报告目录中的重复
HTML、DOCX、PDF 导出和两个结果目录的原始 MAT 仿真历史由 gitignore 排除。
脚本、实验模型快照、输入参数、紧凑 CSV/JSON 汇总与分析图仍保留。

论文采用的最终 SIL、历史 HIL 与板端重放结果见
[`paper/daes_results/`](../../../paper/daes_results/README.md)。
