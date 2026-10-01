/* ZCU104 PS concurrent schedule test (review point 4): three pinned threads drive the PL at the real rates for N seconds:
 *   core 1: control tick 50 us  (mpcc_r_hls: changed-register writes, ap_start, poll, read D)
 *   core 2: detector cycle 20 ms (emi_feat_hls 2400-word buffer, run, 48-word copy, emi_detector_axi run, read flags)
 *   core 3: estimator window 250 us (harmonic_estimator_axi 80-word write, run, read enc)
 * gcc -O2 -pthread -o rt_sched rt_sched.c && sudo ./rt_sched frames.bin nf bufs.bin nb waves.bin nw seconds out_prefix
 * Per task and per instance: release jitter (actual start - scheduled release), service time (start -> done), end-to-end
 * (release -> done), PL time (ap_start -> ap_done seen, axi_timer for mpcc), late (done > next release), dropped (> 1 period).
 * All threads run at normal priority (SCHED_OTHER); the AXI-Lite master is shared. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#define MPCC_BASE 0xA0010000u
#define FEAT_BASE 0xA0020000u
#define DET_BASE  0xA0030000u
#define EST_BASE  0xA0040000u
#define TIMER_BASE 0xA0050000u
static const unsigned OFF[18] = {16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 136, 144, 152};
static const int IS_INT[18] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0};
static inline double now_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
typedef struct { const char *name; double period; long n; double *jit, *svc, *e2e, *pl; long late, dropped; } task_t;
static void report(task_t *t, FILE *o) {
    double *m[4] = {t->jit, t->svc, t->e2e, t->pl}; const char *nm[4] = {"release_jitter", "service", "end_to_end", "pl"};
    for (int k = 0; k < 4; k++) { double *s = malloc(t->n * 8); memcpy(s, m[k], t->n * 8); qsort(s, t->n, 8, cmp); double mean = 0; for (long i = 0; i < t->n; i++) mean += m[k][i]; mean /= t->n;
        printf("%-10s %-15s n %7ld mean %8.2f median %8.2f p99 %8.2f max %8.2f us\n", t->name, nm[k], t->n, mean, s[t->n / 2], s[(long)(0.99 * t->n)], s[t->n - 1]);
        fprintf(o, "%s,%s,%ld,%.3f,%.3f,%.3f,%.3f\n", t->name, nm[k], t->n, mean, s[t->n / 2], s[(long)(0.99 * t->n)], s[t->n - 1]); free(s); }
    printf("%-10s late %ld dropped %ld of %ld\n", t->name, t->late, t->dropped, t->n); fprintf(o, "%s,late,%ld,,,,\n%s,dropped,%ld,,,,\n", t->name, t->late, t->name, t->dropped);
}
static volatile uint32_t *ip_m, *ip_f, *ip_d, *ip_e, *tm; static float *FR, *BU, *WV; static long NF, NB, NW; static double SECS, T0;
static void pin(int core) { cpu_set_t c; CPU_ZERO(&c); CPU_SET(core, &c); pthread_setaffinity_np(pthread_self(), sizeof(c), &c); }
static void *run_mpcc(void *arg) { task_t *t = arg; pin(1); uint32_t last[18]; for (int j = 0; j < 18; j++) last[j] = 0xFFFFFFFFu; const double P = t->period; long k = 0;
    while (1) { double rel = T0 + k * P; if (rel > T0 + SECS) break; while (now_s() < rel) {} double ts = now_s(); const float *v = FR + 18 * (k % NF);
        for (int j = 0; j < 18; j++) { uint32_t u; if (IS_INT[j]) u = (uint32_t)lrintf(v[j]); else memcpy(&u, &v[j], 4); if (u == last[j]) continue; ip_m[OFF[j] / 4] = u; last[j] = u; }
        uint32_t ta = tm[2]; ip_m[0] = 1; while (!(ip_m[0] & 2)) {} uint32_t tb = tm[2]; volatile uint32_t d = ip_m[160 / 4]; (void)d; double te = now_s();
        t->jit[k] = 1e6 * (ts - rel); t->svc[k] = 1e6 * (te - ts); t->e2e[k] = 1e6 * (te - rel); t->pl[k] = 1e-2 * (double)(tb - ta); if (te > rel + P) { t->late++; if (te > rel + 2 * P) t->dropped++; } k++; }
    t->n = k; return NULL; }
static void *run_det(void *arg) { task_t *t = arg; pin(2); const double P = t->period; long k = 0;
    while (1) { double rel = T0 + k * P; if (rel > T0 + SECS) break; while (now_s() < rel) {} double ts = now_s(); const uint32_t *b = (const uint32_t *)(BU + 2400 * (k % NB));
        for (int i = 0; i < 2400; i++) ip_f[16384 / 4 + i] = b[i]; ip_f[16 / 4] = (k == 0); double t1 = now_s(); ip_f[0] = 1; while (!(ip_f[0] & 2)) {}
        for (int i = 0; i < 48; i++) ip_d[256 / 4 + i] = ip_f[256 / 4 + i]; ip_d[96 / 4] = (k == 0); ip_d[0] = 1; while (!(ip_d[0] & 2)) {} volatile uint32_t f = ip_d[16 / 4]; (void)f; double te = now_s();
        t->jit[k] = 1e6 * (ts - rel); t->svc[k] = 1e6 * (te - ts); t->e2e[k] = 1e6 * (te - rel); t->pl[k] = 1e6 * (te - t1); if (te > rel + P) { t->late++; if (te > rel + 2 * P) t->dropped++; } k++; }
    t->n = k; return NULL; }
static void *run_est(void *arg) { task_t *t = arg; pin(3); const double P = t->period; long k = 0;
    while (1) { double rel = T0 + k * P; if (rel > T0 + SECS) break; while (now_s() < rel) {} double ts = now_s(); const uint32_t *w = (const uint32_t *)(WV + 80 * (k % NW));
        for (int i = 0; i < 80; i++) ip_e[512 / 4 + i] = w[i]; double t1 = now_s(); ip_e[0] = 1; while (!(ip_e[0] & 2)) {} double t2 = now_s(); volatile uint32_t e0 = ip_e[32 / 4]; (void)e0; double te = now_s();
        t->jit[k] = 1e6 * (ts - rel); t->svc[k] = 1e6 * (te - ts); t->e2e[k] = 1e6 * (te - rel); t->pl[k] = 1e6 * (t2 - t1); if (te > rel + P) { t->late++; if (te > rel + 2 * P) t->dropped++; } k++; }
    t->n = k; return NULL; }
static float *loadf(const char *f, long n) { float *b = malloc(n * 4); FILE *fp = fopen(f, "rb"); if (!fp || fread(b, 4, n, fp) != (size_t)n) { perror(f); exit(1); } fclose(fp); return b; }
int main(int argc, char **argv) {
    if (argc < 9) { fprintf(stderr, "usage: %s frames.bin nf bufs.bin nb waves.bin nw seconds out_prefix\n", argv[0]); return 1; }
    NF = atol(argv[2]); NB = atol(argv[4]); NW = atol(argv[6]); SECS = atof(argv[7]); FR = loadf(argv[1], NF * 18); BU = loadf(argv[3], NB * 2400); WV = loadf(argv[5], NW * 80);
    int fd = open("/dev/mem", O_RDWR | O_SYNC); ip_m = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, MPCC_BASE); ip_f = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, FEAT_BASE);
    ip_d = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, DET_BASE); ip_e = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, EST_BASE); tm = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, TIMER_BASE);
    tm[0] = 0; tm[1] = 0; tm[0] = 0x20; tm[0] = 0x90;
    for (int j = 0; j < 13; j++) { uint32_t u; memcpy(&u, &FR[j], 4); ip_m[OFF[j] / 4] = u; } ip_m[OFF[13] / 4] = 1; ip_m[OFF[16] / 4] = 437;
    long nm = (long)(SECS / 50e-6) + 2, nd = (long)(SECS / 20e-3) + 2, ne = (long)(SECS / 250e-6) + 2;
    task_t tmk = {"mpcc", 50e-6, 0, malloc(nm * 8), malloc(nm * 8), malloc(nm * 8), malloc(nm * 8), 0, 0};
    task_t tdt = {"detector", 20e-3, 0, malloc(nd * 8), malloc(nd * 8), malloc(nd * 8), malloc(nd * 8), 0, 0};
    task_t tes = {"estimator", 250e-6, 0, malloc(ne * 8), malloc(ne * 8), malloc(ne * 8), malloc(ne * 8), 0, 0};
    pthread_t th[3]; T0 = now_s() + 0.05;
    pthread_create(&th[0], NULL, run_mpcc, &tmk); pthread_create(&th[1], NULL, run_det, &tdt); pthread_create(&th[2], NULL, run_est, &tes);
    for (int i = 0; i < 3; i++) pthread_join(th[i], NULL);
    char fn[512]; snprintf(fn, sizeof fn, "%s_summary.csv", argv[8]); FILE *o = fopen(fn, "w"); fprintf(o, "task,quantity,n,mean_us,median_us,p99_us,max_us\n");
    report(&tmk, o); report(&tdt, o); report(&tes, o); fclose(o);
    snprintf(fn, sizeof fn, "%s_mpcc.csv", argv[8]); o = fopen(fn, "w"); fprintf(o, "k,jitter_us,service_us,e2e_us,pl_us\n"); for (long k = 0; k < tmk.n; k++) fprintf(o, "%ld,%.2f,%.2f,%.2f,%.2f\n", k, tmk.jit[k], tmk.svc[k], tmk.e2e[k], tmk.pl[k]); fclose(o);
    return 0;
}
