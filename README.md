# ABI — Agent-Bioinformatics Interface

A plugin-based Python abstraction layer that lets AI agents drive bioinformatics analyses through a unified plan → dry-run → execute → inspect → report workflow.

## Quick Start

```bash
# Core install (metatranscriptomics plugin only)
pip install -e .

# Or include optional plugins:
pip install -e ".[autoplasm]"       # metagenomic_plasmid plugin
pip install -e ".[autoplasm,dev]"   # both plugins + dev tooling

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

## Optional Dependencies

Some plugins require packages outside the core dependency tree:

| Extra        | Plugin                  | Package    | Install                              |
|-------------|-------------------------|------------|--------------------------------------|
| `autoplasm` | `metagenomic_plasmid`   | autoplasm  | `pip install abi-agent[autoplasm]`   |
| `dev`       | (development tooling)   | pytest, ruff, mypy | `pip install abi-agent[dev]` |

Plugins with optional dependencies use **lazy imports** — the external
package is imported inside each method, not at the top of the module.
This means:

- The plugin module can be imported without its dependencies installed.
- A clear `ImportError` is raised only when you actually try to **use**
  the plugin, with an install hint.
- CI and test suites don't need to install every optional dependency.

### Installing all plugins + dev tooling

```bash
pip install -e ".[autoplasm,dev]"
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
from abi.schemas import ABIExecutionPlan
from abi.tools import ToolRegistry


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

Validate a plugin with the SDK testing helper:

```python
from abi.plugins import get_plugin
from abi.testing import assert_plugin_contract


def test_my_plugin_contract():
    assert_plugin_contract(get_plugin("my_analysis"))
```

## Agent Integration

All CLI commands support `--output-json` for structured output. Export OpenAI-compatible tool descriptors:

```bash
abi export-openai-tools --type metatranscriptomics --format responses
```

## Development

Use an editable install so imports resolve to this checkout:

```bash
pip install -e ".[dev]"
pytest -q
```

The test suite does **not** require `autoplasm` — the metagenomic_plasmid
plugin uses lazy imports so its module can be loaded without the optional
dependency.  CI installs only `.[dev]` for speed.

If you need to test the metagenomic_plasmid plugin locally:

```bash
pip install -e ".[autoplasm,dev]"
```

## License

MIT
