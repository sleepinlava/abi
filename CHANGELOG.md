# Changelog

## [1.5.2] - 2026-07-07

### Added

- Added a consolidated `scripts/release_check.sh` entry point for local
  release verification before tagging or publishing.
- Added a paper-evaluation task package with benchmark task definitions,
  metrics schema, bilingual evaluation notes, and manuscript outline drafts.
- Added contract lint coverage for DAG template parameters so plugin validation
  catches unresolved command, params, input, and output placeholders.

### Changed

- Aligned the documented release gate with CI by running the full test suite
  and SciPlot tests under coverage, excluding `requires_tools` tests, and
  checking module coverage from `coverage.json`.
- Updated metagenomic plasmid DAG-driven tests to assert the current declarative
  step and output contracts instead of old handwritten planner paths.

### Fixed

- Fixed declarative DAG input resolution for `source: config.*` references,
  including tool database resources and cross-sample report inputs.
- Fixed metagenomic plasmid FASTA export and reports to read assembly paths
  from DAG-resolved step inputs/outputs after the planner refactor.
- Fixed GitHub Actions release identity by adding this `1.5.2` changelog
  section and moved the opencode API key reference to a GitHub Actions secret.

## [1.5.1] - 2026-06-23

### Changed

- Made package metadata the single runtime version source and added strict
  tag/wheel/runtime/CHANGELOG release identity checks.
- Removed the legacy handwritten plasmid planner; all 7 built-in workflows now
  use declarative `pipeline_dag.yaml` planning.
- Replaced core imports of concrete plugin implementations with optional
  resource and result-validation capability protocols.
- Raised the branch-aware global coverage gate to 75% and added risk-based
  module line/branch gates for DAG, executor, resources, local/HPC runtimes,
  internal handlers, and step execution.

### Fixed

- Corrected wheel-installed plasmid configuration discovery outside the source
  checkout, PBS scheduler job-ID validation, resource selection filtering, and
  dry-run resource setup side effects.
- Made release and PyPI publication consume the exact wheel that passed the
  complete quality gate.

## [1.5.0] - 2026-06-23

### Added

- HPC runtime overhaul with SLURM/PBS execution support and transport-neutral
  internal DAG handlers.
- `easymetagenome` and `viral_viwrap` analysis plugins.
- Expanded SciPlot biological renderers, workflow validation, performance gates,
  security regression tests, and golden traces for all built-in workflow families.

### Changed

- Unified tool-to-environment declarations in `environments.yaml` and expanded
  multi-platform ONT, PacBio HiFi, hybrid, and assembly-only planning.
- Hardened executor contracts, resource setup, diagnostics, permission enforcement,
  result validation, and CI packaging checks.

### Fixed

- Corrected environment mappings, parser/output alignment, optional-node conditions,
  timeout handling, path safety, and documentation drift identified by the 1.5 audit.

## [1.3.3] - 2026-06-19

### Added

- **`abi.sciplot`**: Publication-grade scientific figure compiler. Core protocol:
  `FigureSpec → Validate → Render → Export → Lint → Provenance`.
  Supports 8 figure types (barplot, boxplot_with_points, violin_with_box,
  scatterplot, ordination_plot, stacked_barplot, heatmap, volcano_plot) with
  PDF+SVG+PNG+TIFF export, 3 themes (abi_nature/abi_cell/abi_report),
  perceptually uniform palettes (jet/rainbow blocked), 11 FigureLint rules,
  and SHA256 provenance tracking.
- **`abi-sciplot` CLI**: `validate`, `render`, `lint`, `list-plot-types` commands.
- **Figure rendering in reports**: `write_plugin_report()` and plasmid
  `write_report()` now render figures via `abi.sciplot` by default
  (`use_sciplot=True`). Rendered figures are embedded in HTML reports.
- **`generic_report.py`**: New `_render_figures_via_sciplot()` and
  `_render_figures_via_legacy()` helpers with `use_sciplot` flag for
  graceful fallback to the legacy FigureEngine.

### Changed

- **Dependencies**: Added `pydantic>=2.0`, `pandas>=1.5`, `numpy>=1.24` as core
  dependencies for `abi.sciplot`.
- **Plasmid figure specs**: Updated `plugins/metagenomic_plasmid/figure_specs.yaml`
  to use key-value schema tables (qc_summary, assembly_summary, plasmid_predictions,
  annotations, abundance) compatible with abi_sciplot FigureSpec format.
- **`.gitignore`**: Added `.codex/` for Codex project files.
- **`CLAUDE.md`**: Added `abi.sciplot/` module to source tree and architecture docs.

