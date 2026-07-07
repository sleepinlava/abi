# ABI 论文大纲

## Title

ABI：基于契约的智能体生物信息工作流规划与执行

## Abstract

概述可靠智能体生物信息执行的问题、ABI 的契约化规划模型、评测设计，以及在计划有效性、
命令正确性、dry-run 成功、溯源完整度和人工干预次数上的结果。

## Introduction

说明通用智能体执行生物信息流程的难点：工具参数复杂、环境约束多、数据分支依赖强、
数据库资源庞大且需要完整溯源。将 ABI 定位为一个暴露工作流意图、验证、dry-run 和
可复现执行界面的控制平面。

## System Architecture

介绍 thick-core、thin-adapter 架构：插件 manifest、`pipeline_dag.yaml`、工具注册表、
工具契约、规划器、runtime lock、溯源写入、CLI/MCP 适配器以及报告生成。

## Contract Model

定义 ABI 使用的契约层：工具契约、DAG 结构、模板参数 lint、报告产物元数据、
标准表 schema、资源 manifest 和运行时断言。

## Evaluation Design

使用 `bench/paper_tasks/tasks.yaml` 中冻结的任务矩阵和
`bench/paper_tasks/metrics_schema.yaml` 中定义的指标 schema。比较 README/手动 CLI、
直接 Python API、通用 LLM tool-calling，以及 ABI 介导的规划与执行。最终评分记录在
`metrics.tsv`。

## Results

报告任务级和汇总指标：计划有效性、命令正确性、dry-run 成功、溯源完整度、
人工干预次数，以及到达有效计划的时间。条件允许时加入置信区间或重复运行摘要。

## Case Studies

讨论宏基因组质粒、宏转录组和 RNA-seq expression dry-run 的代表任务。突出 ABI 的
query、dry-run、validation 和 provenance 界面如何避免常见规划错误。

## Limitations

说明对插件元数据质量的依赖、真实工具 smoke 执行仍有缺口、外部数据库可用性、
调度器/环境差异，以及 dry-run 成功与完整生物学验证之间的区别。

## Reproducibility Appendix

列出仓库版本、基准文件、环境设置、发布质量门、命令、评分说明和产物位置。
`bench/paper_tasks/tasks.yaml`、`bench/paper_tasks/metrics_schema.yaml` 和
`metrics.tsv` 是规范评测输入与评分表。
