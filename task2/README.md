# 题2 容器化持续 CPU Profiling（选做加分）

7×24 持续 CPU Profiling 工具：`perf record` 后台采集 + 按时间窗口轮转 + 历史保留（24h 自动清理）+ 按时间段回查 + 一键生成火焰图。Docker 容器化（aarch64，`--privileged` 运行）。

> 状态：**暂缓**。题1 全部完成后视时间推进。
> 评审为腾讯导师，ARM 镜像声明架构即可。

## 核心功能（规划）

| 功能 | 说明 |
|---|---|
| 后台持续采集 | `perf record -F 99 -ag`，每 60s 轮转 |
| 历史保留 | 时间戳命名，留 24h，自动清理 |
| 按时间回查 | CLI/API 输入时间段 → 定位采样文件 |
| 一键火焰图 | 调 FlameGraph 链生成 SVG |

## <TODO 阶段4 填：架构 / Dockerfile / 测试 / 启动命令>
