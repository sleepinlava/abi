# Plugin Development Guide

ABI plugins expose biological analysis types behind the shared lifecycle API.

## Recommended Declarative Interface

Place `abi-plugin.yaml` beside your plugin module and inherit from
`DeclarativeABIPlugin`. The base class reads plugin identity, the tool registry,
and standard-table paths from the manifest, so those values are declared once:

```python
from abi.plugin import DeclarativeABIPlugin


class MyPlugin(DeclarativeABIPlugin):
    def load_config(self, config_path=None, **kwargs): ...
    def build_plan(self, config, *, check_files=True): ...
    def parse_outputs(self, tool_id, output_dir, sample_id): ...
    def write_report(self, plan, result_dir): ...
```

Monorepos that keep declarations away from the Python module may set one class
attribute, for example `plugin_root = Path("plugins/my_analysis")`.

The base class validates the manifest and all declared paths during import.
Discovery also requires the entry-point name, manifest `plugin_id`, and manifest
`entry_point` to agree. Runtime registry, tool-contract, and environment checks
remain unchanged; use `abi contract-lint --strict` before publishing.

## Low-level Python Interface

Implement the `abi.interfaces.ABIPlugin` protocol:

- `plugin_id`
- `display_name`
- `description`
- `report_title`
- `load_config()`
- `build_plan()`
- `registry()`
- `table_schemas()`
- `parse_outputs()`
- `write_report()`

Register the plugin with:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

The entry-point key must exactly match `plugin_id` in `abi-plugin.yaml`.

## Plugin Directory

Recommended layout:

```text
plugins/my_analysis/
  abi-plugin.yaml
  config_default.yaml
  sample_sheet_template.tsv
  tool_registry.yaml
  standard_tables.yaml
  tool_contracts/
    tool_a.yaml
  skills/               ← SKILL.md files bundled with the package
    tool_a/SKILL.md
  _engine/             ← optional: complex engine code (see metagenomic_plasmid)
```

For complex plugins with substantial internal logic, use a self-contained
package with a private `_engine/` subdirectory. See `plugins/metagenomic_plasmid/`
for the canonical example.

## Skills and Agent Integration

Each tool should have a `SKILL.md` file under `skills/<tool_name>/SKILL.md`.
Skills are bundled inside the package at `src/abi/skills/` and installed into
Claude Code via:

```bash
abi install-skills      # → ~/.claude/skills/abi/
```

To add a new skill, create the directory and SKILL.md file under
`src/abi/skills/<tool_name>/SKILL.md`. The `abi_agent/SKILL.md` skill teaches
Claude Code how to use the `abi` CLI itself; other skills document individual
bioinformatics tools.

A tool skill explains scientific purpose, parameters, inputs, outputs, and failure modes. It does not add a new MCP function or bypass the ABI lifecycle.

## Make a Plugin Callable by Agents

Agent transports expose shared lifecycle tools. A new plugin becomes callable through the `analysis_type` argument after entry-point discovery; do not create separate `abi_my_plugin_plan` or `abi_my_plugin_run` tools.

### Provide discoverable biological identity

The manifest identity is what an untrained Agent sees through `abi_list_types` and `abi_export_agent_context`:

```yaml
abi_version: "0.1"
plugin_id: my_analysis
display_name: My Biological Analysis
description: "Analyzes <input> to produce <main biological result>."
report_title: My Biological Analysis Report
entry_point: my_package.plugin:MyPlugin
```

Write `description` for plugin selection. State the biological goal, expected input class, and primary output; avoid implementation-only or marketing text.

The entry-point key, manifest `plugin_id`, and plugin class identity must match. Include `config_default.yaml` and `sample_sheet_template.tsv` so users and Agents can start from explicit schemas instead of inventing metadata.

### Make the workflow queryable

`abi_query` reads the declarative DAG and tool registry. Use stable node and tool IDs, declare platforms, and give every node meaningful inputs, outputs, dependencies, and descriptions.

An Agent should be able to answer these questions without reading source code:

```bash
abi query --type my_analysis --what stages
abi query --type my_analysis --what tools
abi query --type my_analysis --what platforms
abi query --type my_analysis --step qc_tool --what inputs
abi query --type my_analysis --step qc_tool --what outputs
```

If a resource belongs to a specific node, make that relationship explicit so step-level resource queries and preflight diagnostics can explain what is missing.

### Keep planning safe and deterministic

