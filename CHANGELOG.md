# Changelog

## [Unreleased]

### Added
- `docs/workflow_validation.md` to track the path toward a constrained,
  verifiable, reproducible, and literature-backed metagenomic plasmid workflow.
- Executor regression tests covering output directory preparation, actual-output
  resolution, R1/R2 matching, and JSON assertion context handling.

### Changed
- Development, plugin, ABI spec, metagenomic plasmid, roadmap, README, and
  agent-facing docs now describe runtime step contracts and scientific
  validation boundaries.
- `ruff format --check src tests` is now clean across the repository.

### Fixed
- **Executor**: output contract validation and assertions now use resolved
  on-disk output files when planner paths are abstract.
- **Executor**: `output_dir` is no longer pre-created for tools that must create
  their own output directory; only its parent directory is prepared.
- **Executor**: actual-output matching is deterministic and read-pair aware, so
  `clean_read1`/`clean_read2` do not silently swap R1/R2 files.
- **Contracts**: `min_files` and JSON `required_keys` contracts are now enforced.
- **Lint**: removed stale imports and import-order issues found by `ruff check`.

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
