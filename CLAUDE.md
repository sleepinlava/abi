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
abi query --type metagenomic_plasmid --what stages
abi dry-run --type metatranscriptomics --outdir /tmp/abi-smoke
autoplasm --help

# Documentation build
bash docs/build_docs.sh

# Docker build
docker build -f docker/Dockerfile.amplicon -t abi-amplicon .
docker compose -f docker/docker-compose.yml build

# Agent integration
abi-mcp                          # start MCP stdio server for Claude Desktop / Claude Code
abi install-skills               # install ABI skills into ~/.claude/skills/abi/
abi query --type metagenomic_plasmid --what stages  # lightweight metadata query (~50ms)
abi query --type metagenomic_plasmid --step qc_fastp --what inputs  # step-level I/O
abi doctor-agent --type metagenomic_plasmid   # print per-plugin operating guide
abi export-openai-tools --type metagenomic_plasmid --format responses  # OpenAI function descriptors
abi export-tools --type metagenomic_plasmid --format openai --provider deepseek  # DeepSeek/Zhipu/Kimi/Qwen
abi export-tools --type metagenomic_plasmid --format anthropic  # Anthropic Claude tool_use
abi export-tools --type metagenomic_plasmid --format gemini     # Google Gemini function_declarations
abi contract-lint --type metagenomic_plasmid [--strict]  # Static DAG/contract validation
abi check-resources --type metagenomic_plasmid           # Check resource/database availability
abi setup-resources --type metagenomic_plasmid --confirm  # Resource setup (confirmation required)

# Figure compiler
abi-sciplot validate --spec figure.yaml   # Validate a FigureSpec
abi-sciplot render --spec figure.yaml     # Render a figure (PDF+SVG+PNG+TIFF)
abi-sciplot lint --spec figure.yaml       # Lint a rendered figure
abi-sciplot list-plot-types               # List supported figure types

# Job Service (default localhost, requires ABI_JOB_SECRET for remote binding)
abi job-service --host 127.0.0.1 --port 18791 --workers 2
```

## Architecture

ABI is a **Python library + CLI + Agent tool layer** for AI-driven bioinformatics. It is NOT a workflow engine — it is a **control plane** that sits between AI agents and bioinformatics tools.

```
Agent Platforms (Claude / ChatGPT / Cursor)
        │
Transport Layer   CLI JSON  │  OpenAI Tools  │  Anthropic Tools  │  Gemini Tools  │  MCP  │  HTTP Job API  │  Query
        │
ABIAgentInterface   plan / dry_run / run / inspect / report / dispatch / query
        │
ABI Core            schemas  │  provenance  │  permissions  │  diagnostics
                    tables   │  tools       │  executor     │  report
                    contracts│  dag         │  figures      │  dag_planner
                    tsv_mapping  │  sciplot  │  resources   │  workflow
                    tool_descriptors  │  internal  │  results
        │
Runtimes            local  │  Docker  │  Nextflow  │  HPC (SLURM/PBS)  │  cloud  │  Job Service
        │
