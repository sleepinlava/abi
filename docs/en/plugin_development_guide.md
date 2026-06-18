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
- `execution.env_name`
- `execution.executable`
- `execution.command_template`
- declared input/output template fields
- normalized standard table names

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

## Execution Safety

Plugins should make `plan` and `dry_run` safe for agents. Real external tool
execution must only happen through `run` after explicit confirmation.
