# <img src="figures/abi_logo.png" alt="ABI" width="36" height="36" align="top"> ABI — Agent-Bioinformatics Interface

ABI is a Python interface layer for agent-driven bioinformatics workflows. It
standardizes analysis plugins behind a common
`plan -> dry-run -> run -> inspect -> report` lifecycle, with provenance,
standard TSV tables, **multi-LLM tool descriptors** (OpenAI, Anthropic Claude,
Google Gemini, DeepSeek, 智谱 GLM, Kimi, Qwen, MiniMax), optional MCP transport,
Nextflow export/runtime support, DAG/contract static analysis, and a queue-backed
HTTP Job Service with force-kill capability.

[![PyPI](https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=blue)](https://pypi.org/project/abi-agent/)
[![Python](https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square)](https://pypi.org/project/abi-agent/)
[![CI](https://img.shields.io/github/actions/workflow/status/sleepinlava/abi/ci.yml?branch=master&style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-60%25%2B-brightgreen?style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-Sphinx-blue?style=flat-square)](https://sleepinlava.github.io/abi/)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)](https://github.com/sleepinlava/abi)
[![License](https://img.shields.io/pypi/l/abi-agent?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)

> :cn: [中文版](README.zh.md)

## Installation

```bash
pip install abi-agent

# Development install
pip install -e ".[dev]"

# Optional MCP server dependencies
pip install -e ".[dev,mcp]"
```

Python 3.10-3.13 is supported.

## Quick Start

```bash
# List installed analysis plugins
abi list-types

# Build a plan without executing tools
abi plan --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Write dry-run provenance and table skeletons
abi dry-run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Execute only after explicit confirmation
abi run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv \
  --confirm-execution

# Inspect and rebuild reports
abi inspect --result-dir results/
abi report --result-dir results/ --type metatranscriptomics

# Lightweight metadata query (~50ms, reads DAG + tool registry only)
abi query --type metatranscriptomics --what stages
abi query --type metatranscriptomics --what tools
abi query --type metatranscriptomics --what platforms
abi query --type metatranscriptomics --step qc_fastp --what inputs

# Export agent/runtime interfaces
abi export-nextflow --type metatranscriptomics --output workflow.nf
abi export-openai-tools --type metatranscriptomics --format responses    # legacy compat
abi export-tools --type metatranscriptomics --format openai --provider openai   # OpenAI
abi export-tools --type metatranscriptomics --format openai --provider deepseek # DeepSeek
abi export-tools --type metatranscriptomics --format openai --provider zhipu    # 智谱 GLM
abi export-tools --type metatranscriptomics --format anthropic           # Claude
abi export-tools --type metatranscriptomics --format gemini              # Gemini
abi export-agent-context --type metatranscriptomics --format json
abi doctor-agent --type metatranscriptomics

# Static contract / DAG validation (L1 literature + L2 path + L3 validation)
abi contract-lint --type metagenomic_plasmid
abi contract-lint --type metagenomic_plasmid --strict

# Headless agent dispatch (used by Job Service workers)
abi dispatch --command list-types --arguments '{}'

# Start MCP stdio server for Claude Desktop / Claude Code
abi-mcp

# Install ABI agent skills into Claude Code (~/.claude/skills/abi/)
abi install-skills

# Scientific figure compiler (validate, render, lint, export)
abi-sciplot validate --spec figure.yaml
abi-sciplot render --spec figure.yaml
abi-sciplot lint --spec figure.yaml
abi-sciplot list-plot-types

# Job Service with optional force-kill subprocess workers
abi job-service --workers 2 --store jobs.json --subprocess-workers
```

All agent-facing commands support `--output-json`.

## Built-In Analysis Types

| Type | Tools | Description |
| --- | --- | --- |
| `amplicon_16s` | 8 | 16S rRNA microbiome: cutadapt → vsearch merge/derep/denoise → SINTAX taxonomy → MAFFT+FastTree phylogeny → diversity (alpha/beta). **✅ 端到端验证通过** |
| `rnaseq_expression` | 6 | Bulk RNA-seq: fastp → STAR → featureCounts → build_count_matrix → DESeq2 → clusterProfiler. **✅ 端到端验证通过** |
| `wgs_bacteria` | 5 | Bacterial isolate WGS: fastp → SPAdes → Prokka → MLST → AMRFinderPlus. **✅ 端到端验证通过** |
| `metatranscriptomics` | 4 | Metatranscriptomics: fastp → STAR/HISAT2 → featureCounts. **✅ 端到端验证通过** |
| `metagenomic_plasmid` | 67 | Flagship plasmid analysis: QC → assembly → plasmid detection → annotation → abundance → community analysis → visualization. 10 conda envs, 84+-node DAG, 16 standard tables. **⚠️ 核心流程通过，全量待数据库补齐** |

The `autoplasm` CLI is preserved for backward compatibility:

```bash
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```

## Docker

Pre-built Docker images for all 5 plugins:

```bash
# Build a plugin image
docker build -f docker/Dockerfile.amplicon -t abi-amplicon .

# Run a workflow inside the container
docker run --rm -v $PWD:/data abi-amplicon \
  abi plan --type amplicon_16s --outdir /data/results

# Start all services with Docker Compose
docker compose -f docker/docker-compose.yml up -d
```

Images: `abi-amplicon` (~1.5 GB), `abi-rnaseq` (~2.5 GB), `abi-wgs` (~2.0 GB), `abi-metatranscriptomics` (~2.0 GB), `abi-plasmid` (~15 GB). See `docker/docker-compose.yml` for the full orchestration.

## Architecture

```
Agent Platforms (Claude / ChatGPT / Cursor / CI)
        │
        v
Transport Layer   CLI JSON  │  OpenAI/Anthropic/Gemini Tools  │  MCP  │  HTTP Job API  │  Skills  │  Query
        │
        v
ABIAgentInterface   plan / dry_run / run / inspect / report / dispatch / query
        │
        v
ABI Core            schemas  │  provenance  │  permissions  │  diagnostics
                    tables   │  tools       │  executor     │  report
                    contracts│  dag         │  figures      │  dag_planner
                    tsv_mapping  │  sciplot
        │
        v
Plugins             amplicon_16s/  rnaseq_expression/  wgs_bacteria/
                    metatranscriptomics/  metagenomic_plasmid/
                        (community_analysis, comparative_genomics,
                         visualization, co-occurrence_network)
        │
        v
Runtimes            local  │  Docker  │  Nextflow  │  HPC  │  cloud
```

### Design Principles

| Principle | Meaning |
| --- | --- |
| **Thick Core** | Lifecycle, permissions, diagnostics, provenance, standard tables, plugin discovery all live in Core. |
| **Thin Transport** | CLI, OpenAI tools, MCP, HTTP only adapt calls — no business logic. |
| **Clean Plugin** | Biology logic in plugins, generic mechanisms in Core. |
| **Agent Doesn't Code** | Agents call ABI through schemas, descriptors, JSON envelopes, and diagnostic hints. |

## Agent Transports

`ABIAgentInterface` is the stable transport-neutral boundary used by:

- CLI JSON through `--output-json`
- `abi dispatch --command <name> --arguments '<json>'` for headless subprocess dispatch
- **`abi query`** for lightweight metadata queries (~50ms) — pipeline stages, tools,
  platforms, and step-level I/O directly from DAG + tool registry, no plan required
- **Multi-LLM descriptors** from `abi export-tools --format openai|anthropic|gemini [--provider ...]` covering 7+ providers
- OpenAI-compatible descriptors from `abi export-openai-tools` (backward compat)
- MCP stdio server via `abi-mcp` (or `python -m abi.mcp.server`) — auto-generated from SSOT
- HTTP Job Service via `abi job-service` and `abi job submit/list/status/artifacts/cancel`
- Skills via `abi install-skills` (copies bundled SKILL.md files to `~/.claude/skills/abi/`)

**Plan summarization**: `abi plan` envelopes now include a `summary` field (pipeline stages,
key tools, platforms) so agents understand the workflow structure without reading the full
`execution_plan.json`. This saves 78-95% tokens on plan output for complex pipelines.

Agents can also get operating instructions programmatically:

```python
import abi
print(abi.get_agent_guide())        # compact operating guide for system prompt
print(abi.list_plugins_summary())   # list all installed analysis plugins
```

Execution tools require explicit confirmation. `abi run`, `abi_run`, and Job
Service execution submissions return `confirmation_required` unless
`confirm_execution=true` or `--confirm-execution` is provided.

## Job Service

```bash
# Start with in-process workers
abi job-service --host 127.0.0.1 --port 18791 --workers 1 --store jobs.json

# Start with subprocess workers for force-kill support
abi job-service --workers 2 --subprocess-workers

# Client commands
abi job submit --command run --analysis-type metatranscriptomics --confirm-execution
abi job status <JOB_ID>
abi job artifacts <JOB_ID>
abi job cancel <JOB_ID>          # SIGTERM → SIGKILL (3s grace) for subprocess workers
```

When `--subprocess-workers` is enabled, each job runs in an isolated `abi dispatch`
process and can be force-killed via SIGTERM on cancel. The job record tracks
`worker_pid` and `remote_scheduler_job_id` (for HPC/cloud backends).

## Development

```bash
pip install -e ".[dev]"

ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short

python -m build
python -m twine check dist/*
```

Repository-local bioinformatics environments are described under `envs/` and
resolved from `.mamba/envs/<env_name>/bin`. Set `ABI_MAMBA_ROOT` to override the
default `.mamba` root; `AUTOPLASM_MAMBA_ROOT` remains accepted for compatibility.

More details:

- [ABI Spec v0.1](docs/en/abi_spec_v0.1.md)
- [Development Plan](docs/en/next_development_plan.md)
- [API Reference](docs/en/api.rst) — Sphinx auto-generated from docstrings
- [abi_sciplot Design](docs/en/abi_sciplot_design.md) — Scientific figure compiler
- [Plugin Development Guide](docs/en/plugin_development_guide.md)
- [RNA-seq Workflow](docs/en/rnaseq_expression_workflow.md)
- [Workflow Validation](docs/en/workflow_validation.md)
- [HPC Development](docs/en/hpc_development.md)
- [OpenAI/LLM Interface Standard](docs/en/openai_interface_standard.md)
- [Agent Usage Guide](docs/en/agent_usage.md)
- [Job Service Guide](docs/en/job_service.md)
- [Release Guide](docs/en/release.md)
- [Dev Log](docs/en/devlog.md)
- [Work Report 2026-06-20](docs/en/work_report_2026-06-20.md) — 最新工作报告

## Public SDK

Plugin authors should depend on these public modules:

| Module | Contents |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan` (`ABI`-prefixed aliases available) |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV provenance writers |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError`, `MissingTemplateParamError` |
| `abi.contracts` | `ContractViolationError`, `validate_output_contract`, `evaluate_assertions`, `save_checksums_atomic`, `run_contract_lint`, `WorkflowSpec`, `WorkflowStepSpec`, `load_workflow_spec` |
| `abi.dag` | `infer_dag`, `ABIDAG`, `StepBinding` — DAG inference with L1 (literature) / L2 (path) / L3 (validation) layers |
| `abi.dag_planner` | `UniversalDAG`, `build_plan_from_dag`, `PathTemplateContext` — declarative plan generation from `pipeline_dag.yaml`. Replaces all hand-written `build_plan()` boilerplate; used by all 5 plugins including plasmid. (v1.3.2) |
| `abi.tsv_mapping` | `TSVMapper`, `generate_rows` — YAML-driven TSV/JSON/log parsing with 3 source types (tsv_mapping, json_mapping, key_value_log). Replaces ~14 boilerplate parser functions. (v1.3.2) |
| `abi.sciplot` | `FigureSpec`, `render_figure`, `validate_spec`, `lint_figure` — publication-grade scientific figure compiler. Pydantic schema, 15 plot types (including PCoA, volcano, stacked bar, heatmap, phylogeny), plotnine+seaborn backends, PDF/SVG/PNG/TIFF export, 3 themes, FigureLint, SHA256 provenance. (v1.4.0) |
| `abi.tool_descriptors` | `ABI_AGENT_TOOLS`, `TOOL_ALIASES`, `export_openai_compatible`, `export_anthropic`, `export_gemini`, `PROVIDER_PROFILES` |
| `abi.testing` | `assert_plugin_contract` |

Register third-party plugins with:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## License

MIT, see [LICENSE](LICENSE).
