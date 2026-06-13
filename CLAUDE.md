# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Lint / format / type-check
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports

# Run all tests
pytest tests/ -v --tb=short

# Run a single test file or test function
pytest tests/unit/test_job_service.py -v
pytest tests/unit/test_job_service.py::test_job_service_requires_confirmation_for_execution_jobs -v

# Build and verify package
python -m build
python -m twine check dist/*

# Smoke-test installed CLI
abi list-types
abi dry-run --type metatranscriptomics --outdir /tmp/abi-smoke
autoplasm --help
```

## Architecture

ABI is a **Python library + CLI + Agent tool layer** for AI-driven bioinformatics. It is NOT a workflow engine — it is a **control plane** that sits between AI agents and bioinformatics tools.

```
Agent Platforms (Claude / ChatGPT / Cursor)
        │
Transport Layer   CLI JSON  │  OpenAI Tools  │  MCP  │  HTTP Job API
        │
ABIAgentInterface   plan / dry_run / run / inspect / report / dispatch
        │
ABI Core            schemas  │  provenance  │  permissions  │  diagnostics
                    tables   │  tools       │  executor     │  report
        │
Plugins             metagenomic_plasmid/    metatranscriptomics/
        │
Runtimes            local  │  Nextflow  │  HPC  │  cloud
```

### Design Principles

- **Thick Core, Thin Transport**: All business logic in `ABIAgentInterface` and Core; CLI/MCP/HTTP only adapt calls.
- **Plugin own biology, Core own mechanism**: Tool contracts, provenance, diagnostics are generic; tool selection, parsing, report interpretation are plugin-specific.
- **Agent never codes**: Agents interact via JSON envelopes, tool descriptors, and diagnostic hints — never by importing Python modules.
- **Execution is gated**: `run` returns `confirmation_required` unless `confirm_execution=true` is explicit.

### Source tree (what matters)

```
src/abi/
  agent/              ABIAgentInterface, JSON envelopes, agent context export
  plugins/
    metagenomic_plasmid/   Self-contained package (engine in _engine/)
    metatranscriptomics.py Native demo plugin (inline, no sub-package)
  autoplasm/          Backward-compatible re-export shim → metagenomic_plasmid/_engine/
  provenance.py       RunLogger, PipelineProgressRecorder, TSV writers (482 lines)
  tools.py            ToolRegistry, ToolSkill, GenericCommandSkill, RunResult (524 lines)
  schemas.py          Canonical types: SampleInput, ExecutionPlan, PlanStep, SampleContext
  executor.py         GenericABIExecutor — step iteration, tool invocation, provenance generation
  permissions.py      read_only / planning_write / execution levels
  diagnostics.py      Error taxonomy + DiagnosticHint for agent self-recovery
  jobs/service.py     HTTP Job Service with subprocess force-kill (SIGTERM → SIGKILL)
  cli.py              Typer CLI: abi + autoplasm entry points
```

### Key modules for plugin authors (Public SDK)

| Module | What it provides |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` protocols |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan` |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV provenance writers |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.testing` | `assert_plugin_contract` |

## Architectural invariants

### JSON envelope contract

Every `ABIAgentInterface` method returns a JSON string with exactly one of three statuses:
- `success` — `result` holds the payload
- `confirmation_required` — operation gated on user approval (only `run`)
- `error` — `error_code` + `diagnostic_hints` guide automated recovery

### Permission model (3 tiers)

- `read_only`: `list_types`, `inspect`, `validate_result` — no file writes, no tool execution
- `planning_write`: `plan`, `dry_run`, `report`, `export_nextflow` — writes plans/provenance, no tool execution
- `execution`: `run` — **requires `confirm_execution=true`**, writes provenance, executes real tools

### The two plugins

- **`metagenomic_plasmid`**: The complex plugin. Engine lives in `_engine/` (8,434 lines migrated from original AutoPlasm). 43 tool contracts, plasmid detection/annotation/abundance pipeline. Plugin class in `__init__.py` delegates to `._engine.*` modules.
- **`metatranscriptomics`**: The portability demo. 297 lines, 4 tools (fastp, STAR, HISAT2, featureCounts), one standard table (`gene_expression.tsv`). All logic inline — proves the same `ABIAgentInterface` drives radically different analyses.

### autoplasm/ is a backward-compat shim

`autoplasm/` (39 .py files) is a **re-export proxy** to `plugins/metagenomic_plasmid/_engine/`. It exists only so `autoplasm --help` and `from abi.autoplasm import ...` still work. Do not add new logic there — put it in `_engine/` or in the ABI core.

### Tool contract pipeline

The lifecycle for any tool is: `check_installation → plan → validate_inputs → select_params → build_command → run → parse_outputs → normalize_outputs`. GenericCommandSkill handles this from YAML tool_contracts; only tools with complex post-processing need Python subclasses.

### Provenance artifacts

Every run writes to `<outdir>/provenance/`: `commands.tsv`, `resolved_inputs.tsv`, `tool_versions.tsv`, `resources.json`, `environment.yml`, `run_summary.json`, `progress.json`/`progress.jsonl`, `step_logs/`. These are always written even on failure — post-mortem inspection is always possible.

### Job Service execution modes

- **In-process** (default): worker threads call `agent.dispatch()` directly. Cancel sets `cancel_requested=true` but cannot interrupt running dispatch.
- **Subprocess** (`--subprocess-workers`): each job runs via `abi dispatch` subprocess. Cancel sends SIGTERM (3s grace) then SIGKILL for true force-kill.

## Testing patterns

- Tests use mock agents (`RecordingAgent`, `SlowAgent`) that return controlled JSON envelopes.
- `tests/unit/test_job_service.py` — thread synchronization via `threading.Event` for worker state control.
- `tests/integration/test_dry_run.py` — end-to-end dry runs against real plugin configuration.
- Fixtures live in `tests/fixtures/`; curated example data in `data/examples/`.

## Adding a new analysis type

1. Implement `ABIPlugin` protocol in a new module or package under `plugins/`.
2. Create `abi-plugin.yaml`, `tool_registry.yaml`, `standard_tables.yaml` under `plugins/<name>/`.
3. Add tool contracts as `tool_contracts/*.yaml`.
4. Register in `pyproject.toml` under `[project.entry-points."abi.plugins"]`.
5. Verify with `assert_plugin_contract(plugin)` in tests.
