# ABI — Agent-Bioinformatics Interface

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

# Static contract / DAG validation
abi contract-lint --type metagenomic_plasmid
abi contract-lint --type metagenomic_plasmid --strict

# Headless agent dispatch (used by Job Service workers)
abi dispatch --command list-types --arguments '{}'

# Start MCP stdio server for Claude Desktop / Claude Code
abi-mcp

# Install ABI agent skills into Claude Code (~/.claude/skills/abi/)
abi install-skills

# Job Service with optional force-kill subprocess workers
abi job-service --workers 2 --store jobs.json --subprocess-workers
```

All agent-facing commands support `--output-json`.

## Built-In Analysis Types

| Type | Implementation | Notes |
| --- | --- | --- |
| `metatranscriptomics` | Native ABI plugin | fastp -> STAR/HISAT2 -> featureCounts portability demo. |
| `metagenomic_plasmid` | Self-contained plugin package | Migrated from AutoPlasm; engine under `plugins/metagenomic_plasmid/_engine/`. |

The `autoplasm` CLI is preserved for backward compatibility:

```bash
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```

## Architecture

```
Agent Platforms (Claude / ChatGPT / Cursor / CI)
        │
        v
Transport Layer   CLI JSON  │  OpenAI/Anthropic/Gemini Tools  │  MCP  │  HTTP Job API  │  Skills
        │
        v
ABIAgentInterface   plan / dry_run / run / inspect / report / dispatch
        │
        v
ABI Core            schemas  │  provenance  │  permissions  │  diagnostics
                    tables   │  tools       │  executor     │  report
        │
        v
Plugins             metagenomic_plasmid/    metatranscriptomics/
                    (self-contained)        (native demo)
        │
        v
Runtimes            local  │  Nextflow  │  HPC  │  cloud
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
- **Multi-LLM descriptors** from `abi export-tools --format openai|anthropic|gemini [--provider ...]` covering 7+ providers
- OpenAI-compatible descriptors from `abi export-openai-tools` (backward compat)
- MCP stdio server via `abi-mcp` (or `python -m abi.mcp.server`) — auto-generated from SSOT
- HTTP Job Service via `abi job-service` and `abi job submit/list/status/artifacts/cancel`
- Skills via `abi install-skills` (copies bundled SKILL.md files to `~/.claude/skills/abi/`)

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

- [ABI Spec v0.1](docs/abi_spec_v0.1.md)
- [Agent Usage Guide](docs/agent_usage.md)
- [Development Guide](docs/development.md)
- [Plugin Development Guide](docs/plugin_development_guide.md)
- [Development Plan](docs/abi_final_development_plan.md)
- [Workflow Validation Plan](docs/workflow_validation.md)
- [OpenAI Interface Standard](docs/openai_interface_standard.md)
- [Job Service Guide](docs/job_service.md)
- [Experiment Plan](docs/experiments.md)
- [Metagenomic Plasmid Plugin](docs/metagenomic_plasmid.md)
- [Release Guide](docs/release.md)

## Public SDK

Plugin authors should depend on these public modules:

| Module | Contents |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan` (`ABI`-prefixed aliases available) |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV provenance writers |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError`, `MissingTemplateParamError` |
| `abi.contracts` | `ContractViolationError`, `validate_output_contract`, `evaluate_assertions`, `save_checksums_atomic`, `run_contract_lint` |
| `abi.tool_descriptors` | `ABI_AGENT_TOOLS`, `TOOL_ALIASES`, `export_openai_compatible`, `export_anthropic`, `export_gemini`, `PROVIDER_PROFILES` |
| `abi.testing` | `assert_plugin_contract` |

Register third-party plugins with:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## License

MIT, see [LICENSE](LICENSE).
