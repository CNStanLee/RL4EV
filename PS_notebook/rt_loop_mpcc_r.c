/* ZCU104 PS real-time loop for mpcc_r_hls without Python (docs/HIL_TEST_PLAN.md stage H6).
 *   gcc -O2 -o rt_loop_mpcc_r rt_loop_mpcc_r.c
 *   sudo ./rt_loop_mpcc_r frames.bin <n_frames> <seconds> <mode 0=all 18 writes, 1=changed registers only> out.csv
 * frames.bin: n_frames x 18 float32 (make_hil_replay_data.py order); the loop replays them cyclically at 20 kHz
 * (50 us deadline, busy-wait), one ap_start/ap_done per tick, and records the service time of every tick
 * (input writes + start + done polling + D read) with CLOCK_MONOTONIC, plus the axi_timer ticks between
 * ap_start and ap_done seen.  Prints late / dropped counts and the service-time distribution. */
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define MPCC_BASE 0xA0010000u
#define TIMER_BASE 0xA0050000u
static const unsigned OFF[18] = {16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 136, 144, 152};
static const int IS_INT[18] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0};
#define OFF_D 160

static inline double now_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }

int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage: %s frames.bin n_frames seconds mode out.csv\n", argv[0]); return 1; }
    long nf = atol(argv[2]); double secs = atof(argv[3]); int mode = atoi(argv[4]);
    float *fr = malloc(nf * 18 * sizeof(float)); FILE *f = fopen(argv[1], "rb");
    if (!f || fread(fr, sizeof(float), nf * 18, f) != (size_t)(nf * 18)) { perror("frames"); return 1; }
    fclose(f);
    int fd = open("/dev/mem", O_RDWR | O_SYNC); if (fd < 0) { perror("/dev/mem"); return 1; }
    volatile uint32_t *ip = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, MPCC_BASE);
    volatile uint32_t *tm = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, TIMER_BASE);
    if (ip == MAP_FAILED || tm == MAP_FAILED) { perror("mmap"); return 1; }
    tm[0] = 0; tm[1] = 0; tm[0] = 0x20; tm[0] = 0x90;              /* free-running up counter */
    uint32_t last[18]; for (int j = 0; j < 18; j++) last[j] = 0xFFFFFFFFu;
    long total = (long)(secs / 50e-6); double *svc = malloc(total * sizeof(double)); double *plt = malloc(total * sizeof(double));
    float *Dout = malloc((nf < total ? nf : total) * sizeof(float));
    long late = 0, dropped = 0; const double period = 50e-6;
    double t_start = now_s();
    for (long k = 0; k < total; k++) {
        double deadline = t_start + (k + 1) * period;
        double t0 = now_s();
        const float *v = fr + 18 * (k % nf);
        for (int j = 0; j < 18; j++) {
            uint32_t u; if (IS_INT[j]) u = (uint32_t)lrintf(v[j]); else memcpy(&u, &v[j], 4);
            if (mode == 1 && u == last[j]) continue;
            ip[OFF[j] / 4] = u; last[j] = u;
        }
        uint32_t ta = tm[2]; ip[0] = 1; while (!(ip[0] & 2)) {} uint32_t tb = tm[2];
        uint32_t d = ip[OFF_D / 4]; float D; memcpy(&D, &d, 4); if (k < nf) Dout[k] = D;
        double t1 = now_s(); svc[k] = 1e6 * (t1 - t0); plt[k] = 1e-2 * (double)(tb - ta);   /* 100 MHz -> us */
        if (t1 > deadline) { late++; if (t1 > deadline + period) dropped++; }
        else while (now_s() < deadline) {}
    }
    double el = now_s() - t_start;
    FILE *o = fopen(argv[5], "w"); fprintf(o, "k,service_us,pl_us,D\n");
    for (long k = 0; k < total; k++) fprintf(o, "%ld,%.3f,%.2f,%.7g\n", k, svc[k], plt[k], k < nf ? Dout[k] : NAN);
    fclose(o);
    double *s = malloc(total * sizeof(double)); memcpy(s, svc, total * sizeof(double)); qsort(s, total, sizeof(double), cmp);
    double *p = malloc(total * sizeof(double)); memcpy(p, plt, total * sizeof(double)); qsort(p, total, sizeof(double), cmp);
    double mean = 0, pm = 0; for (long k = 0; k < total; k++) { mean += svc[k]; pm += plt[k]; } mean /= total; pm /= total;
    printf("mode %d: %ld ticks in %.3f s (%.1f kHz), late %ld, dropped %ld\n", mode, total, el, total / el / 1e3, late, dropped);
    printf("service_us mean %.2f median %.2f p99 %.2f max %.2f\n", mean, s[total / 2], s[(long)(0.99 * total)], s[total - 1]);
    printf("pl_us (ap_start->ap_done seen, timer) mean %.2f median %.2f p99 %.2f max %.2f\n", pm, p[total / 2], p[(long)(0.99 * total)], p[total - 1]);
    return 0;
}
