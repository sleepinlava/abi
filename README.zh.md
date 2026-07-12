# <img src="figures/abi_logo.png" alt="ABI" width="36" height="36" align="top"> ABI — Agent-Bioinformatics Interface（面向 Agent 的生物信息学接口）

> :us: [English version](README.md)

ABI 是一个面向 AI Agent 驱动的生物信息学工作流的 Python 接口层。它将 **7 个分析插件** 标准化为统一的
`plan -> dry-run -> run -> inspect -> report` 生命周期，提供 provenance 审计追踪、
标准 TSV 表、**多 LLM 工具描述符**（OpenAI、Anthropic Claude、Google Gemini、
DeepSeek、智谱 GLM、Kimi、通义千问 Qwen、MiniMax），可选 MCP 传输、
Nextflow 导出/运行支持、DAG/合约静态分析、资源自动发现 + 安装、
论文级科研图形编译器（`abi-sciplot`，15 种图形类型，PDF/SVG/PNG/TIFF），
以及带 force-kill 能力的队列化 HTTP Job Service。

[![PyPI](https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=blue)](https://pypi.org/project/abi-agent/)
[![Python](https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square)](https://pypi.org/project/abi-agent/)
[![CI](https://img.shields.io/github/actions/workflow/status/sleepinlava/abi/ci.yml?branch=master&style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen?style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-Sphinx-blue?style=flat-square)](https://sleepinlava.github.io/abi/)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)](https://github.com/sleepinlava/abi)
[![License](https://img.shields.io/pypi/l/abi-agent?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)

> **工程状态（v1.5.5 源码，2026-07-12）：本地冻结候选。**
> 2294 项测试通过（83% 语句覆盖率），高风险模块覆盖率门禁全部通过，
> 全新环境安装 wheel 后 7 个内置插件 dry-run 全部通过。正式硬冻结仍需：
> 远程 Python 3.10-3.13 矩阵全绿、带生物学判定标准的固定真实工具 benchmark、
> 连续两个仅修缺陷的候选版本，以及连续一周无新增 P0/P1 缺陷。

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

# 显示版本号
abi --version

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

# 轻量级元数据查询（~50ms，仅读取 DAG + 工具注册表）
abi query --type metatranscriptomics --what stages
abi query --type metatranscriptomics --what tools
abi query --type metatranscriptomics --what platforms
abi query --type metatranscriptomics --step qc_fastp --what inputs

# 导出 Agent/运行时接口
abi export-nextflow --type metatranscriptomics --output workflow.nf
abi export-openai-tools --type metatranscriptomics --format responses    # 向后兼容
abi export-tools --type metatranscriptomics --format openai --provider openai   # OpenAI
abi export-tools --type metatranscriptomics --format openai --provider deepseek # DeepSeek
abi export-tools --type metatranscriptomics --format openai --provider zhipu    # 智谱 GLM
abi export-tools --type metatranscriptomics --format anthropic           # Claude
abi export-tools --type metatranscriptomics --format gemini              # Gemini
abi export-agent-context --type metatranscriptomics --format json
abi doctor-agent --type metatranscriptomics

# 资源发现与自动安装
abi check-resources --type metagenomic_plasmid
abi setup-resources --type metagenomic_plasmid --confirm

# 静态合约 / DAG 验证（L1 文献 + L2 路径 + L3 验证三层模型）
abi contract-lint --type metagenomic_plasmid
abi contract-lint --type metagenomic_plasmid --strict

# 无头 Agent 调度（Job Service worker 使用）
abi dispatch --command list-types --arguments '{}'

# 启动 MCP stdio 服务（用于 Claude Desktop / Claude Code）
abi-mcp

# 将 ABI agent skills 安装到 Claude Code（~/.claude/skills/abi/）
abi install-skills

# 科研图形编译器（验证、渲染、质检、导出）
abi-sciplot validate --spec figure.yaml
abi-sciplot render --spec figure.yaml
abi-sciplot lint --spec figure.yaml
abi-sciplot list-plot-types

# 带 force-kill 子进程 worker 的 Job Service
abi job-service --workers 2 --store jobs.json --subprocess-workers
```

所有面向 Agent 的命令均支持 `--output-json`。

## 可发布的运行时锁

ABI 可以固定生产工作流使用的 Conda 包、已注册工具、数据库、主机运行时、ABI
版本和 Git commit。普通 `lock-runtime` 是审计快照；`--strict` 才是发布门禁。

```bash
abi lock-runtime \
  --output-dir locks/candidate \
  --prefix abi-production \
  --mamba-root /root/autodl-tmp/.mamba \
  --resource-root /root/autodl-tmp/resources \
  --db-profile full \
  --strict
```

严格模式会 fail-closed：缺失或多余的 Conda 环境、未包含或失败的包快照、发布
范围内未解析的工具、未就绪资源、缺失的代码身份以及 dirty Git 工作树都会使
候选失败。只有在认证全部可选注册能力时才增加 `--require-all-tools`。

云端统一布局将质粒/宏基因组数据库放在 `resources/autoplasm/`，RNA 参考资源
放在顶层。托管云主机使用 `scripts/cloud/prepare_release_lock.sh` 原子生成带版本
和 commit、只读且经过 SHA-256 验证的正式锁。当前助手认证已经部署的六类流程；
`viral_viwrap` 在独立多环境和数据库包完成安装前不进入该发布范围。详见
[可发布的运行时锁](docs/zh/runtime_locks.md)。

## 内置分析类型

| 类型 | 工具数 | 说明 |
| --- | --- | --- |
| `amplicon_16s` | 10 | 16S rRNA 微生物组：cutadapt → vsearch 合并/去冗余/去噪 → SINTAX 分类 → MAFFT+FastTree 系统发育 → alpha/beta 多样性。**✅ 软件工作流验证通过** |
| `rnaseq_expression` | 5 | 批量 RNA-seq：fastp → STAR → featureCounts → build_count_matrix → DESeq2 → clusterProfiler。**✅ 软件工作流验证通过** |
| `wgs_bacteria` | 5 | 细菌分离株 WGS：fastp → SPAdes → Prokka → MLST → AMRFinderPlus。**✅ 软件工作流验证通过** |
| `metatranscriptomics` | 3 | 宏转录组：fastp → STAR/HISAT2 → featureCounts。**✅ 软件工作流验证通过** |
| `easymetagenome` | 10 | P0 宏基因组：fastp → kneaddata → kraken2 → bracken → humann4 + HUMAnN 工具集 → seqkit。3 种工作流预设（分类、功能、全流程），DAG 驱动规划，内置处理器。**✅ 软件工作流验证通过** |
| `viral_viwrap` | 1 | 病毒宏基因组：封装 ViWrap 1.3.1 — 分箱 → 分类 → 宿主预测 → 质量过滤。托管外部 CLI 插件，含环境检查器。**✅ 软件工作流验证通过** |
| `metagenomic_plasmid` | 64 | 旗舰质粒分析：QC → 组装 → 质粒检测 → 注释 → 丰度 → 群落分析 → 可视化。10 个 conda 环境，**90 节点声明式 DAG**，16 张标准表，8 张 sciplot 图形。**✅ 软件工作流验证通过；assembly 模式 RefSeq 验证通过（3 个质粒，genomad+platon，majority_vote）** |

`autoplasm` CLI 保留以维持向后兼容：

```bash
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```

## Docker

为 7 个插件中的 5 个提供预构建 Docker 镜像（`easymetagenome` 和 `viral_viwrap` 本地运行）：

```bash
# 构建插件镜像
docker build -f docker/Dockerfile.amplicon -t abi-amplicon .

# 在容器内运行工作流
docker run --rm -v $PWD:/data abi-amplicon \
  abi plan --type amplicon_16s --outdir /data/results

# 使用 Docker Compose 启动所有服务
docker compose -f docker/docker-compose.yml up -d
```

镜像：`abi-amplicon` (~1.5 GB)、`abi-rnaseq` (~2.5 GB)、`abi-wgs` (~2.0 GB)、`abi-metatranscriptomics` (~2.0 GB)、`abi-plasmid` (~15 GB)。完整编排见 `docker/docker-compose.yml`。

## 架构

```
Agent 平台 (Claude / ChatGPT / Cursor / CI)
        │
        v
传输层       CLI JSON  │  OpenAI/Anthropic/Gemini Tools  │  MCP  │  HTTP Job API  │  Skills  │  Query
        │
        v
ABIAgentInterface   plan / dry_run / run / inspect / report / dispatch / query
        │
        v
ABI 核心层          schemas  │  provenance  │  permissions  │  diagnostics
                    tables   │  tools       │  executor     │  report
                    contracts│  dag         │  figures      │  dag_planner
                    tsv_mapping  │  sciplot  │  resources  │  workflow
                    tool_descriptors  │  internal  │  results
        │
        v
插件层              amplicon_16s/  rnaseq_expression/  wgs_bacteria/
                    metatranscriptomics/  easymetagenome/
                    viral_viwrap/  metagenomic_plasmid/
        │
        v
运行时后端          local  │  Docker  │  Nextflow  │  HPC (SLURM/PBS)  │  cloud  │  Job Service
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
- **`abi query`** 轻量级元数据查询（~50ms）— 直接从 DAG + 工具注册表查询流水线阶段、工具、
  平台和步骤级 I/O，无需完整 plan
- **多 LLM 描述符** `abi export-tools --format openai|anthropic|gemini [--provider ...]` 覆盖 7+ 厂商
- `abi export-openai-tools` 生成的 OpenAI 兼容工具描述符（向后兼容）
- MCP stdio 服务 `abi-mcp`（或 `python -m abi.mcp.server`）— 从 SSOT 自动生成
- HTTP Job Service：`abi job-service` 和 `abi job submit/list/status/artifacts/cancel`
- Skills 安装 `abi install-skills`（将内置 SKILL.md 文件复制到 `~/.claude/skills/abi/`）

**Plan 摘要化**：`abi plan` 信封现在包含 `summary` 字段（流水线阶段、关键工具、平台），
Agent 无需读取完整 `execution_plan.json` 即可理解工作流结构。复杂流水线 plan 输出可节省 78-95% token。

Agent 也可以通过 Python API 获取操作指南：

```python
import abi
print(abi.get_agent_guide())        # 紧凑操作指南，可注入 system prompt
print(abi.list_plugins_summary())   # 列出所有已安装分析插件
```

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

# 与 CI 一致的测试、分支覆盖率和高风险模块门禁
python -m pytest tests/ src/abi/sciplot/tests/ \
  -m "not requires_tools" --strict-markers \
  --cov=src/abi --cov-branch --cov-report=json:coverage.json \
  --cov-fail-under=75
python scripts/check_module_coverage.py --coverage coverage.json

python -m build
python -m twine check dist/*
```

仓库本地的生信环境描述在 `envs/` 下，工具从 `.mamba/envs/<env_name>/bin` 解析。
设置 `ABI_MAMBA_ROOT` 可覆盖默认的 `.mamba` 根目录；`AUTOPLASM_MAMBA_ROOT` 保持兼容。

更多文档：

- [ABI Spec v0.1](docs/zh/abi_spec_v0.1.md)
- [开发指南](docs/zh/development.md)
- [API 参考](docs/en/api.rst) — Sphinx 自动从 docstring 生成
- [abi_sciplot 设计文档](docs/zh/abi_sciplot_design.md) — 科研图形编译器
- [插件开发指南](docs/zh/plugin_development_guide.md)
- [RNA-seq 工作流](docs/zh/rnaseq_expression_workflow.md)
- [工作流验证](docs/zh/workflow_validation.md)
- [HPC 开发](docs/zh/hpc_development.md)
- [OpenAI/LLM 接口标准](docs/zh/openai_interface_standard.md)
- [Agent 使用指南](docs/zh/agent_usage.md)
- [Job Service 指南](docs/zh/job_service.md)
- [发布指南](docs/zh/release.md)
- [开发日志](docs/zh/devlog.md)（[英文完整版](docs/en/devlog.md)）
- [生产验收清单](docs/zh/production_manual_acceptance_checklist.md)（[英文版](docs/en/production_manual_acceptance_checklist.md)）

## 公共 SDK

插件作者应依赖以下公共模块：

| 模块 | 内容 |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin`, `ABIResourcePlugin`, `ABIResultValidationPlugin` |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan`（含 `ABI` 前缀别名） |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV 审计追踪写入器 |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError`, `MissingTemplateParamError` |
| `abi.contracts` | `ContractViolationError`, `validate_output_contract`, `evaluate_assertions`, `save_checksums_atomic`, `run_contract_lint`, `WorkflowSpec`, `WorkflowStepSpec`, `load_workflow_spec` |
| `abi.dag` | `infer_dag`, `ABIDAG`, `StepBinding` — DAG 推断，支持 L1（文献）/ L2（路径）/ L3（验证）三层正确性模型 |
| `abi.dag_planner` | `UniversalDAG`, `build_plan_from_dag`, `PathTemplateContext` — 从 `pipeline_dag.yaml` 声明式生成执行计划，全部 7 个插件使用。（v1.3.2） |
| `abi.tsv_mapping` | `TSVMapper`, `generate_rows` — YAML 驱动的 TSV 列映射，替换 ~14 个手写解析器样板代码。（v1.3.2） |
| `abi.sciplot` | `FigureSpec`, `render_figure`, `validate_spec`, `lint_figure` — 论文级科研图形编译器。Pydantic schema，15 种图形类型（含 PCoA、火山图、堆叠柱状图、热图、系统发育热图），plotnine+seaborn 后端，PDF/SVG/PNG/TIFF 导出，3 套主题，FigureLint 质检，SHA256 溯源。（v1.4.0） |
| `abi.tool_descriptors` | `ABI_AGENT_TOOLS`, `TOOL_ALIASES`, `export_openai_compatible`, `export_anthropic`, `export_gemini`, `PROVIDER_PROFILES` |
| `abi.resources` | `check_resources`, `setup_resources` — 基于插件能力协议的资源发现与受控配置 |
| `abi.internal` | `ABIInternalHandler`, `InternalHandlerContext`, `InternalHandlerResult` — 传输无关的内部 DAG 节点，用于无外部工具的步骤 |
| `abi.results` | `ABIResultWriter`, `validate_abi_result_dir` — 共享结果/provenance 写入器 |
| `abi.tables` | `StandardTableManager` — YAML 驱动的表规范化 |
| `abi.config` | `resolved_mamba_root`, `PROJECT_ROOT`, `load_yaml`, `deep_merge` — 环境解析，4 级优先级 |
| `abi.testing` | `assert_plugin_contract` |

注册第三方插件：

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## 许可证

MIT，详见 [LICENSE](LICENSE)。
