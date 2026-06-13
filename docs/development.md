# Development Guide

This repository publishes one Python distribution: `abi-agent`.

## Source Tree

```
src/abi/
  agent/          ABIAgentInterface, JSON envelopes, agent context
  plugins/        Built-in analysis-type plugins
    metagenomic_plasmid/   Self-contained plugin package (engine in _engine/)
    metatranscriptomics.py Native ABI demo plugin
  autoplasm/      Backward-compatible re-export shim → plugins/metagenomic_plasmid/_engine/
  provenance.py   RunLogger, PipelineProgressRecorder, TSV provenance writers
  tools.py        ToolRegistry, ToolSkill, GenericCommandSkill, RunResult
  schemas.py      Canonical ExecutionPlan, PlanStep, SampleInput, SampleContext
  executor.py     GenericABIExecutor
  permissions.py  read_only / planning_write / execution
  diagnostics.py  Error taxonomy and diagnostic hints
  tables.py       StandardTableManager
  report.py       Generic report writer
  jobs/           HTTP Job Service (service, client)
  runtimes/       local, Nextflow runtimes
  exporters/      Nextflow DSL2 exporter
  mcp/            Optional MCP stdio server
  transports/     (future) transport-specific adapters
  cli.py          Typer CLI (abi, autoplasm entry points)
```

The `abi.autoplasm` package is a backward-compatible re-export shim that proxies
to `abi.plugins.metagenomic_plasmid._engine`. Internal code should import from
`abi.plugins.metagenomic_plasmid._engine` for the plasmid engine or from the ABI
core modules for shared infrastructure.

## Public SDK

| Module | Purpose |
| --- | --- |
| `abi.interfaces` | Plugin protocol classes |
| `abi.schemas` | Canonical schema types (SampleInput, ExecutionPlan, etc.) |
| `abi.tools` | ToolRegistry, ToolSkill, GenericCommandSkill |
| `abi.provenance` | RunLogger, PipelineProgressRecorder, TSV writers |
| `abi.errors` | ABIError, ConfigError, SampleSheetError, ToolError |
| `abi.testing` | Plugin contract assertions |

## Local Setup

```bash
pip install -e ".[dev]"
```

Useful checks:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short
```

`mypy` is intentionally scoped to `src/abi/`; the bundled pipeline is covered by
runtime tests and ruff first, with stricter typing left for later hardening.

## Runtime Assets

Small source assets are tracked:

- `config/`
- `envs/`
- `skills/`
- `plugins/`
- `examples/`
- `data/examples/`
- `scripts/`

Large or generated runtime state is ignored:

- `.mamba/`
- `resources/`
- `results/`
- `log/`
- Nextflow work directories

Tool execution resolves environments from `.mamba/envs/<env_name>/bin` by
default. Override with `ABI_MAMBA_ROOT`; `AUTOPLASM_MAMBA_ROOT` is still
accepted for compatibility.

## Agent Interfaces

`ABIAgentInterface` is the transport-neutral boundary. Keep CLI JSON, MCP,
OpenAI descriptors, `abi dispatch`, and Job Service behavior aligned with it.

Execution must remain gated: `abi run`, `abi_run`, and Job Service execution
submissions should return `confirmation_required` unless explicit confirmation
is passed.
