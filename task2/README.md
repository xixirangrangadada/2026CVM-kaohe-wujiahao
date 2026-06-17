# 容器化持续 CPU Profiling（题2）

> 7×24 持续 CPU 采样"黑匣子"：`perf record` 常驻采集 + 按时间窗口轮转 + 历史保留（自动清理）+ 按时段回查 + 一键生成火焰图。Docker 容器化（aarch64，`--privileged` 运行）。

---

## 一、项目简介

**背景**：在线服务凌晨 CPU 飙升，值班赶到时进程已恢复，`perf top` 看不到故障现场，复盘只能靠猜。

**方案**：做一个常驻后台的持续 Profiling 工具，让 perf 像"黑匣子"一样持续采样。出故障时只需指定时间段，就能调出当时的 CPU 采样数据、生成火焰图定位根因。

**架构**：aarch64（鲲鹏 920），Docker 容器化，组件化设计（采集 / 清理 / 回查 / 火焰图四个独立组件，靠文件总线解耦）。

---

## 二、架构设计

### 组件化 + 文件总线

组件之间**不直接调用**，靠**约定目录 + 文件命名**（文件总线）解耦——采集器写文件，清理器/回查器/火焰图器各自读，互不感知。这是 Unix 哲学，也是 perf 生态本身的工作方式。

```
C1 采集器 ──写──→ /data/perf/perf-<start>-<end>.data ──读──→ C2 清理器（删过期）
                       │  文件总线
                       └──读──→ C3 回查（定位）──→ C4 火焰图（出 SVG）
```

| 组件 | 文件 | 职责 | 形态 |
|---|---|---|---|
| C1 采集器 | `collector.py` | perf record 后台采 + 60s 轮转 + SIGTERM 优雅停 | 常驻（supervisord）|
| C2 清理器 | `janitor.py` | 定时删 >24h 采样文件 | 常驻（supervisord）|
| C3 回查 | `query.py` | 时间段 → 定位命中文件 | 库 + CLI |
| C4 火焰图 | `flamegraph.py` | 采样文件 → SVG | 库 + CLI |

**命名约定（文件总线契约）**：`perf-<start>-<end>.data`，时间戳本地时区 `YYYYmmdd_HHMMSS`。文件名自带时段信息，回查/清理无需额外索引。

---

## 三、快速启动

### 方式一：从 tar 加载（推荐，评审一键验证）
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
# 准备 build context（含 profiler/ FlameGraph/ Dockerfile supervisord.conf）
docker build -t cpu-profiler .
docker run -d --privileged --pid=host \
  -v /lib/modules:/lib/modules:ro -v /sys:/sys \
  -v /data:/data -p 8080:8080 \
  --name cpu-profiler cpu-profiler
```

> **运行参数说明**（必填）：
> - `--privileged`：perf 访问 PMU 硬件性能计数器
> - `--pid=host`：共享宿主机 PID namespace，采到宿主机/其他容器的进程
> - `-v /lib/modules`：内核符号表，解析内核栈（否则内核函数显示 `[unknown]`）
> - `-v /data`：采样数据持久化卷
> - `-v /usr/local/bin/stress-ng`（测试时）：让容器内 perf 能读 stress-ng 符号

---

## 四、使用示例

容器启动后即开始持续采集（每 60s 一个采样文件，落 `/data/perf/`）。

### 1. 触发一次 CPU 飙升（宿主机或另一容器）
```bash
stress-ng --cpu 2 --cpu-method matrixprod -t 60s   # 记下起止时间
```

### 2. 回查该时段的采样文件
```bash
# 容器内执行（推荐，工具自包含）
docker exec cpu-profiler python3 -m profiler.query "2026-06-17 19:43:52" "2026-06-17 19:44:17"
```

### 3. 生成火焰图
```bash
docker exec cpu-profiler python3 -m profiler.flamegraph \
  "2026-06-17 19:43:52" "2026-06-17 19:44:17" --out /data/svg/matrixprod.svg
