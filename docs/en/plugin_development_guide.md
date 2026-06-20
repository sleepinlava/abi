# Plugin Development Guide

ABI plugins expose biological analysis types behind the shared lifecycle API.

## Minimum Python Interface

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

## Tool Contracts

Contracts are machine-readable and must match the runtime registry:

- `tool_id`
- `category`
- `execution.executable`
- `execution.command_template`
- declared input/output template fields
- normalized standard table names

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
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` protocols |
| `abi._shared` | `_read_tsv`, `_display_command`, `_plan_dict`, `_common_overrides` |
| `abi.dag_planner` | `UniversalDAG`, `build_plan_from_dag`, `PathTemplateContext` — DAG-driven `build_plan()` (added 2026-06-18) |
| `abi.tsv_mapping` | `TSVMapper`, `generate_rows` — declarative TSV column mapping (added 2026-06-18) |
| `abi.sciplot` | `FigureSpec`, `render_figure`, `validate_spec`, `lint_figure` — publication-grade figure compiler. 15 plot types (PCoA, volcano, stacked bar, heatmap, phylogeny), plotnine+seaborn backends. (v1.4.0, added 2026-06-20) |
| `abi.contracts` | `WorkflowSpec`, `WorkflowStepSpec`, `load_workflow_spec`, `run_contract_lint` — L1/L2/L3 workflow declaration + validation |
| `abi.report` | `write_plugin_report`, `render_figures_via_sciplot` — report generation + figure rendering |

## DAG-Driven Plan Construction (recommended for new plugins)

Instead of writing a hand-coded `build_plan()` that iterates samples and
constructs `PlanStep` objects (~200 lines of boilerplate), new plugins should
declare their workflow in a `pipeline_dag.yaml` file and use the universal
DAG planner:

```python
# In your plugin's build_plan():
def build_plan(self, config, *, check_files=True):
    context = self.build_sample_context(config, check_files=check_files)
    if config.get("use_dag", True):
        from abi.dag_planner import build_plan_from_dag
        return build_plan_from_dag(
            self.root / "pipeline_dag.yaml", config, context
        )
    # ... old hand-written code (deprecated)
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

## Execution Safety

Plugins should make `plan` and `dry_run` safe for agents. Real external tool
execution must only happen through `run` after explicit confirmation.
