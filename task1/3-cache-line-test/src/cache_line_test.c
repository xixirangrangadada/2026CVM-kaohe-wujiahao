/*
 * 题1③ Cache Line 微基准 —— pointer chasing
 * 不同 stride 遍历大数组测延迟，验证 cache line 对性能的影响
 * 环境：鲲鹏 920 / TaiShan v110，cache line L1/L2=64B, L3=128B
 * 编译：gcc -O2 -o cache_line_test cache_line_test.c
 *
 * 用法：
 *   ./cache_line_test              # 扫所有 stride，输出延迟曲线
 *   ./cache_line_test <stride>     # 单 stride 模式（配合 perf stat）
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#define ARRAY_SIZE (16U << 20)   /* 16 MB：> L2(2MiB)、< L3(128MiB) */

/* 构造 stride 间距的循环链表，节点顺序随机化（绕过硬件预取器）。
 * 节点 = 1 个指针(8B)，物理位置 = order[i]*stride。 */
static void build_list(char *buf, size_t size, size_t stride) {
    size_t n = size / stride;                 /* 节点数 */
    size_t *order = malloc(n * sizeof(size_t));
    for (size_t i = 0; i < n; i++) order[i] = i;

    /* Fisher-Yates 洗牌（LCG 确定性，结果可复现） */
    uint32_t rng = 12345u;
    for (size_t i = n - 1; i > 0; i--) {
        rng = rng * 1103515245u + 12345u;
        size_t j = (rng >> 16) % (i + 1);
        size_t t = order[i]; order[i] = order[j]; order[j] = t;
    }

    /* 节点 order[i] 的 next 指针 → 节点 order[(i+1)%n] 的地址 */
    for (size_t i = 0; i < n; i++) {
        char **cur = (char **)(buf + order[i] * stride);
        *cur = buf + order[(i + 1) % n] * stride;
    }
    free(order);
}

/* 沿指针链遍历 iterations 次，返回纳秒。
 * 关键：memcpy(&p, p, ...) 让前后 load 数据依赖，CPU 无法乱序/预取 */
static uint64_t chase(const char *head, size_t iterations) {
    const char *p = head;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (size_t i = 0; i < iterations; i++) {
        memcpy(&p, p, sizeof(p));   /* p = *(char **)p */
        asm volatile("" : "+r"(p) :: "memory");  /* 屏障：防编译器消除/重排 */
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    return (uint64_t)(t1.tv_sec - t0.tv_sec) * 1000000000ULL
         + (uint64_t)(t1.tv_nsec - t0.tv_nsec);
}

int main(int argc, char **argv) {
    /* 单 stride 模式：配合 perf stat 单跑某 stride */
    if (argc == 2) {
        size_t stride = (size_t)strtoul(argv[1], NULL, 10);
        if (stride < sizeof(void *)) stride = sizeof(void *);   /* 最小 = 节点大小 */
        char *buf = aligned_alloc(64, ARRAY_SIZE);
        memset(buf, 0, ARRAY_SIZE);
        build_list(buf, ARRAY_SIZE, stride);
        size_t nodes = ARRAY_SIZE / stride;
        size_t iters = nodes * 200;
        uint64_t ns = chase(buf, iters);
        printf("stride=%4zu  nodes=%zu  latency_ns=%.2f\n",
               stride, nodes, (double)ns / iters);
        free(buf);
        return 0;
    }

    /* 默认：扫所有 stride，输出延迟曲线 */
    size_t strides[] = {1, 2, 4, 8, 16, 32, 64, 128, 256};
    printf("# stride(B)  latency_ns   nodes\n");
    for (size_t s = 0; s < sizeof(strides) / sizeof(strides[0]); s++) {
        size_t stride = strides[s];
        if (stride < sizeof(void *)) stride = sizeof(void *);
        char *buf = aligned_alloc(64, ARRAY_SIZE);
        memset(buf, 0, ARRAY_SIZE);
        build_list(buf, ARRAY_SIZE, stride);
        size_t nodes = ARRAY_SIZE / stride;
        size_t iters = nodes * 200;
        double best = 1e18;
        for (int r = 0; r < 5; r++) {            /* 5 次取最小，减噪声 */
            uint64_t ns = chase(buf, iters);
            double lat = (double)ns / iters;
            if (lat < best) best = lat;
        }
        printf("%4zu          %-10.2f   %zu\n", strides[s], best, nodes);
        free(buf);
    }
    return 0;
}
