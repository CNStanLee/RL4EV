# 早期 PV_MEV 配置诊断与注入记录

本目录保留本地早期实验的模型快照、脚本、CSV 记分卡和分析图。
`results/verify_results.csv` 中部分谐波策略的 d/p 标志设置错误；即使后续
`verify_results_harmonic.csv` 修正了标志，部分配置的母线仍偏离 400 V。
`attack_comparison.csv` 的 MPCC_D 无扰工作点约为 572 V / 15.06 kW，
不能和 400 V / 6.90 kW 充电基准作为同工况对照。

因此这些诊断记录没有并入 DAES 主文的最终 SIL/HIL 比较。
正式结果的来源、指标和重建脚本见
[`paper/daes_results/`](../../../paper/daes_results/README.md)。
实验原始 MAT 历史、测试导出 CSV 和自动保存文件保留在本地并由 gitignore 排除；
模型运行所需的 `model/PVArrayGridData.mat` 仍跟踪。
