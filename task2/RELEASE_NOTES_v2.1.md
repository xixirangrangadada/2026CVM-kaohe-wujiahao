# Release v2.1 — 容器化持续 CPU Profiling（增强版）

> 在 v2.0「7×24 黑匣子」基础上新增三大功能：**环境自检 / CPU 指标采集 / 事件标记**。
> 把工具从「能用的采样器」升级为「健壮、完整、易用、可移植」的产品。

**测试环境**：鲲鹏 920（TaiShan v110）/ aarch64 / openEuler（内核 4.19.208）/ perf 4.19.90 / KVM guest。

---

## 🆕 三大新功能

### 1. 🔍 环境自检 preflight（健壮性 / 可移植性）
容器自带 **8 项体检**，换机器跑前一键确认环境，卡住项给修复建议：
perf 二进制 / PMU 权限（`perf_event_paranoid`）/ 采样能力 / 内核符号解析 / **PMU 事件可用性** / `--pid=host` / FlameGraph 工具链 / 磁盘空间。
呼应考题「地基验证三关卡」，把手动验证脚本升级为容器自带的自检模块。

```bash
docker exec cpu-profiler python3 -m profiler.preflight
```
> **本机实测**：8 项全绿（8 个 PMU 事件全可用、内核符号 `[unknown]` 仅 22%）。

### 2. 📊 CPU 指标采集与趋势（功能完整度，呼应题1①）
collector 并行跑 `perf stat`，采集 **IPC / LLC miss / 分支预测失败率 / L1·dTLB miss**，
每窗口产出 `metrics-*.csv`，前端 IPC 折线 + 指标卡片实时展示。
> perf 4.19 ARM 上 `branches` 通用名 `<not counted>`，已用 raw code `0x021`（BR_RETIRED）修复。
> **本机实测**：stress matrixprod 时段 IPC 0.8→2.3、L1 miss 暴涨 10×，指标精准反映 CPU 飙升。

### 3. 🎬 事件标记 + 一键诊断（易用性）
前端点「🎬 标记事件」记下关注时刻 → 时间线高亮 → 「一键诊断」直接出该时段火焰图。
**不做 start/stop 采集**（会偏离「7×24 常驻黑匣子」题眼），改用事件标记实现全链路图形化。

---

## 📦 镜像下载

附件 `profiler-v21.tar.gz`（164MB，aarch64）：

```bash
docker load -i profiler-v21.tar.gz
docker run -d --privileged --pid=host \
  -v /lib/modules:/lib/modules:ro -v /sys:/sys \
  -v /data:/data -p 8080:8080 \
  --name cpu-profiler cpu-profiler:v21
```

**必填参数**：`--privileged`（PMU 访问）/ `--pid=host`（采宿主机进程）/ `-v /lib/modules`（内核符号，否则栈 `[unknown]`）/ `-v /data`（持久化卷）。

---

## 🚀 使用方式

### 浏览器（推荐）
- **本机跑容器**（自己有 ARM 环境）：`docker run -p 8080:8080 ...` 后，浏览器直接开 **http://localhost:8080**
- **远程服务器跑**（8080 不对公网开放）：SSH 隧道 `ssh -L 8080:localhost:8080 <server>` → 本地浏览器开 http://localhost:8080

打开后：
- 🔍 **环境检查** → 8 项绿勾
- 📊 **CPU 指标趋势** → IPC 折线 + LLC miss / 分支失败率卡片
- 采样时间线 + 🎬 **事件标记** + **一键诊断**火焰图

### CLI
```bash
docker exec cpu-profiler python3 -m profiler.preflight           # 环境自检
docker exec cpu-profiler python3 -m profiler.metrics 10          # 最近窗口指标
docker exec cpu-profiler python3 -m profiler.query "起" "止"      # 时段回查
docker exec cpu-profiler python3 -m profiler.flamegraph "起" "止" --out /data/svg/x.svg
```

### 触发一次 CPU 飙升验证
```bash
stress-ng --cpu 2 --cpu-method matrixprod -t 60s   # 前端 IPC/指标会明显跳动
```

---

## 🏗️ 架构（C1–C8 组件 + 文件总线）

| 组件 | 职责 |
|---|---|
| C1 collector | perf record（栈）+ perf stat（指标）并行采集 + 60s 轮转 |
| C2 janitor | 定时清 >24h 采样文件 |
| C3 query | 时段 → 命中采样文件 |
| C4 flamegraph | 采样文件 → SVG |
| C5 server | 9 个 HTTP 接口 + 前端托管 |
| C6 preflight | 8 项环境自检 + 修复建议 |
| C7 metrics | perf stat CSV → IPC/LLC/分支率 |
| C8 events | 事件标记 + 一键诊断 |

**文件总线**：`perf-*.data`（栈）/ `metrics-*.csv`（指标）/ `flame-*.svg` / `events.json`，组件靠文件命名约定解耦，互不直接调用。

---

## ✅ 测试验证

- **单测 31 个全绿**：naming 契约往返 / query 回查命中边界（半开区间）/ janitor 清理误删风险（不碰非约定文件、按文件名时间戳非 mtime）
- **云端端到端**：preflight 8 项全绿 + 3 场景火焰图定位热点（stress_cpu / stress_vm_child / queens_try）+ metrics 指标实测

---

## 📝 Changelog（v2.0 → v2.1）

**新增**
- 🔍 环境自检 preflight（8 项体检）
- 📊 CPU 指标采集（collector 并行 perf stat + metrics 解析 + `/api/metrics` + 前端趋势）
- 🎬 事件标记 + 一键诊断（events + `/api/events` + 前端）
- 前端三区块（环境检查 / 指标趋势 / 事件标记）
- query / janitor 单测（+20，共 31）

**修复**
- `branches` 事件 perf 4.19 ARM `<not counted>` → raw code `0x021`

详见 `task2/README.md`。