## [1.3.0] - 2026-06-18

### Added

- **Plan summarization**: `abi plan` now returns a `summary` field with pipeline
  stages, key tools, and platforms. Agents no longer need to read the full
  `execution_plan.json` (saves 78-95% tokens on plan output).
- **`abi query` CLI**: Lightweight metadata query interface (~50ms) for
  pipeline stages, tools, platforms, and step-level inputs/outputs/resources.
  No config loading required — reads `pipeline_dag.yaml` and tool registry only.
- **Benchmark data**: `expected_assertions.yaml` + `config.yaml` for all 5
  plugins under `data/benchmarks/<plugin>/`. wgs_bacteria and metatranscriptomics
  added to complete 5/5 plugin benchmark coverage.
- **Benchmark smoke tests**: Value-level assertion validation for wgs_bacteria
  and metatranscriptomics (upgraded from file-existence-only checks).
- **Conda environments**: Created `wgs`, `abi-qc`, `abi-stats` environments
  (prokka, mlst, STAR, hisat2, subread) for local benchmark execution.
- **`ABIAgentInterface(verbose_errors=False)`**: Error envelopes now omit
  `error_type` by default; agents receive only `error_code` + `diagnostic_hints`
  for recovery. Full details available with `verbose_errors=True`.

### Changed

- **Dry-run envelope**: Removed `written_files` list; agents use `abi inspect`
  on demand instead of receiving auto-generated file lists.
- **Error envelope**: `error_envelope()` now accepts `verbose` parameter;
  `error_type` field only included when `verbose=True`.
- **`@runtime_checkable`**: Added to `ABIPlugin` protocol for `isinstance` checks.

### Bench v0.5 (sibling repo)

- 5 new real execution tasks: T31 (plasmid), T32 (rnaseq), T33 (amplicon),
  T34 (wgs), T35 (metatranscriptomics).
- New scoring checks: `check_pipeline_completed`, `check_assertions_validated`,
  `check_discrepancy_analyzed`, `check_provenance_quality`.
- Benchmark fixtures for all 5 plugins with `real_tool_execution: true`.

## [1.2.0] - 2026-06-18

### Added

- **amplicon_16s**: `vsearch_mergepairs` tool between cutadapt and vsearch_derep,
  fixing the paired-end read-merging gap. New 7-tool chain: cutadapt → merge →
  derep → UNOISE3 → SINTAX → diversity. (P0-2)
- **rnaseq_expression**: `build_count_matrix` tool that collects per-sample
  featureCounts outputs into a unified count matrix for DESeq2. (P0-1)
- **Environment automation**: `envs/rnaseq.yml` conda spec + `scripts/install_deseq2.R`
  (BiocManager installer) + `scripts/setup_rnaseq_env.sh` (orchestrator).
  One-command setup: `abi setup-resources --type rnaseq_expression`. (P1-1)
- **Taxonomy database**: `scripts/download_rdp_sintax.sh` (RDP 16S training set
  downloader, ~50 MB) + `scripts/generate_synthetic_taxonomy.py` (offline synthetic
  fallback, 23 lineages). Three-tier setup: `abi setup-resources --type amplicon_16s`
  with `--mock` and `--dry-run` flags. (P1-2)
- **Smoke tests**: `tests/smoke/test_dry_run_smoke.py` — 7 fast plan-generation tests
  for all 5 plugins (no tools; <1s each). `tests/smoke/test_tool_smoke.py` — real-tool
  execution test with synthetic E. coli reads. `smoke` and `requires_tools` pytest markers.
- **Test coverage**: +90 tests (527 → 625), including `test_workflow_validation.py`
  (28 tests, 19%→98%), `test_provenance.py` (34 tests, 49%→98%), and
  `test_hpc_runtime.py` (28 tests, 19%→66%).
- **Dev docs**: `docs/devlog.md` (development log), updated `docs/next_development_plan.md`
  with Route C and P0-P2 status.
- Shared pytest fixtures in `tests/conftest.py`: `mock_sample`, `mock_contract_dict`,
  `tmp_project`.

### Changed

- **amplicon_16s**: Output directory numbering updated (02_merge → 03_derep →
  04_denoise → 05_taxonomy → 06_diversity) to accommodate new merge step.
- **Resources**: `check_resources` and `setup_resources` now support `rnaseq_expression`
  and `amplicon_16s` analysis types (previously only `metagenomic_plasmid`).
- `pyproject.toml`: Added `smoke` and `requires_tools` pytest markers; excluded `*.R`
  files from ruff linting.

### Fixed

