# 知识点：阶段0 环境与 PMU 检测（ARM 版）

> 阶段0 执行复盘。覆盖"环境搭建 + PMU 可用性判定"全过程的知识点。
> **ARM 云版（鲲鹏 920 / TaiShan v110）**，附「WSL2 → ARM 环境选型复盘」。
> 配套：`任务分析与环境评估.md`、`进度跟踪.md`、`阶段0-环境与基建.md`。
> 日期：2026-06-14

---

## 〇、整体：把"环境"看成一条分层栈

PMU 数据要从最底层的物理硬件一路冒到 `perf` 的终端输出，中间每过一层都可能断裂——**任一层断裂 = `<not supported>`**。阶段0 的全部排查，就是沿这条栈逐层定位"断在哪一层"。

```
┌──────────────────────────────────────────────────┐
│ 执行 shell   本地 Git Bash → ssh arm → 云端 bash │ ← 命令到底进没进 ARM Linux
├──────────────────────────────────────────────────┤
│ perf 工具    perf 4.19（事件引用语法有坑，见三） │ ← raw code vs 符号名
├──────────────────────────────────────────────────┤
│ perf_event_open  系统调用入口 / paranoid 闸门    │ ← 权限
├──────────────────────────────────────────────────┤
│ 内核         perf_event 子系统 + armv8 PMU 驱动  │ ← KVM 透传了 armv8_pmuv3
├──────────────────────────────────────────────────┤
│ 虚拟化层     KVM（透传 PMU，与 WSL2/Hyper-V 不同）│ ← 关键差异
├──────────────────────────────────────────────────┤
│ 物理 CPU     鲲鹏 920 PMU 硬件计数器（真硬件）   │ ← 计数真正发生处
└──────────────────────────────────────────────────┘
```

**本次结论**：链路全通——KVM 向 guest 透传了 `armv8_pmuv3`，内核带 PMU 驱动，`paranoid=-1` 权限全开。只有 perf 4.19 的事件**引用语法**需要绕（raw code），与"平台能力"无关。

**方法论总纲（贯穿全文）**
1. **决策树驱动**：先定判据（盯死 4 个关键事件），一次跑完看结果，不瞎试。
2. **隔离变量**：把"权限"（paranoid）和"平台能力"（PMU 透传）两个维度拆开。
3. **读源头真相**：perf 是用户态工具，最终答案在 `dmesg` / `/sys` / `/proc`，不在 perf 的报错文案里。

---

## 一、ARM 硬件层：鲲鹏 920 / TaiShan v110

| 项 | 值 | 含义 |
|---|---|---|
| implementer | 0x48 | HiSilicon（华为海思）|
| part | 0xd01 | 鲲鹏 920 |
| 微架构 | **TaiShan v110** | 华为自研 ARM 服务器核 |
| 核数 / 频率 | 4 核 @2.6GHz | 同构（无 P/E 异构，区别 Alder Lake）|
| L1d / L1i | 各 256KiB（每核 64KiB）| |
| L2 | 2 MiB | |
| L3 | **128 MiB** | 大共享 L3，服务器特色 |
| cache line | L1/L2 = **64B**，L3 = **128B** | 题1③ 双拐点 |

**做题含义**：鲲鹏 920 是真服务器 ARM 芯片，PMU 完整，cache 层级典型——是非常好的微架构分析对象。报告里微架构代号写 "Kunpeng-920 / TaiShan v110"。

---

## 二、虚拟化层：KVM guest，但 PMU 透传

```
systemd-detect-virt → kvm
perf list → 有 armv8_pmuv3_0/* 事件   ← 关键：内核注册了 PMU 事件
perf_event_paranoid → -1              ← 全开
```

**为什么 KVM 能而 WSL2(Hyper-V) 不能**：hypervisor 对 PMU MSR（性能计数器寄存器）的处理决定一切。这些 MSR 是 ring-0 特权、与物理核强绑定；guest 看到的是 vCPU。hypervisor 要么不虚拟化这些 MSR（写进去被吞），要么做昂贵的 save/restore。
- **KVM（本机）**：选择透传 `armv8_pmuv3` 给 guest → PMU 可用 ✅
- **Hyper-V/WSL2（复盘见附录）**：不透传 → `<not supported>` ❌

**一锤定音的判据**：`perf list` 里有没有 `armv8_pmuv3_0/...` 事件 + `perf stat` 那 4 个关键事件出不出真实数字。

---

## 三、perf 工具层：raw event code 写法（本次核心知识点）

