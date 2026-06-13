# ABI — Agent-Bioinformatics Interface（面向 Agent 的生物信息学接口）

> :us: [English version](README.md)

ABI 是一个面向 AI Agent 驱动的生物信息学工作流的 Python 接口层。它将分析插件标准化为统一的
`plan -> dry-run -> run -> inspect -> report` 生命周期，提供 provenance 审计追踪、
标准 TSV 表、OpenAI 兼容工具描述符、可选 MCP 传输、Nextflow 导出/运行支持，
以及带 force-kill 能力的队列化 HTTP Job Service。

[![PyPI](https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=blue)](https://pypi.org/project/abi-agent/)
[![Python](https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square)](https://pypi.org/project/abi-agent/)
[![License](https://img.shields.io/pypi/l/abi-agent?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)

## 安装

```bash
pip install abi-agent

# 开发安装
pip install -e ".[dev]"

# 可选 MCP 服务依赖
pip install -e ".[dev,mcp]"
```

支持 Python 3.10-3.13。

## 快速开始

```bash
# 列出已安装的分析插件
abi list-types

# 构建执行计划（不运行工具）
abi plan --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# 写入 dry-run 审计追踪和空表骨架
abi dry-run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# 仅在显式确认后执行
abi run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv \
  --confirm-execution

# 检查结果并重建报告
abi inspect --result-dir results/
abi report --result-dir results/ --type metatranscriptomics

# 导出 Agent/运行时接口
abi export-nextflow --type metatranscriptomics --output workflow.nf
abi export-openai-tools --type metatranscriptomics --format responses
abi export-agent-context --type metatranscriptomics --format json
abi doctor-agent --type metatranscriptomics

# 无头 Agent 调度（Job Service worker 使用）
abi dispatch --command list-types --arguments '{}'

# 带 force-kill 子进程 worker 的 Job Service
abi job-service --workers 2 --store jobs.json --subprocess-workers
```

所有面向 Agent 的命令均支持 `--output-json`。

## 内置分析类型

| 类型 | 实现 | 说明 |
| --- | --- | --- |
| `metatranscriptomics` | 原生 ABI 插件 | fastp -> STAR/HISAT2 -> featureCounts 可移植性示例。 |
| `metagenomic_plasmid` | 自包含插件包 | 从 AutoPlasm 迁移而来；引擎在 `plugins/metagenomic_plasmid/_engine/`。 |

`autoplasm` CLI 保留以维持向后兼容：

```bash
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```

## 架构

```
Agent 平台 (Claude / ChatGPT / Cursor / CI)
        │
        v
传输层       CLI JSON  │  OpenAI Tools  │  MCP  │  HTTP Job API
        │
        v
ABIAgentInterface   plan / dry_run / run / inspect / report / dispatch
        │
        v
ABI 核心层          schemas  │  provenance  │  permissions  │  diagnostics
                    tables   │  tools       │  executor     │  report
        │
        v
插件层              metagenomic_plasmid/    metatranscriptomics/
                    (自包含)                  (原生示例)
        │
        v
运行时后端          local  │  Nextflow  │  HPC  │  cloud
```

### 设计原则

| 原则 | 含义 |
| --- | --- |
| **Core 要厚** | 生命周期、权限、诊断、provenance、标准表、插件发现全部在 Core 中 |
| **Transport 要薄** | CLI、OpenAI tools、MCP、HTTP 只做调用适配，不含业务逻辑 |
| **Plugin 要清** | 生物学逻辑在插件，通用机制在 Core |
| **Agent 不写代码** | Agent 通过 schema、descriptor、JSON envelope 和 diagnostic hints 调用 ABI |

## Agent 传输层

`ABIAgentInterface` 是传输无关的稳定边界，被以下组件使用：

- 通过 `--output-json` 输出的 CLI JSON
- `abi dispatch --command <name> --arguments '<json>'` 无头子进程调度
- `abi export-openai-tools` 生成的 OpenAI 兼容工具描述符
- 可选 MCP stdio 服务 `python -m abi.mcp.server`
- HTTP Job Service：`abi job-service` 和 `abi job submit/list/status/artifacts/cancel`

执行类工具需要显式确认。除非传入 `confirm_execution=true` 或 `--confirm-execution`，
否则 `abi run`、`abi_run` 和 Job Service 执行提交会返回 `confirmation_required`。

## Job Service / 作业服务

```bash
# 进程内 worker（默认，无 force-kill）
abi job-service --host 127.0.0.1 --port 18791 --workers 1 --store jobs.json

# 子进程 worker（支持 force-kill）
abi job-service --workers 2 --subprocess-workers

# 客户端命令
abi job submit --command run --analysis-type metatranscriptomics --confirm-execution
abi job status <JOB_ID>
abi job artifacts <JOB_ID>
abi job cancel <JOB_ID>          # 子进程 worker: SIGTERM → 3s → SIGKILL
```

启用 `--subprocess-workers` 后，每个作业在独立的 `abi dispatch` 子进程中运行。
取消时发送 SIGTERM（3 秒后升级为 SIGKILL）。作业记录中跟踪 `worker_pid` 和
`remote_scheduler_job_id`（用于 HPC/cloud 后端）。

## 开发

```bash
pip install -e ".[dev]"

ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short

python -m build
python -m twine check dist/*
```

仓库本地的生信环境描述在 `envs/` 下，工具从 `.mamba/envs/<env_name>/bin` 解析。
设置 `ABI_MAMBA_ROOT` 可覆盖默认的 `.mamba` 根目录；`AUTOPLASM_MAMBA_ROOT` 保持兼容。

更多文档：

- [ABI Spec v0.1](docs/abi_spec_v0.1.md)
- [Agent 使用指南](docs/agent_usage.md)
- [开发指南](docs/development.md)
- [插件开发指南](docs/plugin_development_guide.md)
- [OpenAI 接口标准](docs/openai_interface_standard.md)
- [Job Service 指南](docs/job_service.md)
- [实验计划](docs/experiments.md)
- [宏基因组质粒插件](docs/metagenomic_plasmid.md)
- [发布指南](docs/release.md)

## 公共 SDK

插件作者应依赖以下公共模块：

| 模块 | 内容 |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan`（含 `ABI` 前缀别名） |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV 审计追踪写入器 |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.testing` | `assert_plugin_contract` |

注册第三方插件：

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## 许可证

MIT，详见 [LICENSE](LICENSE)。