- **12 bugs** from lightweight local IDE rnaseq pipeline test:
  - `check_installation` falls back to system PATH when executable not in conda env.
  - `_safe_output_path` skips validation for ABI-internal stdout/stderr paths.
  - `_ensure_step_output_dirs` pre-creates output_dir itself, not just parent.
  - STAR: added `--readFilesCommand zcat` (rnaseq_expression + metatranscriptomics).
  - featureCounts: added `-p` paired-end flag (rnaseq_expression + metatranscriptomics).
  - DESeq2: `estimateSizeFactors(type="poscounts")`, `DESeq(fitType="mean")`,
    all-zero gene filter before size factor estimation.
- **mypy**: 5 errors → 0 across 138 source files (type narrowing in limitations.py,
  citations.py, contracts/__init__.py; no-redef fix in dag.py).
- **ruff**: 4 errors → 0 (unused imports, line-too-long).
- **contract-lint**: No longer crashes on dict-format DAG `nodes`.

### Known limitations

- **DESeq2**: Conda R + Bioconductor DESeq2 can have dependency conflicts; the setup
  script falls back to system R when needed. Verified working on Ubuntu 24.04 with
  R 4.3.3 + DESeq2 1.42.1.
- **HPC runtime**: Unit-tested at 66%. Remaining 34% (`_submit_jobs`, `_poll_slurm`,
  `_collect_results`) requires a real SLURM/PBS environment.
- **amplicon taxonomy DB**: Synthetic mode is for testing only; real SINTAX classification
  requires the RDP training set (download via `abi setup-resources --type amplicon_16s`).
- **STAR index**: Genome index must be built manually before running rnaseq_expression
  end-to-end (future: `abi setup-resources` integration).

## [1.1.0] - 2026-06-14

### Added
- `abi-mcp` console_script entry point for starting the MCP stdio server directly.
- `abi install-skills` CLI command to install bundled SKILL.md skill files into
  `~/.claude/skills/abi/` for Claude Code auto-discovery.
- `abi_agent/SKILL.md` — new agent skill teaching Claude Code how to use the
  pip-installed `abi` CLI (lifecycle, transport methods, error recovery).
- `abi.get_agent_guide()` and `abi.list_plugins_summary()` Python API for
  agents to get operating instructions without calling the CLI.
- Enhanced `abi/__init__.py` with package documentation and agent-facing helper
  functions.

### Changed
- **Skills relocated**: moved from repo-root `skills/` to `src/abi/skills/` so
  they are installed inside the package and always available at runtime.
- `abi` package `__init__.py` now exports `get_agent_guide()` and
  `list_plugins_summary()` in addition to `__version__`.
- Updated `test_registry_skill_docs_exist` to resolve skill paths against the
  in-package `skills/` directory.

### Fixed
- `list_plugins_summary()` narrowed `except Exception` to `except ImportError`
  so real plugin-loading failures propagate instead of silently returning `[]`.
- `get_agent_guide()` lifecycle order corrected: `run` (step 5) now precedes
  `report` (step 6), matching `SKILL.md` and logical execution order.
- `get_agent_guide()` docstring comment fixed: `list_plugins_summary()` returns
  dicts, not tuples.
- `abi install-skills` now accepts `--output-json` and emits standard agent JSON
  envelopes, consistent with other lifecycle commands.
- `abi install-skills` no longer copies `README.md` (human documentation) to the
  target skills directory; only `SKILL.md` files in subdirectories are installed.
- `--target` help text corrected from `~/.claude/skills` to `~/.claude/skills/abi`
  to match the actual default path.
- `abi install-skills` uses atomic copy (temp directory) to prevent partial
  installs on disk-full or permission errors.
- `src/abi/skills/README.md`: stale `skills/` path prefixes removed after relocation.
- Pyproject sdist `include` list: removed stale `"skills"` entry referencing the
  deleted repo-root directory.
- Skills source path resolution uses `importlib.resources.files()` with a
  `Path(abi.__file__)` fallback for robustness across install layouts.

### Security
- Sample sheet path resolution now validates that resolved paths stay within the
  project directory, preventing path-traversal attacks via `../../` in input paths.

### Fixed (codebase-wide audit)
- **Executor**: step iteration now wraps in `try/except` so provenance artifacts
  are always written even when an unexpected exception crashes the pipeline.
- **Schemas**: `VALID_PLATFORMS`, `VALID_MODES`, `VALID_PLASMID_STRATEGIES` are
  now `frozenset` (documented as "frozen" but were mutable `set`). Added
  `"generic"` to `VALID_PLATFORMS` to match `SampleInput`'s default.