- `load_config()` may read configuration but must not install resources or run tools.
- `build_plan()` must produce deterministic steps and paths from explicit inputs.
- `plan` and `dry_run` may write review artifacts but must not execute external analysis tools.
- Real tool execution must happen only through `run` after the shared confirmation gate.
- `report` must consume existing published results and must not silently rerun the workflow.

Agent permission profiles are owned by the ABI core. Plugins must not create hidden execution paths inside planning, parsing, reporting, or diagnostics.

### Publish results that an Agent can interpret

The plugin's `table_schemas()` defines the `standard_tables` returned by `abi_export_agent_context`. Use stable names, columns, units, identifiers, and missing-value conventions.

Parsers should normalize tool outputs into these tables. Reports and figures should read published tables instead of re-parsing raw logs or private intermediate files.

Implement `published_outputs(plan)` for stable final artifacts that do not fit a standard table. Publish methods, provenance, limitations, and branch-qualified manifests when a workflow has multiple output branches.

Raise ABI error types or provide structured diagnostic hints for recoverable failures. Agents use `error_code` and `diagnostic_hints`; raw tracebacks are not an operating contract.

### Verify the Agent context

After installing the plugin, inspect its machine-readable contract:

```bash
abi list-types --output-json
abi export-agent-context --type my_analysis
abi doctor-agent --type my_analysis
abi export-tools --type my_analysis --format openai
```

Confirm that the plugin description is sufficient for selection, the standard table list is complete, and execution tools are excluded unless explicitly requested.

Do not hand-edit OpenAI, Anthropic, Gemini, or MCP schemas for a plugin. ABI generates lifecycle descriptors from one source of truth and injects the plugin scope during export.

### Add an end-to-end Agent contract test

In addition to plugin unit tests, cover discovery, context export, planning, dry-run, confirmation, and result validation through `ABIAgentInterface`.

```python
import json

from abi.agent import ABIAgentInterface


def call(tool, arguments):
    return json.loads(ABIAgentInterface().dispatch(tool, arguments))


def test_agent_can_discover_and_plan_my_plugin(tmp_path, plugin_fixture):
    listed = call("abi_list_types", {})
    plugin_ids = {
        row["analysis_type"]
        for row in listed["result"]["analysis_types"]
    }
    assert "my_analysis" in plugin_ids

    context = call(
        "abi_export_agent_context",
        {"analysis_type": "my_analysis"},
    )
    assert context["status"] == "success"
    assert context["result"]["standard_tables"]
    assert "abi_run" in context["result"]["unsafe_tools"]

    common = {
        "analysis_type": "my_analysis",
        "config_path": str(plugin_fixture.config),
        "sample_sheet": str(plugin_fixture.sample_sheet),
    }
    plan = call("abi_plan", {**common, "outdir": str(tmp_path / "plan")})
    assert plan["status"] == "success"

    dry = call("abi_dry_run", {**common, "outdir": str(tmp_path / "dry")})
    assert dry["status"] == "success"

    run = call("abi_run", {**common, "confirm_execution": False})
    assert run["status"] == "confirmation_required"
```

Add a known-good lifecycle under `golden_traces/<plugin_id>.jsonl` and replay it in `tests/integration/test_golden_traces.py`. The trace should include error recovery and a confirmation-required run attempt.

Define `plugin_fixture` in the plugin test suite so it writes a valid minimal config and sample sheet. Keep these fixtures synthetic, small, and independent of machine-specific resource paths.

### Agent-callable plugin checklist

- The plugin is present in `abi list-types --output-json`.
- Context export names the correct standard tables, artifacts, permissions, and errors.
- DAG stages, tools, platforms, inputs, outputs, and resources are queryable.
- Default config and sample sheet templates contain no ambiguous fields.
- Plan, check, and dry-run work without executing external tools.
- `abi_run` returns `confirmation_required` before approval.
- Real results pass `abi_validate_result` and reports use standard tables.
- Provider descriptors and MCP profiles require no plugin-specific transport code.
- Golden traces and regression tests cover the complete Agent lifecycle.

## Tool Contracts

Contracts are the authoritative machine-readable tool declarations:

- `tool_id`
- `category`
- `execution.executable`
- `execution.command_template`
- declared input/output template fields
- normalized standard table names

`tool_registry.yaml` is a compact policy index. Each contract must have exactly
one registry entry, but the entry only needs the tool ID and runtime policy:

```yaml
tools:
  - id: fastp
    required: true
    default_enabled: true
    skill_path: skills/fastp/SKILL.md
```

Do not repeat `name`, `category`, `executable`, or `command_template` there.
Legacy registries may still contain those fields, but ABI rejects a conflicting
duplicate instead of silently choosing one declaration.

