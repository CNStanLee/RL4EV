/* ZCU104 PS-native detector path (docs/HIL_TEST_PLAN.md H6 supplement): per grid cycle write the 200x12 buffer to
 * emi_feat_hls over AXI-Lite, run it, copy the 48 features into emi_detector_axi, run it, read logits and flags.
 *   gcc -O2 -o rt_loop_det rt_loop_det.c && sudo ./rt_loop_det bufs.bin <n_bufs> <n_cycles> out.csv
 * bufs.bin: n_bufs x 2400 float32 (make_hil_replay_data.py). Reports the buffer-write, feature, detector and total
 * time per cycle. */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#define FEAT_BASE 0xA0020000u
#define DET_BASE  0xA0030000u
#define FEAT_RESET 16
#define FEAT_FEAT 256
#define FEAT_BUF 16384
#define DET_FEAT 256
#define DET_LOGIT 32
#define DET_FLAGS 16
#define DET_RESET 96
static inline double now_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
static int cmp(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
static void stats(const char *n, double *v, long k) { double *s = malloc(k * sizeof(double)); memcpy(s, v, k * sizeof(double)); qsort(s, k, sizeof(double), cmp); double m = 0; for (long i = 0; i < k; i++) m += v[i]; printf("%-14s mean %8.1f median %8.1f p99 %8.1f max %8.1f us\n", n, m / k, s[k / 2], s[(long)(0.99 * k)], s[k - 1]); free(s); }
int main(int argc, char **argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s bufs.bin n_bufs n_cycles out.csv\n", argv[0]); return 1; }
    long nb = atol(argv[2]), n = atol(argv[3]);
    float *B = malloc(nb * 2400 * sizeof(float)); FILE *f = fopen(argv[1], "rb"); if (!f || fread(B, 4, nb * 2400, f) != (size_t)(nb * 2400)) { perror("bufs"); return 1; } fclose(f);
    int fd = open("/dev/mem", O_RDWR | O_SYNC); volatile uint32_t *fe = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, FEAT_BASE);
    volatile uint32_t *de = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, DET_BASE);
    if (fe == MAP_FAILED || de == MAP_FAILED) { perror("mmap"); return 1; }
    double *tw = malloc(n * 8), *tf = malloc(n * 8), *td = malloc(n * 8), *tt = malloc(n * 8); FILE *o = fopen(argv[4], "w"); fprintf(o, "cycle,buf_write_us,feat_us,det_us,total_us,flags\n");
    for (long k = 0; k < n; k++) {
        const uint32_t *b = (const uint32_t *)(B + 2400 * (k % nb)); double t0 = now_s();
        for (int i = 0; i < 2400; i++) fe[FEAT_BUF / 4 + i] = b[i];
        fe[FEAT_RESET / 4] = (k == 0); double t1 = now_s();
        fe[0] = 1; while (!(fe[0] & 2)) {} double t2 = now_s();
        for (int i = 0; i < 48; i++) de[DET_FEAT / 4 + i] = fe[FEAT_FEAT / 4 + i];
        de[DET_RESET / 4] = (k == 0); de[0] = 1; while (!(de[0] & 2)) {} uint32_t fl = de[DET_FLAGS / 4]; double t3 = now_s();
        tw[k] = 1e6 * (t1 - t0); tf[k] = 1e6 * (t2 - t1); td[k] = 1e6 * (t3 - t2); tt[k] = 1e6 * (t3 - t0);
        fprintf(o, "%ld,%.2f,%.2f,%.2f,%.2f,%u\n", k, tw[k], tf[k], td[k], tt[k], fl);
    }
    fclose(o); stats("buf_write", tw, n); stats("feat", tf, n); stats("det", td, n); stats("total", tt, n); return 0;
}