- **Job Service**: Popen creation + registration is now atomic (single lock
  acquisition) to eliminate the race window where `cancel()` could miss a
  subprocess. `_kill_process` uses `proc.wait()` instead of `proc.communicate()`
  to avoid concurrent access to the same `Popen` object.
- **Pipeline**: `_run_external_step` now catches all exceptions (not just
  `ToolError`), preventing pipeline crashes from `OSError`/`FileNotFoundError`.
  Standard output parsing is also wrapped in `try/except`.
- **CLI**: `dispatch_command` now has a `try/except` wrapper (was the only
  command without one). `_emit_agent_json` exits with code 1 for unparseable or
  non-dict payloads instead of silently returning 0. `report_command` no longer
  defaults to `metagenomic_plasmid` when `--type` is omitted.
- **CLI**: `install-skills` `--output-json` flag, corrected `--target` help
  text, README.md exclusion, and atomic install (see previous section).
- **DAG**: `internal` steps are no longer filtered out of the DAG, preserving
  dependency edges for downstream steps. `_is_shared_output_path` uses explicit
  directory-name heuristics instead of relying on `Path.suffix` alone.
- **Diagnostics**: `missing_database` now checked before `invalid_config` so
  database-path errors are classified correctly. `parse_failed` uses multi-word
  phrase matching instead of substring `"parse"`.
- **Config**: `deep_merge` uses `isinstance(x, Mapping)` for both base and
  override values, supporting `OrderedDict` and other mapping types.
- **Contracts**: `.yml` tool contract files are now discovered alongside
  `.yaml` files (previously silently ignored).
- **Runtime**: `LocalRuntime` uses `.get()` for optional `log_dir` config key and
  a `_coerce_bool` helper to handle string `"false"` from env vars.
- **Provenance**: `_tsv_value` now replaces embedded tabs/newlines to prevent
  TSV column corruption.
- **Metatranscriptomics**: thread count validation accepts string integers
  (e.g., `"8"` from env-var substitution).
- **Nextflow exporter**: `internal` steps are skipped during export (no
  Nextflow equivalent for Python-side processing).

## [1.0.0] - 2026-06-13

### Added
- `abi dispatch` CLI command for headless agent dispatches (used by Job Service subprocess workers).
- Job Service force-kill: subprocess workers (`--subprocess-workers`) receive SIGTERM on cancel.
- Job Service `remote_scheduler_job_id` tracking for HPC/cloud backends.
- Job Service `worker_pid` field for process-level cancellation audit.

### Changed
- **Architecture**: Eliminated `_compat/` compatibility layer. `provenance.py` (482 lines) and
  `tools.py` (524 lines) are now first-class modules with their own logic.
- **Architecture**: Unified schema types in `abi.schemas` — canonical `ExecutionPlan`, `PlanStep`,
  `SampleInput`, `SampleContext` now live in one place with `ABI`-prefixed aliases.
- **Architecture**: `autoplasm/` is now a backward-compatible re-export shim. The real engine
  lives in `plugins/metagenomic_plasmid/_engine/`.
- **Architecture**: `metagenomic_plasmid` is now a self-contained package under
  `plugins/metagenomic_plasmid/` with zero imports from `abi.autoplasm`.
- `RunLogger`, `PipelineProgressRecorder`, TSV provenance writers moved from `_compat` to
  `abi.provenance`.
- `ToolRegistry`, `ToolSkill`, `GenericCommandSkill`, `RunResult` moved from `_compat` to
  `abi.tools`.
- Cancelling a running job now marks it `cancelled` after dispatch completes (was `succeeded`
  with `cancel_requested` flag).
- Updated schema types: `ExecutionPlan` now includes optional `analysis_type` field.

### Removed
- Removed `abi._compat` package entirely (986 lines across 6 files migrated to first-class modules).

## [0.1.0] - 2026-06-12

### Added
- Initial release as standalone package.
- Core ABI schemas: `ABISample`, `ABISampleContext`, `ABIPlanStep`, `ABIExecutionPlan`.
- Plugin system with Python `entry_points` registration.
- Built-in metatranscriptomics plugin.
- Bundled metagenomic plasmid pipeline under `abi.autoplasm`.
- Local and Nextflow runtime backends.
- `ABIAgentInterface` and OpenAI-compatible descriptor export.
- Public SDK entry points for plugin authors: `abi.tools`, `abi.errors`, and `abi.testing`.
- ABI HTTP Job Service and `abi job submit/list/status/artifacts/cancel`.
- Optional MCP stdio server module.
- `abi_validate_result` as a read-only agent/OpenAI tool.
- Repository-local configs, env specs, tool skills, examples, small datasets, and fixtures.
