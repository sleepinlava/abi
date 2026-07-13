# ABI Documentation

> 自动生物信息学基础设施 — 统一的分析框架，覆盖质粒组学、宏基因组、RNA-seq、扩增子分析。

ABI (Automatic Bioinformatics Infrastructure) 通过声明式 DAG、可插拔分析类型和统一工具注册表，为生物信息学工作流提供可复现、可扩展的执行引擎。

---

## 📖 核心文档 / Core Documentation

### 用户指南 / Users

| 文档 | 中文 | English |
|:---|:---:|:---:|
| Agent 使用指南 | [zh](zh/agent_usage.md) | [en](en/agent_usage.md) |
| 宏基因组质粒分析 | [zh](zh/metagenomic_plasmid.md) | [en](en/metagenomic_plasmid.md) |
| RNA-seq 表达工作流 | — | [en](en/rnaseq_expression_workflow.md) |

### 开发者指南 / Developers

| 文档 | 中文 | English |
|:---|:---:|:---:|
| 开发指南 | [zh](zh/development.md) | [en](en/development.md) |
| 测试指南 | [zh](zh/testing.md) | [en](en/testing.md) |
| 测试审计报告 | — | [en](en/comprehensive-testing-audit.md) |
| 发布指南 | [zh](zh/release.md) | [en](en/release.md) |
| 插件开发指南 | [zh](zh/plugin_development_guide.md) | [en](en/plugin_development_guide.md) |
| 插件报告与图表规范 | — | [en](en/plugin_report_figure_spec.md) |
| HPC 开发指南 | [zh](zh/hpc_development.md) | [en](en/hpc_development.md) |
| Job Service | [zh](zh/job_service.md) | [en](en/job_service.md) |
| ABI SciPlot 设计 | — | [en](en/abi_sciplot_design.md) |
| 工作流验证 | [zh](zh/workflow_validation.md) | [en](en/workflow_validation.md) |
| OpenAI 接口标准 | [zh](zh/openai_interface_standard.md) | [en](en/openai_interface_standard.md) |
| 工程差距审计 | — | [en](en/full-engineering-gap-audit.md) [en](en/tool-engineering-gap-audit.md) |

### 项目规划 / Planning

| 文档 | Language |
|:---|:---|
| [ABI 重构计划](../ABI_REFACTOR_PLAN.md) | 中文 |
| [开发日志](en/devlog.md) | English |
| [论文执行计划](en/paper_execution_plan.md) | English |
| [生产验收检查清单](zh/production_manual_acceptance_checklist.md) | 中文 |

### 规范 / Specification

| 文档 | 中文 | English |
|:---|:---:|:---:|
| ABI 规范 v0.1 | [zh](zh/abi_spec_v0.1.md) | [en](en/abi_spec_v0.1.md) |

---

## 📊 项目状态 / Status

易变化的测试数、覆盖率、插件和运行时环境状态不在此处手工复制。请以
[CI](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)、`pyproject.toml`、
`environments.yaml` 和 `abi list-types` 的当前输出为准。ABI 支持 Python 3.10–3.13。

---

## 🔗 外部链接 / External Links

- 本仓库: `https://github.com/sleepinlava/abi`
- Conda 环境: `envs/` 目录
- 示例: `examples/`
- 脚本: `scripts/`
