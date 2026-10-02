# PS_notebook — ZCU104 板端（PYNQ）程序

板上环境：ZCU104（xczu7ev-ffvc1156-2-e），PYNQ 3.0.1（Linux 5.15）。比特流不入库，
按 [`Vivado_PRJ/README.md`](../Vivado_PRJ/README.md) 重建；接口描述 `.hwh` 入库。

| 文件 | 作用 |
|---|---|
| `libs/mpcc_r_overlay.py` | 四 IP overlay 驱动：按 hwh 寄存器表访问 `mpcc_r_hls`、`emi_feat_hls`、`emi_detector_axi`、`harmonic_estimator_axi`，逐次记录 ap_start→ap_done 时间 |
| `board_selftest_mpcc_r.py` | 板级自检（HIL 计划 H1）：四个 IP 用 `HLS_PRJ/*/tb_data` 的 C 仿真向量核对，并给出 PS 侧调用延迟 |
| `ps_server_mpcc_r.py` | 全链路 HIL 的板端服务：三条 TCP 通路 5010→5011（占空比）、5020→5021（检测）、5030→5031（谐波估计），逐帧日志 |
| `x86_pl_emulator.py` | 无板替身（H0）：同样三条通路，float32 参考模型 + 位精确 ONNX；`MPCC_ABS_IREF=1` 复现修正前的 IP |
| `ddr_replay_mpcc_r.py` | 实时性与功耗（H6 / H7）：SIL 记录放进 PS 内存连续驱动 PL，`axi_timer` 计时，PMBus 读功耗 |
| `rt_loop_mpcc_r.c`、`rt_loop_det.c` | 不经 Python 的 PS 循环：控制拍 / 检测周期的服务时间 |
| `rt_sched.c`、`run_rt_sched.sh` | 三任务并发调度重放（控制 50 µs、估计 250 µs、检测 20 ms，绑核 1/2/3）。默认普通优先级；环境变量 `RT_PRIO` 或 `run_rt_sched.sh` 切到 SCHED_FIFO + 内存锁定，这是论文定时表的配置（`logs_20261001/`） |
| `cpu_partition/` | 处理器侧检测 / 全处理器划分的对照程序 |
| `pwr_loop.c`、`pmbus_sample.py`、`measure_power.sh` | 仅控制器设计的 20 kHz 循环与 PMBus 采样（功耗基线）；`measure_power.sh` 依次测两种设计的空闲 / 运行功耗（`logs_20261002/`） |
| `mpcc_hil.ipynb`、`libs/mpcc_overlay.py`、`libs/tcp_cosim_utils.py`、`com_test.ipynb` | 最初的单 IP（`mpcc_hls`）HIL 通路 |
| `hardware/*.hwh`、`libs/system.hwh` | 两个设计的接口描述 |

## 上板步骤

1. 重建比特流，把 `Vivado_PRJ/MPCC_R/out/mpcc_r.bit` 与 `mpcc_r.hwh` 放进 `PS_notebook/hardware/`
   （单 IP 设计对应 `mpcc_hil.bit` / `mpcc_hil.hwh`）。
2. 把 `PS_notebook/` 与 `HLS_PRJ/` 下各组件的 `tb_data/` 复制到板上同一父目录（实验时为 `/home/xilinx/mpcc_r/`）。
3. 自检：

   ```bash
   sudo bash -lc "python3 -u board_selftest_mpcc_r.py --bit hardware/mpcc_r.bit --tb ../HLS_PRJ --n 200"
   ```

   判据：`emi_feat` 相对误差在容差内、`emi_detector` 标志字全等、`harmonic_estimator` 输出差 ≤ 2 LSB、
   `mpcc_r`（flags = 0）与 float32 参考的相对差 ≤ 1e-5。
4. 全链路 HIL 服务：

   ```bash
   sudo bash -lc "python3 -u ps_server_mpcc_r.py --bit hardware/mpcc_r.bit --log ../logs"
   ```

   主机侧 Simulink 的 `HIL_HOST` 指向板子地址，通路开关为 `ENABLE_HIL`、`ENABLE_HIL_DET`、`ENABLE_HIL_EST`
   （见 `Simulation/PV_MEV/docs/HIL_TEST_PLAN.md`）。无板时在主机上运行 `python x86_pl_emulator.py`。
5. 实时性重放。主机上从一次 SIL 记录导出重放数据，板上转成二进制后运行：

   ```bash
   # 主机
   python EMI_DET_FPGA/scripts/make_hil_replay_data.py --ts Simulation/PV_MEV/results/emi/ts \
       --run E-DC-01b_MPCC_R --out replay_E-DC-01b_MPCC_R.npz
   # 板上
   python3 -c "import numpy as np; z=np.load('replay_E-DC-01b_MPCC_R.npz'); [z[k].astype(np.float32).tofile(k+'.bin') for k in ('frames','bufs','waves')]; print({k: z[k].shape for k in ('frames','bufs','waves')})"
   sudo bash -lc "python3 -u ddr_replay_mpcc_r.py --data replay_E-DC-01b_MPCC_R.npz --out replay/h6 --seconds 20"
   gcc -O2 -o rt_loop_mpcc_r rt_loop_mpcc_r.c -lm && sudo ./rt_loop_mpcc_r frames.bin <n_frames> 20 1 rt_c_mode1.csv
   gcc -O2 -o rt_loop_det rt_loop_det.c && sudo ./rt_loop_det bufs.bin <n_bufs> 1000 rt_c_det.csv
   gcc -O2 -pthread -o rt_sched rt_sched.c -lm && sudo ./rt_sched frames.bin <nf> bufs.bin <nb> waves.bin <nw> 20 rt_sched
   ```

   运行 `rt_*` 程序前需先用 PYNQ 加载一次比特流（例如启动过 `ps_server_mpcc_r.py` 或 `Overlay('hardware/mpcc_r.bit')`）。
   `rt_sched` 输出的 `late` / `releases` 即 20 s 并发重放的迟到计数。论文定时表用实时调度配置：
   `sudo ./run_rt_sched.sh <数据目录> 20 <输出前缀> 80`，2026-10-01 的五次重放与对照见 `logs_20261001/README.md`。

## 来源说明

`ps_server_mpcc_r.py`、`ddr_replay_mpcc_r.py`、`rt_loop_*.c`、`rt_sched.c`、`pwr_loop.c`、`pmbus_sample.py`
以及 `libs/mpcc_r_overlay.py`、`board_selftest_mpcc_r.py`、`x86_pl_emulator.py` 的 2026-09-05 之后的修改，
是从已删除的原工作目录的本地会话记录中逐条重放恢复的，见
[`paper/recovery_20261001/README.md`](../paper/recovery_20261001/README.md)。
这些文件的全部记录操作均已重放成功，Python / C 语法检查通过；板上运行未在恢复后重新验证。
