# Changelog

## [0.1.0] - 2026-06-12

### Added
- Initial release as standalone package.
- Core ABI schemas: `ABISample`, `ABISampleContext`, `ABIPlanStep`, `ABIExecutionPlan`.
- Plugin system with Python `entry_points` registration.
- Built-in metatranscriptomics plugin (fastp → STAR → featureCounts).
- Optional metagenomic_plasmid adapter plugin (requires `autoplasm>=0.1.0`).
- `GenericABIExecutor` for plan execution with full provenance.
- `StandardTableManager` for schema-driven TSV table management.
- DAG inference by path matching for dependency resolution.
- Local and Nextflow runtime backends.
- `ABIAgentInterface` for transport-neutral agent integration.
- OpenAI function calling tool descriptor export.
- CLI via Typer: `list-types`, `init`, `plan`, `dry-run`, `inspect`, `report`, `run`, `export-nextflow`, `export-openai-tools`.
- Public SDK entry points for plugin authors: `abi.tools`, `abi.errors`, and `abi.testing`.
- Plugin contract testing helper (`assert_plugin_contract`).
- Path-priority dev setup tool (`abi-dev-setup`) for environments where another `abi` package may shadow this one.
- Runtime warning when `abi` is loaded from an unexpected location.

### Changed
- CLI and agent planning/execution commands require an explicit ABI analysis type.
- Metatranscriptomics demo registry uses ABI-owned environment names.
- Internal compatibility modules no longer define public-facing error classes.
- Improved type hints and error handling across multiple modules.
