# 容器化持续 CPU Profiling（题2）

> 7×24 持续 CPU 采样"黑匣子"：`perf record` 常驻采集 + 按时间窗口轮转 + 历史保留（自动清理）+ 按时段回查 + 一键生成火焰图。Docker 容器化（aarch64，`--privileged` 运行）。
>
> **v2.1 增强（2026-06-18）**：在原黑匣子基础上新增 ① 环境自检 preflight（换机器就知道哪里不对、怎么修）② CPU 指标采集与趋势（perf stat → IPC/LLC/分支失败率，呼应题1①）③ 事件标记 + 一键诊断（契合黑匣子定位的全链路图形化，**不做偏离题眼的 start/stop**）。

---

## 一、项目简介

**背景**：在线服务凌晨 CPU 飙升，值班赶到时进程已恢复，`perf top` 看不到故障现场，复盘只能靠猜。

**方案**：做一个常驻后台的持续 Profiling 工具，让 perf 像"黑匣子"一样持续采样。出故障时只需指定时间段，就能调出当时的 CPU 采样数据、生成火焰图定位根因。

**架构**：aarch64（鲲鹏 920），Docker 容器化，组件化设计（采集/清理/回查/火焰图/HTTP/自检/指标/事件 八组件，靠文件总线解耦）。

---

## 二、架构设计

### 组件化 + 文件总线

组件之间**不直接调用**，靠**约定目录 + 文件命名**（文件总线）解耦。

```
C1 采集器 ──写──→ perf-<start>-<end>.data      ──读──→ C3 回查 → C4 火焰图
       ├──写──→ metrics-<start>-<end>.csv      ──读──→ C7 指标（IPC/LLC/分支）
C5 HTTP API ──读──→ 上述文件 + 调 C6 自检 + C8 事件
```

| 组件 | 文件 | 职责 | 形态 |
|---|---|---|---|
| C1 采集器 | `collector.py` | perf record（调用栈）+ perf stat（指标）后台采 + 60s 轮转 + SIGTERM 优雅停 | 常驻（supervisord）|
| C2 清理器 | `janitor.py` | 定时删 >24h 采样文件 | 常驻（supervisord）|
| C3 回查 | `query.py` | 时间段 → 定位命中采样文件 | 库 + CLI |
| C4 火焰图 | `flamegraph.py` | 采样文件 → SVG | 库 + CLI |
| C5 HTTP API | `server.py` | 9 接口 + 前端托管 | 常驻（supervisord）|
| C6 环境自检 | `preflight.py` | 8 项体检（perf/PMU/符号/事件/...）+ 修复建议 | 库 + CLI |
| C7 指标解析 | `metrics.py` | perf stat CSV → IPC/LLC miss/分支失败率 | 库 + CLI |
| C8 事件标记 | `events.py` | 标记"关注时刻"+ 一键诊断 | 库 |

**文件总线契约**（`naming.py`，单一真相源，禁止别处拼文件名）：
- `perf-<start>-<end>.data` — 调用栈采样（→ 火焰图）
- `metrics-<start>-<end>.csv` — PMU 计数器（→ CPU 指标，与 `.data` 1:1 对应）
- `flame-<start>-<end>.svg` — 火焰图
- `events.json` — 事件标记（原子写）
- 时间戳本地时区 `YYYYmmdd_HHMMSS`

---

## 三、快速启动

### 方式一：从 tar 加载（推荐，评审一键验证）

