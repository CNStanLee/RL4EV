/* 20 kHz control loop on the controller-only design (mpcc_hls: 14 inputs at 16..120, D at 128) for the power baseline.
 * gcc -O2 -o pwr_loop pwr_loop.c -lm && sudo ./pwr_loop frames.bin nf seconds */
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static const unsigned OFF[14] = {16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120};
static inline double now_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
int main(int argc, char **argv) {
    long nf = atol(argv[2]); double secs = atof(argv[3]); float *fr = malloc(nf * 18 * 4); FILE *f = fopen(argv[1], "rb"); if (!f || fread(fr, 4, nf * 18, f) != (size_t)(nf * 18)) { perror("frames"); return 1; } fclose(f);
    int fd = open("/dev/mem", O_RDWR | O_SYNC); volatile uint32_t *ip = mmap(NULL, 0x10000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0xA0010000u);
    long total = (long)(secs / 50e-6), late = 0; double t0 = now_s();
    for (long k = 0; k < total; k++) { double dl = t0 + (k + 1) * 50e-6; const float *v = fr + 18 * (k % nf);
        for (int j = 0; j < 14; j++) { uint32_t u; if (j == 13) u = (uint32_t)lrintf(v[j]); else memcpy(&u, &v[j], 4); ip[OFF[j] / 4] = u; }
        ip[0] = 1; while (!(ip[0] & 2)) {} volatile uint32_t d = ip[128 / 4]; (void)d; if (now_s() > dl) late++; else while (now_s() < dl) {} }
    printf("controller-only loop: %ld ticks, late %ld\n", total, late); return 0;
}