### 3.1 现象
perf list 明明列出了 `armv8_pmuv3_0/ll_cache_miss_rd/`，但 `perf stat -e armv8_pmuv3_0/ll_cache_miss_rd/` 报错：
```
event syntax error: unknown term
valid terms: event,long,config,config1,config2,name,period
```

### 3.2 根因
perf 4.19（老版本）解析 `pmu/X/` 时，把 **X 当作 config term list**（`event=0x..,cmask=..,umask=..`），**不支持 X 是裸事件符号名**。新版 perf 才支持 `pmu/event_name/` 直接用符号名。

### 3.3 解法：raw event code
事件 code 从 sysfs 读：
```
/sys/bus/event_source/devices/armv8_pmuv3_0/events/<事件名>
→ 内容形如 event=0x037
```

三种可用写法：
```bash
# 写法1：完整 raw（推荐，可加 name 别名）
perf stat -e armv8_pmuv3_0/event=0x037,name=LLC-load-misses/ -- sleep 1
# 写法2：r<hex> 短形式
perf stat -e r37 -- sleep 1
# 写法3：通用名（仅 perf 抽象层映射成功的，如 cycles/cache-misses/L1-dcache-load-misses 等）
perf stat -e cycles,cache-misses -- sleep 1
```

### 3.4 题目事件 → 本机映射

| 题目事件 | 本机写法 | code | 说明 |
|---|---|---|---|
| cycles/instructions/cache-references/cache-misses | 通用名 | — | perf 抽象层映射成功，直接用 |
| L1-dcache/icache-load-misses、branch-misses、dTLB/iTLB-load-misses | 通用名 | — | 同上 |
| context-switches、cpu-migrations | 通用名（software）| — | 不依赖 PMU |
| **LLC-load-misses** | `armv8_pmuv3_0/event=0x037,name=LLC-load-misses/` | 0x037 (ll_cache_miss_rd) | 通用名 `<not supported>`，必须 raw |
| **branch-instructions** | `armv8_pmuv3_0/event=0x021,name=branch-instructions/` | 0x021 (br_retired) | 同上 |

> `name=` 让 perf 输出显示可读名（对应题目原文），报告里好对照。

---

## 四、perf_event 内核层：paranoid 与事件体系

### 4.1 perf_event_paranoid（权限闸门）
`/proc/sys/kernel/perf_event_paranoid`：

| 值 | 含义 |
|---|---|
| -1 | 全部放开（**本机值**，root）|
| 0 | 禁 raw/tracepoint 给非特权 |
| 1 | 禁系统级 per-cpu 给非特权 |
| 2 | 禁内核态事件给非特权 |
| ≥3 | 更严 |

**最重要的区分**：paranoid 管"**权限**"，`<not supported>` 是"**平台能力**"——两码事。paranoid 放开救不回平台不支持的事件。

### 4.2 事件分类
- **hardware**：cycles/instructions/cache-misses/branch-misses… 真硬件计数器
- **software**：context-switches/cpu-migrations/page-faults… 内核软件统计，不依赖 PMU
- **cache**：L1-dcache-load-misses/dTLB-load-misses… 硬件缓存事件
- **raw**：`r<hex>` 或 `pmu/event=0xNN/`，直接写 PMU 事件码

### 4.3 错误分型（读报错就知道根因在哪层）
| 报错 | 含义 | 根因层 |
|---|---|---|
| `permission denied` / `Operation not permitted` | 权限不够 | paranoid / 非 root |
| `<not supported>` | 平台/内核不支持该事件 | 虚拟化 / 内核无驱动 / 通用名未映射 |
| `<not counted>` | 开了但没采到 | 采样配置 / 时间太短 |

---

## 五、协作层：ssh arm + heredoc（替代 WSL 跨边界）

本地 Claude Code 跑在 Windows（Git Bash / MINGW64），所有 ARM Linux 操作要跨边界到云端。**跨边界跑带路径/复杂脚本，默认走 heredoc stdin**：

```bash
ssh arm 'bash -s' <<'REMOTE'
echo "=== 在 ARM 上执行 ==="
perf stat -e cycles,instructions -- sleep 1
# 路径/glob 全程不被本地 shell 碰，最干净
REMOTE
```

**为什么 heredoc**：stdin 不是 argv，本地 shell 不扫描里面的路径/glob 做转换。若用 `ssh arm "命令"` 双引号包，里面的 `$var`、`$(...)`、反引号会被**本地** shell 先展开，易踩坑。

**ssh arm 别名**：`~/.ssh/config` 里 `Host arm → HostName 10.14.1.32, User root, IdentityFile ~/.ssh/id_arm`，ed25519 密钥免密。

---

## 六、stress-ng 源码编译（openEuler 仓库无）

