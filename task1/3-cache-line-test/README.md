# 题1③ AI 辅助 Cache Line 微基准

C 语言 **pointer chasing** 程序：构造链表节点、节点间距 = stride、沿指针链遍历（绕过硬件预取器），不同 stride（1/2/4/8/16/32/64/128/256 字节）测延迟，验证 cache line 对性能的影响。

> ⚠️ 不能用朴素 `for i: sum += a[i*stride]`——硬件预取器会抹平 cache line 效应，曲线看不到拐点。必须 pointer chasing。

## 拐点（本机 cache line）

- **64B**：L1/L2 cache line 边界
- **128B**：L3 cache line 边界（鲲鹏 920 的 L3 line=128B，是本机特色，报告需标注双拐点）

## 目录

- `src/cache_line_test.c` —— 微基准源码（AI 辅助编写 + 人工 review）
- `results/` —— 各 stride 的 perf 输出 + 性能数据
- `flamegraphs/` —— stride=1 vs stride=64 火焰图
- `report.pdf` —— 步长 vs 延迟曲线 + 拐点微架构分析
- `ai-chat-log/` —— AI 工具对话记录

## 复现

<TODO：编译/运行/perf 采集命令，阶段3 填>
