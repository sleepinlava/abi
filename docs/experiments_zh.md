# ABI Agent 实验

实验脚手架位于 `docs/experiments/`。其设计目标是测试未经训练的通用 Agent 在 ABI 控制层下是否比在无结构或弱结构化的替代方案中表现更好。

**注意：** 完整的论文投稿计划（包括三层 Demo 矩阵和 7 个月时间线）记录在 [`demo_plan.md`](demo_plan.md) 中。本文件描述原始的实验设计骨架；`demo_plan.md` 在规划用途上已取代本文件。

## 实验分组

- README 基线组
- Plain Python API 基线组
- Plain tool-calling 基线组
- ABI 控制层组

## 评估指标

初始指标 schema 位于 `docs/experiments/metrics.tsv`，跟踪完成率、dry-run 行为、参数错误、诊断恢复以及人工干预次数。

## Trace

Golden ABI 控制层 trace 存放在 `golden_traces/` 中
（`metagenomic_plasmid.jsonl`、`metatranscriptomics.jsonl`）。实验 trace 应复制或引用自 `docs/experiments/traces.jsonl`，并记录实验分组和任务 ID。

## 任务集

初始任务：

- 选择正确的分析类型
- 生成执行计划
- 执行 dry-run
- 诊断缺失资源
- 检查结果产物
- 汇总标准表
- 在未确认的情况下拒绝执行 `run`

## 实验中使用的当前插件

| 插件 | 工具 | 代码行数 | 标准表 |
| --- | --- | --- | --- |
| `metatranscriptomics` | fastp、STAR、HISAT2、featureCounts | 574 | `gene_expression.tsv` |
| `metagenomic_plasmid` | 67 个工具合约（39 个引擎文件，9,006 行） | ~9,000 | `plasmid_predictions.tsv`、`abundance.tsv` 等（16 张标准表） |