Environment names are **not** stored in individual contracts or registries.
They are centralized in `environments.yaml` under `tool_assignments:` (one mapping
per plugin), and the `ToolRegistry` injects the correct `env_name` at runtime.
See: `environments.yaml`, `scripts/emit_env_yamls.py`.

Use `assert_plugin_contract(plugin)` in plugin tests.

## Step Output Contracts

Complex plugins can embed per-step contracts in the execution plan. For the
DAG-driven metagenomic plasmid plugin, each node in `pipeline_dag.yaml`
declares its `outputs` and optional `assertions`; the planner copies those
fields into `PlanStep.params["_contract"]` for runtime enforcement.

Supported output checks include:

- `min_size`: minimum file or directory byte size, such as `"1KB"`.
- `extensions`: allowed file suffixes, such as `[.fastq, .fastq.gz]`.
- `contains`: required files inside an output directory.
- `min_files`: minimum number of regular files under a directory, useful for
  generated indexes.
- `min_contigs`: minimum FASTA contig count.
- `required_keys`: required top-level keys for JSON outputs.
- `schema`: dotted JSON fields with simple type/range constraints.

Checks must be nested under the output's `contract` key; placing `min_size`
or other checks directly beside `type` is invalid and will not be enforced:

```yaml
outputs:
  clean_read1:
    type: file
    format: fastq.gz
    path: "{outdir}/{sample_id}.clean.fastq.gz"
    contract:
      min_size: "1KB"
      extensions: [".fastq.gz"]
```

Assertions are evaluated after output validation against `output_files`,
`output_json`, and `return_code`. Example:

```yaml
assertions:
  - "output_json.summary.after_filtering.total_reads > 0"
  - "output_files.clean_read1 exists"
```

When declaring outputs for tools that create their own output directory, keep
using `output_dir`. The generic executor intentionally creates only the parent
directory, because some tools fail if `output_dir` exists before execution.

If a planner emits abstract output paths while the tool writes fixed names, make
the contract `format` and filename convention unambiguous. The executor resolves
actual files by `output_dir`, format, sample id, and R1/R2 read-pair hints before
checking contracts.

## Standard Tables

Parsers must only write tables declared by the plugin. Empty tables should still
exist with stable headers so agents can inspect results without parsing raw
tool output.

## Published Outputs

Plugins may implement `published_outputs(plan)` to add plugin-specific final
artifacts to the transport-neutral `RuntimeResult.outputs` mapping. Return only
stable, existing paths and use labels that do not collide with the common ABI
bundle keys. This hook is for discoverable final artifacts such as a versioned
artifact manifest; intermediate files remain discoverable through the execution
plan and should not be published individually.

When one preset can produce multiple final reports, publish branch-qualified
labels and add generic aliases only when exactly one complete report exists.
EasyMetagenome, for example, publishes `report_manifest` for a single branch
and `taxonomy_report_manifest` plus `functional_report_manifest` for its
combined preset. Versioned manifests should identify their workflow and link
the standard tables and report they summarize.

## Shared Infrastructure

Plugins should import from the public SDK:

| Module | Use |
| --- | --- |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan` |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV writers |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.diagnostics` | `DiagnosticHint`, `classify_exception`, `ERROR_CODES` |
| `abi.json_utils` | `load_json_file`, `load_json_payload` with `ABIJSONError` |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin`, `ABIPublishedOutputsPlugin` protocols |
| `abi.plugin` | `DeclarativeABIPlugin` — manifest-backed identity, registry, and table schemas |
| `abi._shared` | `_read_tsv`, `_display_command`, `_plan_dict`, `_common_overrides` |
| `abi.dag_planner` | `UniversalDAG`, `build_plan_from_dag`, `PathTemplateContext` — DAG-driven `build_plan()` (added 2026-06-18) |
| `abi.tsv_mapping` | `TSVMapper`, `generate_rows` — declarative TSV column mapping (added 2026-06-18) |
| `abi.sciplot` | `FigureSpec`, `render_figure`, `validate_spec`, `lint_figure` — publication-grade figure compiler. 15 plot types (PCoA, volcano, stacked bar, heatmap, phylogeny), plotnine+seaborn backends. (v1.4.0, added 2026-06-20) |
| `abi.contracts` | `WorkflowSpec`, `WorkflowStepSpec`, `load_workflow_spec`, `run_contract_lint` — L1/L2/L3 workflow declaration + validation |
| `abi.report` | `write_plugin_report`, `render_figures_via_sciplot` — report generation + figure rendering |

## DAG-Driven Plan Construction

Instead of writing a hand-coded `build_plan()` that iterates samples and
constructs `PlanStep` objects (~200 lines of boilerplate), plugins must
declare their workflow in a `pipeline_dag.yaml` file and use the universal
DAG planner:

```python
# In your plugin's build_plan():
def build_plan(self, config, *, check_files=True):
    context = self.build_sample_context(config, check_files=check_files)
    from abi.dag_planner import build_plan_from_dag
    return build_plan_from_dag(
        self.root / "pipeline_dag.yaml", config, context
    )
