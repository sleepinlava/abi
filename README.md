# ABI — Agent-Bioinformatics Interface

A plugin-based Python abstraction layer that lets AI agents drive
bioinformatics analyses through a unified
**plan → dry-run → execute → inspect → report** workflow.

[![PyPI](https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=blue)](https://pypi.org/project/abi-agent/)
[![Python](https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square)](https://pypi.org/project/abi-agent/)
[![License](https://img.shields.io/pypi/l/abi-agent?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)
[![GitHub](https://img.shields.io/badge/github-sleepinlava%2Fabi-lightgrey?style=flat-square&logo=github)](https://github.com/sleepinlava/abi)

## Installation

```bash
# From PyPI (core install — metatranscriptomics plugin)
pip install abi-agent

# Include the optional metagenomic_plasmid adapter
pip install "abi-agent[autoplasm]"

# Development install (core + all dev tooling)
pip install "abi-agent[autoplasm,dev]"
```

**Python**: 3.10 – 3.13

## Quick Start

```bash
# List installed analysis types
abi list-types

# Initialize a workspace from a plugin template
abi init --type metatranscriptomics --outdir ./workspace

# Build an execution plan
abi plan --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Dry-run — full provenance artifacts, no real tool execution
abi dry-run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Execute through a runtime backend
abi run --type metatranscriptomics --config config.yaml --sample-sheet samples.tsv

# Inspect results
abi inspect --result-dir results/

# Regenerate reports
abi report --result-dir results/ --type metatranscriptomics

# Export to Nextflow DSL2
abi export-nextflow --type metatranscriptomics --output workflow.nf

# Export OpenAI-compatible tool descriptors
abi export-openai-tools --type metatranscriptomics --format responses
```

All commands support `--output-json` for structured agent consumption.

## Optional Dependencies

| Extra        | Plugin                | Package    | Install                                |
|-------------|-----------------------|------------|----------------------------------------|
| `autoplasm` | `metagenomic_plasmid` | autoplasm  | `pip install abi-agent[autoplasm]`     |
| `dev`       | (development tooling) | pytest, ruff, mypy, types-PyYAML | `pip install abi-agent[dev]` |

The `metagenomic_plasmid` plugin uses **lazy imports** — the external package is
imported inside each method, not at the module top level. The plugin module
loads without its dependency; a clear `ImportError` is raised only when you
actually try to use it.

## Architecture

```
CLI (Typer)  ────  ABIAgentInterface  ────  OpenAI Tool Export
 │                    │
 └── Plugin Registry (entry_points + builtins)
       │
       └── Plugin Protocol ───────────────────────────────────────┐
            ├── ABIPlugin           (6 core methods)              │
            ├── ABIDryRunPlugin     (+ execute_dry_run)           │
            └── ABIInitializablePlugin  (+ root path for init)    │
                     │                                            │
                     └── Runtime Backend (Local / Nextflow)       │
                              │                                   │
                              └── GenericABIExecutor              │
                                   ├── Standard Tables (TSV)      │
                                   ├── Provenance (JSON / JSONL)  │
                                   └── Reports (Markdown / HTML)  │
                                                                    │
Public SDK for plugin authors:  abi.tools  abi.errors  abi.testing ◄┘
```

## Plugin Development

A plugin is any object that satisfies the `ABIPlugin` protocol. It must expose
four string attributes and six methods:

```python
from abi.interfaces import ABIPlugin
from abi.schemas import ABIExecutionPlan
from abi.tools import ToolRegistry


class MyPlugin:
    # ── attributes ──────────────────────────────────────────────
    plugin_id: str
    display_name: str
    description: str
    report_title: str

    # ── 6 core methods ──────────────────────────────────────────
    def load_config(self, config_path, *, profile, overrides) -> dict: ...
    def build_plan(self, config, *, check_files) -> ABIExecutionPlan: ...
    def registry(self) -> ToolRegistry: ...
    def table_schemas(self) -> dict[str, list[str]]: ...
    def parse_outputs(self, tool_id, output_dir, sample_id) -> dict: ...
    def write_report(self, plan, result_dir) -> dict: ...
```

### Extended Protocols

**`ABIDryRunPlugin`** — add `execute_dry_run` to use a plugin-specific
dry-run pipeline instead of the generic executor:

```python
from abi.interfaces import ABIDryRunPlugin

class MyPlugin(ABIDryRunPlugin):
    def execute_dry_run(self, plan, config) -> dict[str, Path]: ...
```

**`ABIInitializablePlugin`** — expose a `root` path so `abi init` can copy
template files (config, sample sheet) into a workspace:

```python
from abi.interfaces import ABIInitializablePlugin

class MyPlugin(ABIInitializablePlugin):
    root: Path  # directory containing config_default.yaml and sample_sheet_template.tsv
```

### Registration

Register via `pyproject.toml` entry points:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

### Testing

Validate a plugin's contract with the SDK testing helper:

```python
from abi.plugins import get_plugin
from abi.testing import assert_plugin_contract


def test_my_plugin_contract():
    assert_plugin_contract(get_plugin("my_analysis"))
```

## SDK Reference

Public modules available to plugin authors:

| Module             | Contents                                              |
|-------------------|-------------------------------------------------------|
| `abi.tools`       | `ToolRegistry`, `ToolSkill`, `RunResult`             |
| `abi.errors`      | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.testing`     | `assert_plugin_contract`                              |
| `abi.schemas`     | `ABISample`, `ABISampleContext`, `ABIPlanStep`, `ABIExecutionPlan` |
| `abi.interfaces`  | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` |

## Development

```bash
# Editable install with dev tooling
pip install -e ".[dev]"

# Lint, type-check, and test
ruff check src/ && ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v

# Build distribution
pip install build twine
python -m build
python -m twine check dist/*
```

The test suite does **not** require `autoplasm` — CI installs only `.[dev]`.

## Publishing to PyPI

The package is configured for PyPI publication as `abi-agent`. Built-in plugin
templates under `plugins/` are included in both source distributions and wheels
so `abi init` works after installation from PyPI.

Preferred release path:

1. Ensure `pyproject.toml` has the intended version.
2. Create and publish a GitHub Release for that version.
3. The `Publish to PyPI` workflow builds the source distribution and wheel,
   validates them with `twine check`, and publishes via PyPI Trusted Publishing.

Manual release path, if you have a PyPI API token:

```bash
rm -rf dist/
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

Set `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<pypi-api-token>` for manual
uploads.

### Path Conflict with PlasimSkillsForAgent

If you also have the `autoplasm` package installed from the
PlasimSkillsForAgent monorepo, its `abi` package can shadow the standalone
`abi-agent` package on `sys.path`.  Run the dev-setup tool once to fix this:

```bash
abi-dev-setup                          # install priority .pth file
abi-dev-setup --check                  # verify the fix is active
abi-dev-setup --undo                   # remove the fix
```

When the wrong package is loaded at runtime, a warning is emitted with
instructions.  The CI pipeline is unaffected (clean environment).

## License

MIT — see [LICENSE](LICENSE).
