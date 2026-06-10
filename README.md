# ABI — Agent-Bioinformatics Interface

A plugin-based Python abstraction layer that lets AI agents drive bioinformatics analyses through a unified plan → dry-run → execute → inspect → report workflow.

## Quick Start

```bash
pip install -e .

# List available analysis types
abi list-types

# Initialize a workspace
abi init --type metatranscriptomics --outdir ./workspace

# Build an execution plan
abi plan --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Dry-run (full provenance, no tool execution)
abi dry-run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Execute
abi run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv
```

## Architecture

```
CLI (Typer)
  └→ Plugin Registry (entry_points + builtins)
       └→ Plugin Interface (load_config → build_plan → registry → parse_outputs → write_report)
            └→ Runtime Backend (Local / Nextflow)
                 └→ GenericABIExecutor
                      ├→ Standard Tables (TSV)
                      ├→ Provenance (JSON/JSONL)
                      └→ Reports (Markdown/HTML)
```

## Plugin Development

Implement the 6 core methods:

```python
class MyPlugin:
    plugin_id = "my_analysis"
    display_name = "My Analysis"
    description = "..."

    def load_config(self, config_path, *, profile, overrides) -> dict
    def build_plan(self, config, *, check_files) -> ABIExecutionPlan
    def registry(self) -> ToolRegistry
    def table_schemas(self) -> dict[str, list[str]]
    def parse_outputs(self, tool_id, output_dir, sample_id) -> dict
    def write_report(self, plan, result_dir) -> dict
```

Register via `pyproject.toml`:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## Agent Integration

All CLI commands support `--output-json` for structured output. Export OpenAI-compatible tool descriptors:

```bash
abi export-openai-tools --type metatranscriptomics --format responses
```

## License

MIT