```

### `pipeline_dag.yaml` structure

```yaml
pipeline_id: my_analysis
platforms: [illumina]

# Category → subdirectory mapping
category_dirs:
  qc: 01_qc
  alignment: 02_alignment

nodes:
  qc_fastp:
    tool_id: fastp
    category: qc
    scope: per_sample        # per_sample (default) or cross_sample
    depends_on: []
    inputs:
      read1: {type: file, source: sample_sheet}
      read2: {type: file, source: sample_sheet}
    outputs:
      clean_read1:
        type: file
        path: "{outdir}/{category_dir}/{sample_id}/{sample_id}_R1.clean.fastq.gz"
      output_dir:
        type: directory
        path: "{outdir}/{category_dir}/{sample_id}"

  aggregation_step:
    tool_id: my_aggregator
    scope: cross_sample      # runs once, collects all per-sample outputs
    depends_on: [qc_fastp]
    inputs:
      per_sample_data: {aggregate: per_sample_outputs}
```

### Declarative TSV Parsing

For tools with simple TSV/JSON/log output, declare column mappings in `parsers.yaml`
instead of writing Python parser functions. Three source types are supported:

| Source Type | Use Case | Example Tool |
|---|---|---|
| `tsv_mapping` | CSV/TSV column remap | AMRFinderPlus, featureCounts |
| `json_mapping` | Nested JSON flatten | fastp (summary before/after blocks) |
| `key_value_log` | Delimited log parsing | STAR (Log.final.out pipe-delimited) |

Example `tsv_mapping`:

```yaml
parsers:
  my_tool:
    source:
      type: tsv_mapping
      pattern: "*.tsv"
      delimiter: "\t"
    target_table: my_standard_table
    columns:
      gene_name: {sources: [Gene, gene_name], default: ""}
      coverage:  {sources: [Coverage, cov_pct], default: "0"}
    constants:
      tool: my_tool
```

Wire it up in `parse_outputs()`:

```python
def parse_outputs(self, tool_id, output_dir, sample_id):
    if self._tsv_mapper.has_parser(tool_id):
        rows = self._tsv_mapper.parse(tool_id, output_dir, sample_id=sample_id)
        if rows:
            return {self._tsv_mapper.get_target_table(tool_id): rows}
    # Complex parsers remain as Python
    ...
```

## Testing Plugins

Every plugin must include tests. The minimal test suite for a new plugin covers
three areas: contract compliance, registry loading, and plan generation.

### Minimum test file (`tests/test_my_plugin.py`)

```python
import pytest
from abi.testing import assert_plugin_contract
from your_package.plugin import MyPlugin  # your installed plugin entry point


def test_plugin_contract():
    """Plugin satisfies the ABIPlugin protocol."""
    plugin = MyPlugin()
    assert_plugin_contract(plugin)


def test_registry_loads():
    """Tool registry YAML parses without error."""
    plugin = MyPlugin()
    registry = plugin.registry()
    tools = registry.list_tools()
    assert len(tools) > 0
    # Verify expected tools are registered
    tool_ids = [t["id"] for t in tools]
    assert "fastp" in tool_ids


def test_build_plan(mock_sample_context, tmp_path):
    """build_plan() returns valid ExecutionPlan for default config."""
    plugin = MyPlugin()
    config = plugin.load_config()
    config["outdir"] = str(tmp_path)
    plan = plugin.build_plan(config)
    assert len(plan.steps) > 0
    # QC step always comes first
    assert plan.steps[0].step_id.startswith("qc_")


def test_parse_outputs_handles_missing_files(tmp_path):
    """Parsers return empty results (not errors) for missing output files."""
    plugin = MyPlugin()
    result = plugin.parse_outputs("fastp", tmp_path, "S1")
    assert isinstance(result, dict)


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_real_execution_smoke(tmp_path):
    """Full pipeline executes with synthetic data."""
    # Generate minimal test data, run real tools, verify outputs...
    pass
