# <img src="figures/abi_logo.png" alt="ABI" width="36" height="36" align="top"> ABI — Agent-Bioinformatics Interface

Run reproducible bioinformatics workflows from the command line or an AI agent, without asking the agent to invent the pipeline.

ABI gives every supported analysis the same safe lifecycle: inspect the workflow, check inputs and resources, dry-run it, execute with explicit confirmation, then inspect standardized results and provenance.

[![PyPI](https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=blue)](https://pypi.org/project/abi-agent/)
[![Python](https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square)](https://pypi.org/project/abi-agent/)
[![CI](https://img.shields.io/github/actions/workflow/status/sleepinlava/abi/ci.yml?branch=master&style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen?style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-Sphinx-blue?style=flat-square)](https://sleepinlava.github.io/abi/)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)](https://github.com/sleepinlava/abi)
[![License](https://img.shields.io/pypi/l/abi-agent?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)

> :cn: [中文版](README.zh.md)

## What ABI helps you do

- **Review before you run.** See the stages, tools, commands, inputs, outputs, and resource needs before spending compute time.
- **Use one workflow interface.** The same `plan -> check -> dry-run -> run -> inspect -> report` flow works across all built-in analysis types.
- **Keep results traceable.** Each run records resolved inputs, configuration, commands, tool versions, resources, progress, tables, and reports.
- **Let agents operate safely.** Agents call typed ABI tools instead of generating ad hoc shell pipelines, and execution remains confirmation-gated.
- **Move between runtimes.** Start locally, then use Docker, Nextflow, HPC, cloud workers, or the HTTP Job Service without changing the workflow contract.

ABI is an orchestration and interface layer. It does not replace the underlying bioinformatics tools, reference databases, or compute resources required by an analysis.

## Who ABI is for

- **Researchers and bioinformaticians** who want a predictable way to preview, run, inspect, and reproduce an analysis.
- **Teams using AI agents** that need machine-readable tools, clear permissions, and structured diagnostics.
- **Platform engineers** exposing workflows through CLI, MCP, HTTP, Nextflow, HPC, or cloud infrastructure.
- **Plugin authors** who want to add a workflow while reusing ABI's planning, provenance, validation, tables, and reporting core.

## Choose an analysis workflow

| If you want to... | Use `--type` | Main result |
| --- | --- | --- |
| Profile a 16S microbial community | `amplicon_16s` | ASVs, taxonomy, phylogeny, alpha and beta diversity |
| Compare bulk RNA-seq expression | `rnaseq_expression` | Count matrix, differential expression, pathway enrichment |
| Analyze a bacterial isolate genome | `wgs_bacteria` | Assembly, annotation, MLST, antimicrobial resistance calls |
| Quantify metatranscriptomic expression | `metatranscriptomics` | Read QC, alignment summary, per-gene counts |
| Profile shotgun metagenomic reads | `easymetagenome` | Taxonomic and functional abundance profiles |
| Identify and characterize viruses | `viral_viwrap` | Viral bins, quality, taxonomy, hosts, normalized abundance |
| Reconstruct and characterize plasmids | `metagenomic_plasmid` | Detection consensus, typing, hosts, annotation, abundance, community analysis |

All seven workflows have software-path validation. Biological acceptance depends on your data, parameters, databases, and tool versions; validate representative datasets before production use.

Use ABI itself to explore a workflow without reading its implementation:

```bash
abi list-types
abi query --type metagenomic_plasmid --what stages
abi query --type metagenomic_plasmid --what tools
abi query --type metagenomic_plasmid --step qc_fastp --what inputs
```

## Get started in five minutes

### 1. Install ABI

ABI supports Python 3.10-3.13.

```bash
pip install abi-agent
abi --version

# Optional integrations
pip install "abi-agent[mcp]"       # MCP server
pip install "abi-agent[report]"    # Scientific figures and richer reports
```

To run the bundled example and work with the source repository:

```bash
git clone https://github.com/sleepinlava/abi.git
cd abi
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

### 2. Build a plan without running tools

This example resolves a three-step metatranscriptomics workflow and writes the exact plan to `results/quickstart-plan/execution_plan.json`.

```bash
abi plan \
  --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/quickstart-plan
```

### 3. Create a dry-run result

A dry-run does not execute STAR, HISAT2, featureCounts, or other analysis tools. It creates the provenance bundle, standard table skeletons, and report preview you can inspect first.

```bash
abi dry-run \
  --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/quickstart-dry-run
```

The result directory has a consistent shape:

```text
results/quickstart-dry-run/
├── execution_plan.json
├── provenance/          # resolved inputs, config, commands, resources, versions
├── tables/              # workflow-specific standard TSV tables
└── report/              # Markdown and HTML report previews
```

### 4. Check the real runtime

Before a real run, point the configuration at your data and references, then check files, executables, and resources without changing them.

```bash
abi check \
  --type metatranscriptomics \
  --config path/to/config.yaml \
  --sample-sheet path/to/samples.tsv

abi check-resources \
  --type metatranscriptomics \
  --config path/to/config.yaml
```

Some plugins can prepare managed resources. Preview the setup first, then confirm it explicitly if the paths and downloads are correct.

```bash
abi setup-resources --type metagenomic_plasmid --dry-run
abi setup-resources --type metagenomic_plasmid --confirm
```

### 5. Run only after review

`abi run` will not execute without `--confirm-execution`. This gives both people and agents a clear approval boundary.

```bash
abi run \
  --type metatranscriptomics \
  --config path/to/config.yaml \
  --sample-sheet path/to/samples.tsv \
  --outdir results/my-run \
  --confirm-execution

abi inspect --result-dir results/my-run
abi report --result-dir results/my-run --type metatranscriptomics
```

All agent-facing commands support `--output-json` for structured automation.

## How the lifecycle protects your run

| Command | What you get | Does it execute analysis tools? |
| --- | --- | --- |
| `abi query` | Fast workflow metadata from the DAG and tool registry | No |
| `abi plan` | Resolved steps, commands, inputs, outputs, and dependencies | No |
| `abi check` | Input, resource, executable, and runtime diagnostics | No |
| `abi dry-run` | Plan, provenance bundle, table skeletons, report preview | No |
| `abi run` | Executed workflow and recorded artifacts | Yes, after confirmation |
| `abi inspect` | Validation and summary of an existing result directory | No |
| `abi report` | Rebuilt Markdown and HTML reports | No analysis execution |

## Run where you work

### Local and Conda environments

ABI maps registered tools to 18 Conda environments through `environments.yaml`. By default, repository-local environments are resolved from `.mamba/envs/<env_name>/bin`.

Set `ABI_MAMBA_ROOT` to use another root. `AUTOPLASM_MAMBA_ROOT` remains available for backward compatibility.

### Docker

Dockerfiles are provided for amplicon, RNA-seq, bacterial WGS, metatranscriptomics, and plasmid analysis. EasyMetagenome and ViWrap currently use managed local environments.

```bash
docker build -f docker/Dockerfile.amplicon -t abi-amplicon .

docker run --rm -v "$PWD:/data" abi-amplicon \
  abi plan --type amplicon_16s --outdir /data/results

docker compose -f docker/docker-compose.yml up -d
```

Approximate image sizes are 1.5 GB for amplicon, 2-2.5 GB for RNA-seq/WGS/metatranscriptomics, and 15 GB for plasmid analysis.

### Nextflow, HPC, cloud, and queued jobs

Export a workflow to Nextflow, target an HPC executor, or submit work through the queue-backed Job Service when a local foreground process is not enough.

```bash
abi export-nextflow --type metatranscriptomics --output workflow.nf

abi job-service --host 127.0.0.1 --port 18791 --workers 2 --subprocess-workers
abi job submit --command run --analysis-type metatranscriptomics --confirm-execution
abi job status <JOB_ID>
abi job artifacts <JOB_ID>
abi job cancel <JOB_ID>
```

Subprocess workers support force-cancel with a SIGTERM-to-SIGKILL grace period. See the [Job Service guide](docs/en/job_service.md) and [HPC guide](docs/en/hpc_development.md).

## Use ABI with an AI agent

ABI exposes the same core operations through JSON CLI responses, provider-specific tool descriptors, MCP, a headless dispatcher, and HTTP jobs.

```bash
# Install a repository-scoped integration and diagnose it
abi agent install codex --scope project
abi agent doctor codex --scope project

# Start the safe MCP stdio profile
abi-mcp

# Export descriptors for your model provider
abi export-tools --type metatranscriptomics --format openai --provider openai
abi export-tools --type metatranscriptomics --format anthropic
abi export-tools --type metatranscriptomics --format gemini

# Invoke an ABI command from a worker process
abi dispatch --command list-types --arguments '{}'
```

The default MCP `safe` profile omits execution and management tools. `abi-mcp --profile full` adds confirmation-gated execution. Ready-to-load Claude Code, OpenCode, and Codex assets live under `integrations/`.

For system prompts or programmatic discovery:

```python
import abi

print(abi.get_agent_guide())
print(abi.list_plugins_summary())
```

See the [Agent usage guide](docs/en/agent_usage.md) for provider setup and permission details.

## Turn results into scientific figures

`abi-sciplot` validates a declarative figure specification and renders publication-ready PDF, SVG, PNG, or TIFF output. It supports 15 plot types, three themes, linting, and SHA-256 provenance.

```bash
abi-sciplot validate --spec figure.yaml
abi-sciplot render --spec figure.yaml
abi-sciplot lint --spec figure.yaml
abi-sciplot list-plot-types
```

See the [SciPlot design and usage guide](docs/en/abi_sciplot_design.md).

## Reproduce a production runtime

An ordinary runtime lock is an audit snapshot. A strict lock verifies Conda packages, declared tools, databases, host runtime, ABI version, Git commit, and release-scope readiness.

```bash
abi lock-runtime \
  --output-dir locks/candidate \
  --prefix abi-production \
  --mamba-root /path/to/mamba \
  --resource-root /path/to/resources \
  --db-profile full \
  --strict
```

Strict mode fails closed when the release environment is incomplete or the code identity is not clean. Use `--require-all-tools` only when every optional registered capability must be certified.

See [release-ready runtime locks](docs/en/runtime_locks.md) for the resource layout, immutable lock policy, and managed cloud procedure.

## Project status and expectations

ABI is currently alpha software. Its core contracts, built-in planning paths, dry-runs, packaging, and adapters are tested, but production readiness still depends on the underlying tools and your validation data.

Before production use, pin the ABI version, capture a strict runtime lock, verify tool and database versions, and define biological acceptance criteria for representative samples.

The plasmid workflow has passed assembly-mode RefSeq validation for a three-plasmid dataset. Other claims and workflow-specific validation evidence are tracked in the [workflow validation guide](docs/en/workflow_validation.md).

## Extend ABI or contribute

Transport-neutral behavior belongs in `src/abi/`; CLI, MCP, HTTP, and provider integrations stay thin. Built-in workflows combine Python adapters in `src/abi/plugins/` with declarative definitions in `plugins/<analysis_type>/`.

Register a third-party plugin with the `abi.plugins` entry-point group:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

Validate a plugin's declarative DAG and contracts before sharing it:

```bash
abi contract-lint --type my_analysis
abi contract-lint --type my_analysis --strict
```

For local development:

```bash
pip install -e ".[dev]"

ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short
python -m build
```

Start with the [development guide](docs/en/development.md), [plugin development guide](docs/en/plugin_development_guide.md), and [API reference](docs/en/api.rst).

## Documentation

- [Components and architecture](docs/en/components_and_architecture.md)
- [Using ABI: lifecycle and examples](docs/en/usage_guide.md)
- [Development standards](docs/en/development_workflow.md)
- [ABI specification](docs/en/abi_spec_v0.1.md)
- [Agent usage](docs/en/agent_usage.md)
- [Plugin development](docs/en/plugin_development_guide.md)
- [Workflow validation](docs/en/workflow_validation.md)
- [Runtime locks](docs/en/runtime_locks.md)
- [Job Service](docs/en/job_service.md)
- [HPC development](docs/en/hpc_development.md)
- [RNA-seq workflow](docs/en/rnaseq_expression_workflow.md)
- [Metagenomic plasmid workflow](docs/en/metagenomic_plasmid.md)
- [Release guide](docs/en/release.md)
- [Full hosted documentation](https://sleepinlava.github.io/abi/)

## License

ABI is available under the MIT License. See [LICENSE](LICENSE).
