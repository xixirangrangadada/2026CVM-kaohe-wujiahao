# 题2 AI 协作记录

> 本目录存放题2 开发全程的 AI 协作对话导出（考题"AI 工具使用"20%）。

## 真实对话记录

- **[题2-AI协作对话.md](题2-AI协作对话.md)** —— 题2 主体开发全程（167KB）
  - 覆盖：方案评估与重排 → 环境搭建（Docker 装/镜像源/磁盘）→ 地基验证三关卡（含踩坑排查）→ 核心 6 组件开发 → Docker 封装 → 3 场景测试 → 文档
  - 统计：用户发言 25 / Claude 回复 91 / 工具调用 127

- **[题2-优化-AI协作对话.md](题2-优化-AI协作对话.md)** —— 题2 优化阶段（34KB）
  - 覆盖：交付前质检（逐行核对考题）→ 统一日志系统 → P0 死锁 bug 修复 → 特殊样例测试（靠 log 判 bug）→ Web 前端（Flask+HTML）
  - 统计：用户发言 4 / Claude 回复 26 / 工具调用 55

## 体现的 AI 协作能力

- **需求拆解**：把"容器化持续 Profiling"拆成 6 个解耦组件 + 文件总线架构
- **迭代排错**（最有价值）：
  - Docker Hub 超时 → 换 DaoCloud 加速
  - 容器内 PMU 隔离疑问 → 三关卡实测确认 `--privileged` 开放
  - 关卡3 栈全 `[unknown]` → 定位是 perf 时序漏 MMAP 事件 → 修复
  - 跨设备 rename 坑 → `shutil.move`
  - 容器 UTC 时区 → 文件名错位 → tzdata + TZ 修复
- **诚实记录**：判定 bug（grep matrixprod）、采样噪声（_PyEval）均如实记录

---

> 相关：题1 的 AI 协作真实对话记录见 `task1/3-cache-line-test/ai-chat-log/`。
