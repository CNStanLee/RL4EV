# 处理器侧划分的对照程序

用于论文中"检测放在处理器 / 全部放在处理器"与"全部在 PL"的 20 s 并发重放对比，以及原生 CPU 基线。

| 文件 | 内容 |
|---|---|
| `rt_sched_cpu.cpp` | 与 `../rt_sched.c` 相同的三任务与重放数据；`cpudet` 模式在 A53 上计算检测周期（特征核 + float32 网络），`allcpu` 模式连控制拍也在 A53 上计算 |
| `mlp_float.cpp` | 检测网络的 float32 实现，读取 hls4ml 导出的 `firmware/weights/*.txt` |
| `hls_math_compat.h` | 把 `hls::` 数学函数映射到 libm，使综合用的 C++ 可在 CPU 上原样编译 |
| `cpu_baseline.cpp`、`cpu_baseline2.cpp` | 单独计时的原生 CPU 基线（特征核、网络、控制拍） |

板上构建（把 `HLS_PRJ/emi_feat/{emi_feat_hls.cpp,emi_feat_hls.h,trig_tables.h}`、
`HLS_PRJ/mpcc_r/{mpcc_r_hls.cpp,mpcc_r_hls.h}` 和 `HLS_PRJ/emi_detector/firmware/` 复制到本目录后）：

```bash
g++ -O2 -std=c++14 -mtune=cortex-a53 -pthread -include hls_math_compat.h -I. \
    rt_sched_cpu.cpp emi_feat_hls.cpp mpcc_r_hls.cpp -o rt_sched_cpu
sudo ./rt_sched_cpu frames.bin <nf> bufs.bin <nb> waves.bin <nw> 20 out_prefix cpudet   # 或 allcpu
```

需要 Vitis HLS 的 `ap_int.h` 等头文件时，加 `-I<Vitis_HLS>/include`。谐波估计器在两种模式下都留在 PL。
