# 2026CVM-kaohe-wujiahao

> 2026 CVM 校企合作考核项目 —— CPU 微架构性能测评。

## 个人信息

- 姓名：**<TODO 待填>**
- 学号 / 学校：<TODO>
- GitHub：[@xixirangrangadada](https://github.com/xixirangrangadada)

## 题目完成情况

| 题目 | 内容 | 状态 |
|---|---|---|
| 题1① | 多场景 perf stat 微架构指标采集 | ⬜ |
| 题1② | 火焰图生成与热点分析 | ⬜ |
| 题1③ | AI 辅助 Cache Line 微基准 | ⬜ |
| 题2 | 容器化持续 CPU Profiling（选做） | ⬜ 暂缓 |

## 测试环境

| 项 | 值 |
|---|---|
| CPU | 鲲鹏 920（HiSilicon，TaiShan v110 微架构），aarch64，4 核 @2.6GHz |
| 缓存 | L1d/i 256KiB / L2 2MiB / L3 128MiB（cache line：L1/L2=64B，L3=128B）|
| 虚拟化 | KVM guest |
| OS | openEuler，内核 4.19.208 |
| perf | 4.19.90（PMU 硬件事件用 raw event code 引用）|

## 目录结构

```
2026CVM-kaohe-wujiahao/
├── README.md                # 本文件
├── .gitignore
├── docs/                    # 工作过程文档（环境分析、知识点、进度）
├── resume/                  # 个人简历 PDF
├── task1/
│   ├── 1-perf-stat/         # 题1① 五场景 perf stat
│   ├── 2-flamegraph/        # 题1② 火焰图
│   └── 3-cache-line-test/   # 题1③ Cache Line 微基准
└── task2/                   # 题2 容器化 Profiling（选做）
```

## 工作流

代码与文档在**本地仓库**维护（学习与版本可控），通过 `ssh` 在云端 ARM 服务器执行 perf 采集与编译，产物（perf 输出、SVG 火焰图）回传本地入库。