> **镜像下载**：`profiler.tar.gz`（aarch64）在 [GitHub Release](https://github.com/xixirangrangadada/2026CVM-kaohe-wujiahao/releases)（> GitHub 100MB 限制，放 Release 而非仓库）。下载后与仓库同级执行：

```bash
docker load -i profiler.tar.gz
docker run -d --privileged --pid=host \
  -v /lib/modules:/lib/modules:ro -v /sys:/sys \
  -v /data:/data -p 8080:8080 \
  --name cpu-profiler cpu-profiler
```

### 方式二：直接构建

```bash
cd task2/src
docker build -t cpu-profiler .
docker run -d --privileged --pid=host \
  -v /lib/modules:/lib/modules:ro -v /sys:/sys \
  -v /data:/data -p 8080:8080 \
  --name cpu-profiler cpu-profiler
```

> **v2.0 → v2.1**：Release 上的 v2.0 镜像不含 preflight/metrics/events，需重新 `docker build`（或下载新 Release）才能用新功能。

**运行参数**（必填）：`--privileged`（PMU 访问）/ `--pid=host`（采宿主机进程）/ `-v /lib/modules`（内核符号，否则栈 `[unknown]`）/ `-v /sys`（PMU 硬件）/ `-v /data`（持久化卷）。

---

## 四、使用示例

容器启动即开始持续采集（每 60s 一个窗口，落 `/data/perf/`，同时产出 `.data` + `.csv`）。

### 0. 环境自检（换机器第一步）
```bash
docker exec cpu-profiler python3 -m profiler.preflight
```
> 8 项体检：perf 二进制 / PMU 权限 / 采样能力 / 内核符号解析 / PMU 事件可用性 / --pid=host / FlameGraph / 磁盘。每项给 OK/FAIL + 卡住时的修复建议。

### 1. 触发一次 CPU 飙升
```bash
stress-ng --cpu 2 --cpu-method matrixprod -t 60s   # 记下起止时间
```

### 2. 回查该时段采样文件
```bash
docker exec cpu-profiler python3 -m profiler.query "2026-06-17 19:43:52" "2026-06-17 19:44:17"
```

### 3. 生成火焰图
```bash
docker exec cpu-profiler python3 -m profiler.flamegraph \
  "2026-06-17 19:43:52" "2026-06-17 19:44:17" --out /data/svg/matrixprod.svg
```

### 4. 看该时段 CPU 指标
```bash
docker exec cpu-profiler python3 -m profiler.metrics 10   # 最近 10 个窗口 IPC/LLC/分支率
```

### 5. 浏览器（推荐）：http://localhost:8080
点【🔍 环境检查】看体检 → 等 1-2 分钟看 IPC 折线 → 点【🎬 标记事件】→ 时间线高亮 → 【一键诊断】出火焰图。

### 6. 优雅停止
```bash
docker stop cpu-profiler   # SIGTERM → collector 归档最后窗口后退出
```

---

## 五、配置项（环境变量，`docker run -e` 可覆盖）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ROTATE_SECONDS` | 60 | 轮转窗口（秒）|
| `RETAIN_HOURS` | 24 | 采样保留时长（小时），超期由 janitor 清理 |
| `SAMPLE_FREQ` | 99 | perf record 采样频率 Hz |
| `PERF_EVENTS` | 8 事件 | perf stat 事件集（逗号分隔；默认 cycles/instructions/cache-misses/cache-references/L1-dcache-load-misses/branch-misses/branches/dTLB-load-misses，呼应题1①）|
| `DATA_DIR` | /data/perf | 采样文件目录 |
| `SVG_DIR` | /data/svg | 火焰图输出目录 |

---

## 六、设计权衡

| 决策 | 选择 | 理由 |
|---|---|---|
| 语言 | Python | shell 子进程编排 + 文件管理 + HTTP，Python 对症；C++ 强项用不上 |
| 总线形态 | 文件系统约定（非消息中间件）| 组件耦合点是落盘文件；消息队列对"持续写文件+偶尔回查"零收益 |
| 部署形态 | 单容器多进程（supervisord）| 考题要"一个 tar 一键起"；组件共享 /data 卷 |
| 轮转方式 | 外层循环 subprocess | 命名可控、信号好处理、易测；不用 perf `--switch-output` 的不可控切片 |
| 优雅停 | SIGTERM→转发 SIGINT 给 perf record | perf 对 SIGINT 优雅写盘，对 SIGTERM 丢数据 |
| 指标采集 | record + stat 并行 | record 出火焰图、stat 出计数器；stat 是辅链，失败只 warn 不影响主链 |
| 图形化方式 | 事件标记 + 一键诊断（非 start/stop）| start/stop 偏离"7×24 常驻黑匣子"题眼；标记时刻+诊断才契合 |

---

## 七、测试验证

- **单测**（31 个，本地 `python -m unittest profiler.test_naming profiler.test_query profiler.test_janitor`）：naming 契约往返 / query 回查命中边界（半开区间）/ janitor 清理误删风险（不碰非约定文件、按文件名时间戳非 mtime）。
- **端到端**（3 场景）：matrixprod/rand-set/queens 火焰图均精准定位热点（stress_cpu / stress_vm_child / queens_try 17224 次）。

详见 `test/测试报告.md`。

---

## 八、前端界面（Web UI，8080）

浏览器访问 http://localhost:8080，单页应用（纯 HTML+JS，无框架）：

- **系统概览**：采集状态 + 磁盘 + 文件数（`/api/status`，10s 自动轮询）
- **🔍 环境检查**：一键 8 项体检弹层，卡住项给修复建议（`/api/preflight`）
- **📊 CPU 指标趋势**：IPC 折线 + LLC miss / 分支失败率卡片（`/api/metrics`，呼应题1①）
- **采样时间线**：文件列表 + 🎬事件标记高亮 + 一键诊断链接（`/api/files` + `/api/events`）
- **火焰图**：选时段生成，iframe 嵌入 SVG，浏览器原生缩放/搜索（`/api/flame` + `/svg`）
- **🎬 事件标记 + 一键诊断**：标记"关注时刻"→ 以该时段直接出火焰图（`POST /api/event`）

实现：`server.py`（Flask）+ `web/index.html`（复用 C3/C4/C6/C7/C8 库，不重复造轮子）。

---

## 九、目录结构

```
task2/
├── README.md                 ← 本文件
├── src/
│   ├── Dockerfile
│   ├── supervisord.conf
│   ├── profiler/             ← Python 包（8 组件 + 单测）
│   │   ├── naming.py         ← 文件总线契约（单一真相源）
│   │   ├── config.py         ← 配置（含 stat_events 事件集）
│   │   ├── collector.py      ← C1 采集（record + stat 并行）
│   │   ├── janitor.py        ← C2 清理
│   │   ├── query.py          ← C3 回查
│   │   ├── flamegraph.py     ← C4 火焰图
│   │   ├── server.py         ← C5 HTTP API（9 接口）
│   │   ├── preflight.py      ← C6 环境自检
│   │   ├── metrics.py        ← C7 指标解析
│   │   ├── events.py         ← C8 事件标记
│   │   ├── log.py            ← 统一日志（stdout + 轮转文件）
│   │   └── test_*.py         ← 单测（naming/query/janitor）
│   └── web/
│       └── index.html        ← 前端单页
├── test/                     ← 环境验证 + 3 场景测试 + 火焰图 SVG
├── ai-chat-log/              ← AI 协作记录导出
└── profiler.tar.gz           ← Docker 镜像（>100MB 放 GitHub Release）
```

---

## 十、FAQ

**Q: 为什么必须 `--privileged --pid=host`？**
A: perf 需 PMU 权限（`--privileged` 给 capabilities）；要采宿主机/其他容器进程需共享 PID ns（`--pid=host`）。preflight 第 6 项会自动验证。

**Q: 时区为什么是 Asia/Shanghai？**
A: 文件名时间戳用本地时区，"凌晨3点飙升"直接对应文件名 03 点。镜像内置 tzdata + `TZ=Asia/Shanghai`。

**Q: perf stat 事件 `<not supported>` 怎么办？**
A: 不同 CPU 微架构支持的事件不同。preflight 第 5 项会检测哪些不可用；指标面板对应项显示 N/A，不影响火焰图主功能。可用 `PERF_EVENTS` 环境变量换事件集。

**Q: 容器内 `_PyEval_EvalFrameDefault` 是什么？**
A: 容器自身 Python 进程（supervisord/collector）被 `-a` 全系统采样采到的噪声，不影响真实热点辨识。

**Q: 为什么不做 Web start/stop 采集？**
A: 会偏离"7×24 常驻黑匣子"考题定位（常驻是题眼——值班赶到时进程已恢复才需黑匣子）。改用事件标记 + 一键诊断：既全链路图形化，又不破坏常驻采集。