```

### Fixtures available to plugin tests

All fixtures from `tests/conftest.py` are available without import:

| Fixture | Type | Use |
|---------|------|-----|
| `mock_sample` | `ABISample` | Single-sample input with illumina platform |
| `mock_sample_context` | `ABISampleContext` | Single-sample context with two groups |
| `mock_contract_dict` | `dict` | Minimal valid tool contract for scaffolding |
| `tmp_project` | `Path` | Temporary dir with results/logs/provenance/tables/ |

### Benchmark tests

For value-level validation, use `run_benchmark()`:

```python
from abi.testing.benchmark import run_benchmark

@pytest.mark.smoke
@pytest.mark.requires_tools
def test_my_plugin_benchmark(tmp_path):
    result = run_benchmark(
        plugin_id="my_analysis",
        dataset_path=Path("data/benchmarks/my_analysis"),
        outdir=tmp_path / "results",
    )
    assert result.total > 0
    assert result.passed >= result.total * 0.7  # development threshold
```

See `docs/en/testing.md` for the complete testing guide.

## Resource Management

ABI provides a resource discovery and auto-install system for bioinformatics databases.
Plugin authors declare resource requirements; ABI handles checking, downloading, and
post-install hooks.

### Declaring resources

Resources are declared in `plugins/<name>/abi-plugin.yaml`:

```yaml
resources:
  my_database:
    name: "My Database"
    description: "Reference database for MyTool"
    url: "https://example.com/my_database.tar.gz"
    size_gb: 2.5
    required_by: [my_tool]
    install_post: "makeblastdb -in {resource_dir}/sequences.fasta -dbtype nucl"
    env_name: my_env
```

### ResourceSpec fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Human-readable name |
| `description` | `str` | What the resource provides |
| `url` | `str` | Download URL (supports http/https/S3) |
| `size_gb` | `float` | Approximate download size |
| `required_by` | `list[str]` | Tool IDs that depend on this resource |
| `install_post` | `str` or `None` | Shell command to run after download (e.g., `makeblastdb`) |
| `env_name` | `str` | Conda environment that provides the post-install tool |

### CLI commands

```bash
# Check which resources are available/missing
abi check-resources --type my_analysis

# Download and install missing resources (requires confirmation)
abi setup-resources --type my_analysis --confirm
```

### Environment resolution

Tool → environment assignments live in `environments.yaml`, not in individual tool
contracts. When registering a tool, add its env assignment to `environments.yaml`:

```yaml
tool_assignments:
  my_analysis:
    my_tool: my_env
```

The `ToolRegistry` injects the correct `env_name` at runtime. Run
`scripts/emit_env_yamls.py` to regenerate per-environment `envs/*.yml` files.

## Assertion Expression Reference

Step contracts support assertions written in a simple expression language.
Assertions are evaluated after tool execution against resolved outputs.

### Variables

| Variable | Type | Example |
|----------|------|---------|
| `output_json.<key>` | Any | `output_json.summary.after_filtering.total_reads` |
| `output_files.<name>` | Path | `output_files.clean_read1` |
| `output_dir` | Path | `output_dir` |
| `return_code` | int | `return_code` |

### Operators

| Operator | Example | Meaning |
|----------|---------|---------|
| `>` | `output_json.total > 0` | Greater than |
| `>=` | `output_json.qual >= 30` | Greater than or equal |
| `<` | `output_json.errors < 10` | Less than |
| `<=` | `return_code <= 0` | Less than or equal |
| `==` | `output_json.status == "complete"` | Equal |
| `!=` | `return_code != 1` | Not equal |
| `exists` | `output_files.clean_read1 exists` | File/directory exists |
| `contains` | `output_json.log contains "done"` | String contains |

### Writing assertions in pipeline_dag.yaml

```yaml
nodes:
  qc_fastp:
    tool_id: fastp
    # ...
    assertions:
      - "output_json.summary.after_filtering.total_reads > 0"
      - "output_json.summary.after_filtering.q30_rate >= 0.8"
      - "output_files.clean_read1 exists"
      - "output_files.clean_read2 exists"
      - "return_code == 0"
```

### Assertion evaluation

Assertions are evaluated after output validation. If any assertion fails, the
step is marked as failed and a `ContractViolationError` is raised with the
failed assertion details. All assertions must pass for the step to succeed.

## Execution Safety

Plugins should make `plan` and `dry_run` safe for agents. Real external tool
execution must only happen through `run` after explicit confirmation.
