# ABI — Agent-Bioinformatics Interface

ABI is a Python interface layer for agent-driven bioinformatics workflows. It
standardizes analysis plugins behind a common
`plan -> dry-run -> run -> inspect -> report` lifecycle, with provenance,
standard TSV tables, OpenAI-compatible tool descriptors, optional MCP transport,
Nextflow export/runtime support, and a queue-backed HTTP Job Service.

[![PyPI](https://img.shields.io/pypi/v/autoplasm-abi?style=flat-square&color=blue)](https://pypi.org/project/autoplasm-abi/)
[![Python](https://img.shields.io/pypi/pyversions/autoplasm-abi?style=flat-square)](https://pypi.org/project/autoplasm-abi/)
[![License](https://img.shields.io/pypi/l/autoplasm-abi?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)

## Installation

```bash
pip install autoplasm-abi

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

# Initialize a plugin workspace
abi init --type metatranscriptomics --outdir ./workspace

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
abi export-openai-tools --type metatranscriptomics --format responses
abi export-agent-context --type metatranscriptomics --format json
abi doctor-agent --type metatranscriptomics
```

All agent-facing commands support `--output-json`.

## Built-In Analysis Types

| Type | Implementation | Notes |
| --- | --- | --- |
| `metatranscriptomics` | Native ABI demo plugin | fastp -> STAR/HISAT2 -> featureCounts portability demo. |
| `metagenomic_plasmid` | Internal `abi.autoplasm` pipeline | Migrated from the former AutoPlasm development tree and bundled inside `autoplasm-abi`. |

The package also exposes an `autoplasm` command for the bundled plasmid
pipeline:

```bash
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```

There is no top-level Python package named `autoplasm`; import the internal
implementation as `abi.autoplasm`.

## Agent Transports

`ABIAgentInterface` is the stable transport-neutral boundary used by:

- CLI JSON through `--output-json`
- OpenAI-compatible descriptors from `abi export-openai-tools`
- Optional MCP stdio server via `python -m abi.mcp.server`
- HTTP Job Service via `abi job-service` and `abi job submit/list/status/artifacts/cancel`

Execution tools require explicit confirmation. `abi run`, `abi_run`, and Job
Service execution submissions return `confirmation_required` unless
`confirm_execution=true` or `--confirm-execution` is provided.

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
| `abi.schemas` | `ABISample`, `ABISampleContext`, `ABIPlanStep`, `ABIExecutionPlan` |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.testing` | `assert_plugin_contract` |

Register third-party plugins with:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## License

MIT, see [LICENSE](LICENSE).