# 火焰图在宿主机 ./data/svg/ 下（挂载卷）
```

### 4. 优雅停止
```bash
docker stop cpu-profiler   # SIGTERM → collector 归档最后一段窗口后退出
```

---

## 五、配置项（环境变量，`docker run -e` 可覆盖）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ROTATE_SECONDS` | 60 | 轮转窗口（秒）|
| `RETAIN_HOURS` | 24 | 采样保留时长（小时）|
| `SAMPLE_FREQ` | 99 | perf 采样频率 Hz |
| `DATA_DIR` | /data/perf | 采样文件目录 |
| `SVG_DIR` | /data/svg | 火焰图输出目录 |

---

## 六、设计权衡

| 决策 | 选择 | 理由 |
|---|---|---|
| 语言 | Python | 本题本质是 shell 子进程编排 + 文件管理 + 简单 HTTP，Python 的 subprocess/Flask 对症；C++ 强项用不上 |
| 总线形态 | 文件系统约定（非消息中间件）| 组件耦合点是落盘文件，非实时事件；消息队列对"持续写文件+偶尔回查"零收益 |
| 部署形态 | 单容器多进程（supervisord）| 考题要"一个 tar 一键起"；组件共享 /data 卷；无伸缩需求 |
| 轮转方式 | 外层循环 subprocess | 命名可控、信号好处理、易测；不依赖 perf `--switch-output` 的不可控切片命名 |
| 优雅停 | SIGTERM→转发 SIGINT 给 perf | perf 对 SIGINT 优雅写盘，对 SIGTERM 丢数据 |
| 采集时序 | perf 先于目标进程启动 | 否则漏掉目标的 MMAP 事件，栈全 `[unknown]`（常驻采集器天然满足）|

---

## 七、测试验证

3 场景（matrixprod/rand-set/queens）端到端测试，火焰图均精准定位热点：

| 场景 | 实测热点 |
|---|---|
| matrixprod | `stress_cpu`（CPU 计算）|
| rand-set | `stress_vm_child`（访存）|
| queens | `queens_try` 17224 次（N-皇后回溯，分支密集）|

详见 `test/测试报告.md`。

---

## 八、前端界面

> 本版本聚焦后端核心（采集/回查/火焰图），Web 前端为选做项（评分 10%），当前未实现。
> 后端已预留 HTTP 接口位（`query`/`flamegraph` 库可直接被 Flask 包装），可在 8080 端口扩展。

---

## 九、目录结构

```
task2/
├── README.md                 ← 本文件
├── src/
│   ├── Dockerfile
│   ├── supervisord.conf
│   ├── profiler/             ← Python 包（6 组件）
│   │   ├── naming.py         ← 文件总线契约（单一真相源）
│   │   ├── config.py
│   │   ├── collector.py      ← C1
│   │   ├── janitor.py        ← C2
│   │   ├── query.py          ← C3
│   │   └── flamegraph.py     ← C4
│   └── test_naming.py        ← naming 单测
├── test/
│   ├── 环境验证记录.md        ← 地基验证（三关卡 + 踩坑）
│   ├── 测试报告.md            ← 3 场景热点验证
│   ├── verify_base.sh        ← 地基验证脚本
│   ├── test_scenario.sh      ← 3 场景测试脚本
│   └── screenshots/          ← 火焰图 SVG
├── ai-chat-log/              ← AI 协作记录导出
└── profiler.tar.gz           ← Docker 镜像（>100MB，放 GitHub Release）
```

---

## 十、FAQ

**Q: 为什么必须 `--privileged --pid=host`？**
A: perf 需要 PMU 权限（`--privileged` 给 capabilities）；要采宿主机/其他容器进程需共享 PID ns（`--pid=host`）。实测（见 `test/环境验证记录.md` 关卡1/2）证明缺一不可。

**Q: 时区为什么是 Asia/Shanghai？**
A: 文件名时间戳用本地时区，回查时"凌晨3点飙升"直接对应文件名 03 点，避免 UTC 换算。镜像内置 tzdata + `TZ=Asia/Shanghai`。

**Q: 容器内采到的 `_PyEval_EvalFrameDefault` 是什么？**
A: 容器内 supervisord/collector 自身的 Python 进程，被 `-a` 全系统采样采到的噪声，不影响真实热点辨识。详见测试报告。