Plugins             metagenomic_plasmid/  rnaseq_expression/  wgs_bacteria/
                    amplicon_16s/  metatranscriptomics/
                    easymetagenome/  viral_viwrap/
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
  figures/            FigureEngine (7 renderers), FigureSpec — generic figure system
  report/             write_full_report, write_plugin_report, write_methods,
                      citations, limitations, html — generic report system
                      (write_plugin_report supports abi.sciplot via use_sciplot=True)
  workflow/           ResourceManifest, workflow validation, figure_specs loading
  plugins/
    metagenomic_plasmid/   Self-contained package (engine in _engine/, ~40 modules), 67 tools
    rnaseq_expression.py   Inline plugin (6 tools, DESeq2 R script bundled)
    wgs_bacteria.py        Inline plugin (5 tools, SPAdes/Prokka/AMR parsers)
    amplicon_16s.py        Inline plugin (8 tools, cutadapt/vsearch/diversity parsers)
    metatranscriptomics.py Inline plugin (3 tools, shared parsers from _shared)
    easymetagenome/        P0 shotgun metagenomics — 12 tools, 3 workflow presets,
                           internal handlers, manifest validation, schema-driven
    viral_viwrap/          Managed external CLI plugin — wraps ViWrap 1.3.1,
                           1 tool, custom tool skill, environment checker
  scripts/              Bundled scripts: amplicon_diversity.py, install_deseq2.R,
                        setup_rnaseq_env.sh, download_rdp_sintax.sh, etc.
  docker/               Dockerfiles + docker-compose.yml for containerized execution
  runtimes/             Execution runtime backends (1195 lines)
    base.py               ABIRuntime protocol + RuntimeOptions, RuntimeResult
    local.py              LocalRuntime — direct subprocess execution
    nextflow.py           NextflowRuntime — NF config generation, trace parsing, submit
    hpc.py                HpcRuntime — SLURM/PBS script generation, job submission, polling
  exporters/            Plan exporters: nextflow.py (NextflowExporter)
  mcp/                  MCP stdio server — auto-generates tool registrations from tool_descriptors SSOT
  autoplasm/            Backward-compatible re-export shim → metagenomic_plasmid/_engine/
  _shared.py            Shared utilities: _read_tsv, _display_command, _plan_dict,
                        _common_overrides, _clean, _resolve_path,
                        _parse_fastp, _parse_star (373 lines)
  provenance.py         RunLogger, PipelineProgressRecorder, TSV writers (900 lines)
  tools.py              ToolRegistry, ToolSkill, GenericCommandSkill, SafeFormatDict, RunResult (1858 lines)
  schemas.py            Canonical types: SampleInput, ExecutionPlan, PlanStep, SampleContext (511 lines)
  executor.py           GenericABIExecutor — step iteration, tool invocation, contract enforcement.
                        Supports sample-level parallel execution via ThreadPoolExecutor
                        (config.execution.parallel + config.execution.workers). (1551 lines)
  dag_planner.py        Universal DAG planner — generates ExecutionPlan from pipeline_dag.yaml
                        (replaces hand-written build_plan() boilerplate) (1106 lines)
  tsv_mapping.py        Declarative TSV column mapper — YAML-driven output parsing
                        with 3 source types (tsv_mapping, json_mapping, key_value_log).
                        Replaces ~14 csv.DictReader → remap columns parser functions. (446 lines)
  tool_descriptors.py   Unified LLM tool descriptor SSOT — provider-agnostic tool metadata
                        with PROVIDER_PROFILES for OpenAI-compatible, Anthropic, Gemini formats.
                        Replaces hand-duplicated tool definitions. (776 lines)
  internal.py           Transport-neutral internal DAG handler protocol —
                        ABIInternalHandler, InternalHandlerContext, InternalHandlerResult.
                        Plugins register Python functions for steps without external tools. (111 lines)
  step_runner.py        Single-step execution used by native HPC worker jobs —
                        deserializes a PlanStep dict, resolves internal/external handlers,
                        executes, and writes StepExecutionResult. (232 lines)
  results.py            Shared result/provenance writer — ABIResultWriter,
                        validate_abi_result_dir, REQUIRED_RESULT_ARTIFACTS. (411 lines)
  tables.py             StandardTableManager — YAML-driven table normalization. (209 lines)
  sciplot/              Publication-grade scientific figure compiler — FigureSpec →
                        Validate → Render → Export → Lint → Provenance.
                        Pydantic schema, 15 plot types, 3 themes, plotnine+seaborn
                        backends, SHA256 provenance. (32 files, 4516 lines)
  dag.py                DAG inference engine — L1 (literature) / L2 (path) / L3 (validation) (316 lines)
  contracts/            WorkflowSpec, step contract enforcement, checksum chaining, assertion eval
    __init__.py           WorkflowSpec, WorkflowStepSpec, load_workflow_spec, run_contract_lint (468 lines)
    step_contract.py      ContractViolation, validate_output_contract, evaluate_assertions (961 lines)
  permissions.py        read_only / planning_write / execution levels
  diagnostics.py        Error taxonomy + DiagnosticHint + classify_exception (402 lines)
  jobs/service.py       HTTP Job Service with subprocess force-kill (SIGTERM → SIGKILL) (1397 lines)
  json_utils.py         JSON file/payload loading with ABIJSONError wrapping
  timeouts.py           Timeout parsing: parse_timeout_seconds, timeout_from_env_or_value
  resources.py           Resource discovery + auto-install: check_resources, setup_resources,
                        ResourceSpec with install_post hooks (e.g. makeblastdb) (484 lines)
  cli.py                Typer CLI: abi + autoplasm entry points (2163 lines)
  skills/               Agent skill files (abi_agent + per-tool), installed via ``abi install-skills``

environments.yaml      Single source of truth: 25 conda envs + 100+ tool→env assignments
                       (2026-06: fixed stats env mapping; mmseqs2 ResourceSpec added;
                       amrfinderplus install_post: makeblastdb; kraken2 aria2c S3 download)
