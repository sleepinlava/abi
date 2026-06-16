# Development Guide

This repository publishes one Python distribution: `abi-agent`.

## Source Tree

```
src/abi/
  agent/              ABIAgentInterface, JSON envelopes, agent context export
  plugins/            Built-in analysis-type plugins
    metagenomic_plasmid/   Self-contained plugin package (engine in _engine/)
    metatranscriptomics.py Native ABI demo plugin (574 lines)
  autoplasm/          Backward-compatible re-export shim → plugins/metagenomic_plasmid/_engine/
  _shared.py          Shared utilities: _read_tsv, _display_command, _plan_dict, _common_overrides
  provenance.py       RunLogger, PipelineProgressRecorder, TSV provenance writers
  tools.py            ToolRegistry, ToolSkill, GenericCommandSkill, SafeFormatDict, RunResult
  schemas.py          Canonical types: SampleInput, ExecutionPlan, PlanStep, SampleContext
  executor.py         GenericABIExecutor — step iteration, tool invocation, contract enforcement, provenance
  permissions.py      read_only / planning_write / execution levels
  diagnostics.py      Error taxonomy + DiagnosticHint + classify_exception
  interfaces.py       ABIPlugin, ABIDryRunPlugin, ABIInitializablePlugin protocols
  json_utils.py       JSON file/payload loading with ABIJSONError wrapping
  timeouts.py         Timeout parsing: parse_timeout_seconds, timeout_from_env_or_value
  dag.py              DAG inference engine for workflow dependency ordering
  config.py           Configuration loading and management
  resources.py        Resource status checking (on-disk existence validation)
  filesystem.py       Filesystem utilities
  results.py          Result writing and management
  tables.py           StandardTableManager
  report.py           Generic report writer
  contracts/          Contract definitions + step contract enforcement
  tool_descriptors.py Unified tool descriptor SSOT (3 format families, 7+ LLM providers)
  openai_contracts.py Backward-compat re-export shim → tool_descriptors
  jobs/               HTTP Job Service (service, client)
  runtimes/           local, Nextflow runtimes
  exporters/          Nextflow DSL2 exporter
  mcp/                Optional MCP stdio server (exposed via ``abi-mcp``)
  skills/             Agent skill files (41 bundled) → installed via ``abi install-skills``
  cli.py              Typer CLI (abi, abi-mcp, autoplasm entry points)
```

The `abi.autoplasm` package is a backward-compatible re-export shim that proxies
to `abi.plugins.metagenomic_plasmid._engine`. Internal code should import from
`abi.plugins.metagenomic_plasmid._engine` for the plasmid engine or from the ABI
core modules for shared infrastructure.

## Public SDK

| Module | Purpose |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` protocol classes |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan` |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV provenance writers |
| `abi.contracts.step_contract` | `ContractViolationError`, `validate_output_contract`, `evaluate_assertions`, checksum chaining |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.diagnostics` | Error taxonomy + `DiagnosticHint` + `classify_exception` |
| `abi.json_utils` | JSON file/payload loading with `ABIJSONError` |
| `abi.timeouts` | `parse_timeout_seconds`, `timeout_from_env_or_value` |
| `abi.testing` | `assert_plugin_contract` |

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

## Runtime Contract Enforcement

The generic executor enforces the step-level contract embedded in each
`PlanStep.params["_contract"]`. The DAG-driven planner copies this block from
`pipeline_dag.yaml`, so the DAG remains the source of truth for outputs and
runtime assertions.

Execution-time contract handling follows this order:

1. Verify upstream input checksums against `provenance/checksums.json`.
2. Run the external tool.
3. Resolve actual output files from `output_dir` when planned paths are abstract.
4. Validate output contracts and record output checksums.
5. Evaluate assertions against the resolved outputs.

Output validation supports file/directory existence, `min_size`, `extensions`,
directory `contains`, directory/file `min_files`, FASTA `min_contigs`, JSON
`required_keys`, and dotted JSON `schema` constraints.

Two executor details are intentional and should be preserved:

- `output_dir` itself is not pre-created. Some assemblers and workflow tools
  fail if their output directory already exists. The executor only creates its
  parent directory and any unrelated file-output parents.
- Actual-output resolution is deterministic and read-pair aware. If a tool
  writes `S1_R1.clean.fastq.gz` and `S1_R2.clean.fastq.gz` while the plan holds
  abstract paths such as `S1.fastp.clean_read1`, contract checks use the real
  R1/R2 files.

Regression coverage lives in `tests/unit/test_executor.py` and
`tests/unit/test_step_contract.py`.

## Runtime Assets

Small source assets are tracked:

- `config/`
- `envs/`
- `skills/` (inside ``src/abi/skills/`` — bundled with the package, installed via ``abi install-skills``)
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

`ABIAgentInterface` is the transport-neutral boundary. Keep CLI JSON (``--output-json``),
MCP (``abi-mcp``), OpenAI descriptors (``abi export-openai-tools``), Skills
(``abi install-skills``), ``abi dispatch``, and Job Service behavior aligned with it.

Execution must remain gated: `abi run`, `abi_run`, and Job Service execution
submissions should return `confirmation_required` unless explicit confirmation
is passed.

### Agent-Facing Commands

| Command | Purpose |
|---------|---------|
| `abi list-types --output-json` | Discover installed plugins |
| `abi export-agent-context --type <plugin>` | Machine-readable operating context |
| `abi doctor-agent --type <plugin>` | Human-readable operating guide |
| `abi install-skills` | Install SKILL.md files to `~/.claude/skills/abi/` |
| `abi export-openai-tools --type <plugin>` | OpenAI function-calling descriptors |
| `abi-mcp` | Start MCP stdio server |

### Python Agent API

```python
import abi
abi.get_agent_guide()          # returns compact operating guide (str)
abi.list_plugins_summary()     # returns list[dict] of (analysis_type, name, description)
```
