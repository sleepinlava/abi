# Changelog

## [Unreleased]

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