openEuler 用 `dnf`/`yum`（RPM 系，**不是 apt**）。仓库里没有 stress-ng → 源码编译：
```bash
dnf install -y git
git clone --depth 1 https://github.com/ColinIanKing/stress-ng.git /root/stress-ng
cd /root/stress-ng && make -j4
ln -sf /root/stress-ng/stress-ng /usr/local/bin/stress-ng
```
依赖（autoconf/automake/libtool/make/gcc）本机已齐。

**语法坑**：`stress-ng --cpu-method list` 在 0.21+ 把 `list` 当非法 method 名 → 报错把所有 choices 列到 stderr 并返回非 0。列 method 要传无效值看 choices，或 `man stress-ng`。**做题直接用 method 名**（int64/matrixprod/queens/read64/rand-set 都在）。

---

## 七、诊断方法论（沉淀，可复用到任何性能/环境排查）

1. **决策树驱动**：先定"盯死哪几个关键事件"作判据（cache-misses / L1-dcache-load-misses / LLC-load-misses / dTLB-load-misses），一次跑完看结果。
2. **隔离变量**：用户态失败 → 提权 root 复测，把"权限"与"平台能力"拆开归因。
3. **分层下钻**：用户态 perf → 提权 → `perf list`（内核注册没）→ `/sys/.../events/`（事件 code）→ `dmesg`（硬件/驱动真相）。沿环境栈自上而下定位断裂层。
4. **读源头**：perf 是用户态工具，最终答案在内核启动日志和 `/sys`、`/proc`。
5. **诚实记录**：判据、每层证据、结论都写下来（含失败的尝试），报告里说清限制。

---

## 八、环境信息采集速查（ARM）

| 命令 | 看什么 |
|---|---|
| `lscpu` | CPU 型号 / 微架构 / 核数 / cache 层级 |
| `cat /proc/cpuinfo \| grep -E 'implementer\|part'` | ARM 实现 ID（0x48=HiSilicon, 0xd01=鲲鹏920）|
| `systemd-detect-virt` | 是否虚拟化（kvm/none）|
| `cat /proc/sys/kernel/perf_event_paranoid` | perf 权限闸门 |
| `perf list hw` / `perf list cache` | 内核注册的硬件/缓存事件 |
| `ls /sys/bus/event_source/devices/armv8_pmuv3_0/events/` | PMU 事件符号名 → 查 raw code |
| `cat /sys/.../cpu0/cache/index*/coherency_line_size` | 各级 cache line 大小 |
| `dmesg \| grep -iE 'perf\|pmu'` | PMU 驱动真相 |
| `taskset -c N <cmd>` | 钉到第 N 核，避免迁移噪声 |

---

## 附录：环境选型复盘（WSL2 → ARM）

> 本节是阶段0 早先在 WSL2 上排查的精华，保留作为"为什么换 ARM"的决策依据与方法论教材。WSL2 特有的坑（MSYS 路径转换、sudoers、wsl -u root 免密）在 ARM 路线下不再出现，但思路可迁移。

### A.1 WSL2 为什么采不到 PMU
根因链：
1. PMU 计数要读写 MSR，ring-0 特权、与物理核强绑定。
2. WSL2 跑在 Hyper-V 之上，**Hyper-V 不向 guest 透传 PMU MSR**。
3. 叠加：`microsoft-standard-WSL2` 内核**编译时没带 Alder Lake 的 PMU 驱动**。

`dmesg` 一锤定音：
```
Performance Events: unsupported p6 CPU model 151 no PMU driver, software events only.
```
（p6 model 151 = 0x97 = Alder Lake；内核识别到了 CPU，但明说没有 PMU 驱动。）

`perf list hw` 为空 → cycles/instructions 全 `<not supported>`，只剩 software events。

### A.2 推论
要真 PMU 只能上**裸金属/原生 Linux**，或透传 PMU 的虚拟化。普通云 VM 多半残缺，要选**透传 PMU 的**并自检（`systemd-detect-virt` + `perf list` 有无 PMU 事件 + 4 关键事件实测）。本项目的鲲鹏 920 KVM 正好透传 → 合格。

### A.3 WSL2 路线下的两个工程知识点（迁移到 ssh 仍成立）
- **跨边界脚本走 heredoc stdin**：WSL 用 `wsl -- bash -s <<'EOF'`，ARM 用 `ssh arm 'bash -s' <<'REMOTE'`——同理，stdin 不被本地 shell 扫描，路径/glob 不被改写。
- **MSYS_NO_PATHCONV 坑**：本地 Git Bash 会把 `$(ls /xxx/*)` 命令替换里的 Unix 路径转成 Windows 路径。复杂脚本走 heredoc 可完全规避。
