# 本地模型与实验数据快照

[`local_backup_20261001T142101Z/`](local_backup_20261001T142101Z/)
完整保留 2026-10-01 同步主分支前的本地备份。
来源为 `/mnt/data6/playground/.RL4EV_local_backup_20261001T142101Z`；
论文仓库 [DAES_Special_Issue](https://github.com/CNStanLee/DAES_Special_Issue)
在 `supplement/local_backup_20261001T142101Z/` 保存相同副本。

快照包含全部 250 个实际备份文件，约 53 MiB：6 个 SLX 模型、模型输入 MAT、
MATLAB/Python 脚本、182 个 CSV、5 个 JSON、11 张 PNG、论文初稿，
以及备份中的 BIT/XSA/DCP、缓存和自动保存文件。原始 `README.md`、
`manifest.json` 和 `tracked_changes.patch` 也按原字节保留。
`SHA256SUMS` 覆盖全部 253 个原始文件。

原始清单记录备份前的代码提交 `3f9f8e94e4512992e29b665b8b431d31da5392d3`
和同步目标 `5733a9dad674b71a8025733ec965b9bd75c0fd07`。
清单的 251 条记录中，`Simulation/PV_MEV/PV_MEV.slx.r2024b` 标记为
`missing: true`，没有实际备份文件；删除状态保留在原始补丁里。

## 校验与使用

在代码仓库根目录运行：

```bash
cd reproducibility/local_backup_20261001T142101Z
sha256sum -c SHA256SUMS
```

`files/` 内保留原项目的相对路径，可单独取回所需模型、数据和脚本。
备份中的主 SLX 与初始化脚本属于较早的本地版本；当前工作目录保留已有的
韧性控制模型。快照没有覆盖工作模型，也没有合并旧初稿中的待验证结论。
早期约 800 V 实验数据的口径见
[`paper/daes_results/README.md`](../paper/daes_results/README.md)。

此次归档没有运行仿真、训练或板端实验。主论文的结果继续由
`paper/daes_results/` 和论文仓库的 `results_evidence/` 复现。
目录作为不可变快照维护；其中通常被忽略的文件也已显式加入 Git。