scripts/emit_env_yamls.py  Generates per-environment ``envs/*.yml`` from environments.yaml
```

### Key modules for plugin authors (Public SDK)

| Module | What it provides |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` protocols |
| `abi.schemas` | `SampleInput`, `SampleContext`, `PlanStep`, `ExecutionPlan` |
| `abi.tools` | `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` |
| `abi.provenance` | `RunLogger`, `PipelineProgressRecorder`, TSV provenance writers |
| `abi.contracts` | `WorkflowSpec`, `WorkflowStepSpec`, `load_workflow_spec` — literature-backed workflow declarations |
| `abi.contracts.step_contract` | `ContractViolationError`, `validate_output_contract`, `evaluate_assertions`, checksum chaining |
| `abi.dag` | `infer_dag`, `ABIDAG`, `StepBinding` — DAG inference with L1/L2/L3 |
| `abi.dag_planner` | `UniversalDAG`, `build_plan_from_dag`, `PathTemplateContext` — declarative plan generation from `pipeline_dag.yaml`; replaces all hand-written `build_plan()` |
| `abi.tsv_mapping` | `TSVMapper`, `generate_rows` — YAML-driven TSV/JSON/log column mapping |
| `abi.sciplot` | `FigureSpec`, `render_figure`, `validate_spec`, `lint_figure`, `load_spec` — scientific figure compiler (PDF/SVG/PNG/TIFF, lint, provenance) |
| `abi.resources` | `check_resources`, `setup_resources`, `ResourceSpec` — resource discovery + auto-install with install_post hooks |
| `abi.internal` | `ABIInternalHandler`, `InternalHandlerContext`, `InternalHandlerResult` — transport-neutral internal DAG nodes for steps without external tools |
| `abi.results` | `ABIResultWriter`, `validate_abi_result_dir` — shared result/provenance writer |
| `abi.tables` | `StandardTableManager` — YAML-driven table normalization |
| `abi.errors` | `ABIError`, `ConfigError`, `SampleSheetError`, `ToolError` |
| `abi.config` | `resolved_mamba_root()`, `PROJECT_ROOT`, `load_yaml`, `deep_merge` — env resolution with 4-level priority (ABI_MAMBA_ROOT > AUTOPLASM_MAMBA_ROOT > .mamba > abi-envs) |
| `abi.testing` | `assert_plugin_contract` |

## Architectural invariants

### JSON envelope contract

Every `ABIAgentInterface` method returns a JSON string with exactly one of three statuses:
- `success` — `result` holds the payload
- `confirmation_required` — operation gated on user approval (only `run`)
- `error` — `error_code` + `diagnostic_hints` guide automated recovery

### Permission model (3 tiers)

- `read_only`: `list_types`, `inspect`, `validate_result`, `query` — no file writes, no tool execution
- `planning_write`: `plan`, `dry_run`, `report`, `export_nextflow` — writes plans/provenance, no tool execution
- `execution`: `run` — **requires `confirm_execution=true`**, writes provenance, executes real tools

### The seven plugins

All seven plugins have complete tool chains, parsers, report generation, tests, benchmark datasets, and Docker images. All use DAG-driven plan generation via `UniversalDAG`. **856 passed, 10 skipped, 0 ruff errors, 0 mypy errors.**

- **`metagenomic_plasmid`**: The flagship complex plugin. Engine in `_engine/` (40 modules, 9,859 lines). 67 tool contracts, 84-node DAG (`pipeline_dag.yaml`, 3,054 lines), plasmid detection/annotation/abundance pipeline. DAG-driven planner using `UniversalDAG` with platform routing, fallback chains, assertions, consensus algorithms, custom reports, dashboard. 10 conda environments. 8 sciplot figures. **Assembly platform verified**: 19/19 steps passed. **10 databases** (genomad 2.9GB, bakta 4.2GB, mob_suite 3.0GB, plasmidfinder, amrfinderplus 251MB, platon, macsyfinder, metaphlan 34GB, mmseqs2 1.6GB, kraken2 pending).
- **`easymetagenome`**: P0 shotgun metagenomics — 12 tools (fastp, kneaddata, kraken2, bracken, humann4 + 6 HUMAnN utilities, seqkit). 3 workflow presets (`p0_taxonomy`, `p1_humann4`, `full_read_based`). DAG-driven planner with 34-node DAG. Uses internal handlers + manifest validation with JSON Schema. Schema-driven report generation. 2 new conda environments (humann, kneaddata).
- **`rnaseq_expression`**: 6-tool standard RNA-seq. fastp → STAR → featureCounts → build_count_matrix → DESeq2 → clusterProfiler. Uses `build_plan_from_dag()` with TSVMapper. DESeq2 R script bundled, automated BiocManager install.
- **`wgs_bacteria`**: 5-tool bacterial isolate analysis. fastp → SPAdes → Prokka → MLST → AMRFinderPlus. Uses `build_plan_from_dag()` with TSVMapper.
- **`amplicon_16s`**: 8-tool microbial community analysis. cutadapt → vsearch_mergepairs → vsearch_derep → UNOISE3 denoise → SINTAX taxonomy → MAFFT+FastTree phylogeny → diversity (alpha/beta via bundled script).
- **`metatranscriptomics`**: 3-tool demo. fastp, STAR/HISAT2, featureCounts. All 3 parsers working via shared imports from `abi._shared`.
- **`viral_viwrap`**: Managed external CLI plugin wrapping ViWrap 1.3.1. 1 tool with custom ToolSkill (typed command builder), environment checker, artifact mapper. Identifies viruses from metagenomic assemblies — binning, taxonomy, host prediction, quality filtering.

All plugins share the same `ABIAgentInterface` contract, tool contract format, `write_plugin_report()` template, and workflow declaration pattern. Each has a `pipeline_dag.yaml` for L1/L2/L3 DAG validation.

### Runtime backends (`abi.runtimes`)

Four execution runtimes implement the `ABIRuntime` protocol (check / dry_run / run):
- **LocalRuntime**: Direct subprocess execution with conda env activation.
- **NextflowRuntime**: Generates Nextflow DSL2 config + main.nf, submits via `nextflow run`, parses trace files.
- **HpcRuntime**: Generates SLURM/PBS batch scripts with resource directives (cpus, mem, time, gpus), dependency chaining via `--dependency=afterok`, poll-until-complete.
- **Docker**: Containerized execution via docker-compose (separate Dockerfiles per plugin).

### Internal handler system (`abi.internal`)

For DAG steps that don't correspond to external tools (e.g., table joining, filtering, validation), plugins register `ABIInternalHandler` implementations — Python functions that receive `InternalHandlerContext` (outdir, provenance_dir, tables_dir, dry_run flag) and return `InternalHandlerResult` (status, message, tables, artifacts). This replaces the pattern of faking "tools" whose `build_command` returned `/bin/true`. Both `easymetagenome` and `viral_viwrap` use internal handlers.

### Tool descriptor unification (`abi.tool_descriptors`)

`tool_descriptors.py` is the **single source of truth** for LLM tool metadata. It defines:
- `ABI_AGENT_TOOLS` — canonical tool parameter definitions
- `PROVIDER_PROFILES` — provider-specific quirks (strict mode, naming)
- Three format families: OpenAI-compatible (DeepSeek, Zhipu, Kimi, Qwen, MiniMax), Anthropic Claude, Google Gemini

The MCP server (`abi/mcp/server.py`) auto-generates its tool registrations from this SSOT. `cli.py` `export-tools` command delegates to it. Never add a new agent tool without updating `tool_descriptors.py`.

### autoplasm/ is a backward-compat shim

`autoplasm/` (39 .py files) is a **re-export proxy** to `plugins/metagenomic_plasmid/_engine/`. It exists only so `autoplasm --help` and `from abi.autoplasm import ...` still work. Do not add new logic there — put it in `_engine/` or in the ABI core.

### Tool contract pipeline

The lifecycle for any tool is: `check_installation → plan → validate_inputs → select_params → build_command → run → parse_outputs → normalize_outputs`. GenericCommandSkill handles this from YAML tool_contracts; only tools with complex post-processing need Python subclasses.

Each contract may declare a `normalization` block (`parser` + `tables`) that maps tool outputs to standard tables. For simple TSV/JSON/log output parsing, use `TSVMapper` with `parsers.yaml` declarations instead of writing Python parser functions. Supports 3 source types: `tsv_mapping` (column remap), `json_mapping` (nested JSON flatten), and `key_value_log` (pipe-delimited log parsing).

### Step contract enforcement

`contracts/step_contract.py` enforces step contracts on every real tool execution:
1. **Pre-execution**: verify input file checksums against recorded values (checksum chaining)
2. **Actual-output resolution**: map abstract planner outputs to real files in `output_dir` when tools write fixed filenames
3. **Post-execution**: validate output files and directories (existence, min_size, extensions, contains, min_files, min_contigs, JSON required_keys, JSON schema)
4. **Assertions**: evaluate runtime assertions (e.g. `output_json.summary.total_reads > 0`) against resolved tool outputs

Contract violations raise `ContractViolationError` with structured diagnostics. Checksums are persisted to `provenance/checksums.json` for downstream verification.

Do not claim that a workflow is biologically validated from dry-run alone or from individual tool papers alone. Use `docs/workflow_validation.md` to assess the gap between the current constrained control layer and a fully validated, literature-backed, reproducible scientific workflow.

## Key documentation

| Document | Purpose |
| --- | --- |
| `docs/en/` | English documentation (Sphinx source, 19 files) |
| `docs/zh/` | Chinese documentation (Sphinx source, 10 files) |
| `docs/_base.py` | Shared Sphinx config for both language builds |
| `docs/build_docs.sh` | One-command bilingual docs build |
| `docs/en/abi_sciplot_design.md` | abi_sciplot figure compiler design doc — FigureSpec protocol, themes, lint, provenance |
| `docs/en/plugin_report_figure_spec.md` | Report/figure system reference for plugin authors |
| `docs/en/rnaseq_expression_workflow.md` | RNA-seq workflow reference |
| `docs/en/hpc_development.md` | HPC deployment guide (SLURM, Nextflow, databases, benchmarks) |
| `docs/en/workflow_validation.md` | Biological validation methodology |
| `docs/en/plugin_development_guide.md` | How to add a new analysis type |
| `docs/en/devlog.md` | Daily development log — engineering fixes, features, status |
| `docs/en/paper_execution_plan.md` | Paper execution stratification — Tier 1/2/3 hardware, local/cloud/HPC |

### Shared utilities (`_shared.py`)

`src/abi/_shared.py` is the single source of truth for helper functions that were previously duplicated across 2–5 modules each:

| Function | Purpose | Former locations |
|---|---|---|
| `_read_tsv` | Read TSV → list[dict] (returns [] if missing) | cli, agent, results, engine.result_validation, engine.dashboard |
| `_display_command` | Format token list → human-readable shell command | provenance, executor, engine.logger, engine.pipeline |
| `_plan_dict` | Serialize plan + inject analysis_type | cli, agent |
| `_common_overrides` | Build compact overrides dict from CLI flags | cli, agent |

All ABI core modules and `_engine/` subpackages import these from `abi._shared`. When adding a new caller, import from here rather than copying the function.

### Provenance artifacts

Every run writes to `<outdir>/provenance/`: `commands.tsv`, `resolved_inputs.tsv`, `tool_versions.tsv`, `resources.json`, `environment.yml`, `run_summary.json`, `checksums.json`, `progress.json`/`progress.jsonl`, `step_logs/`. These are always written even on failure — post-mortem inspection is always possible.

Additionally, `ABIResultWriter` (in `results.py`) writes `execution_plan.json`, `report/report.md`, and optional per-plugin artifacts (standard tables, figures). `validate_abi_result_dir()` checks that all `REQUIRED_RESULT_ARTIFACTS` exist.

### Job Service execution modes

- **In-process** (default): worker threads call `agent.dispatch()` directly. Cancel sets `cancel_requested=true` but cannot interrupt running dispatch.
- **Subprocess** (`--subprocess-workers`): each job runs via `abi dispatch` subprocess. Cancel sends SIGTERM (3s grace) then SIGKILL for true force-kill.

## Testing patterns

- Tests use mock agents (`RecordingAgent`, `SlowAgent`) that return controlled JSON envelopes.
- `tests/unit/test_job_service.py` — thread synchronization via `threading.Event` for worker state control.
- `tests/integration/test_dry_run.py` — end-to-end dry runs against real plugin configuration.
- Fixtures live in `tests/fixtures/`; curated example data in `data/examples/`.
- Current suite: **856 passed, 10 skipped, 0 ruff errors, 0 mypy errors** (2026-06-23).

## Adding a new analysis type

1. Implement `ABIPlugin` protocol in a new module or package under `plugins/`.
2. Create `abi-plugin.yaml`, `tool_registry.yaml`, `standard_tables.yaml` under `plugins/<name>/`.
3. Add tool contracts as `tool_contracts/*.yaml`.
4. Create `pipeline_dag.yaml` with `category_dirs`, `scope` (per_sample/cross_sample), and `path` templates — use `abi.dag_planner.build_plan_from_dag()` as the sole `build_plan()` implementation.
5. For simple TSV/JSON output parsers, create `parsers.yaml` and use `abi.tsv_mapping.TSVMapper` instead of writing hand-coded Python parsers.
6. For steps that don't map to external tools, register `ABIInternalHandler` implementations using the `@internal_handler` decorator from `abi.internal`.
7. Register in `pyproject.toml` under `[project.entry-points."abi.plugins"]`.
8. Verify with `assert_plugin_contract(plugin)` in tests.
