# Changelog

## [0.2.0] - 2026-06-12

### Added
- Bundled the metagenomic plasmid pipeline under `abi.autoplasm`.
- Added the `autoplasm` compatibility CLI while keeping `autoplasm-abi` as the only Python distribution.
- Added ABI HTTP Job Service and `abi job submit/list/status/artifacts/cancel`.
- Added optional MCP stdio server module.
- Added `abi_validate_result` as a read-only agent/OpenAI tool.
- Added repository-local configs, env specs, tool skills, examples, small datasets, and fixtures for the bundled plasmid workflow.

### Changed
- `metagenomic_plasmid` no longer depends on an external `autoplasm` package.
- OpenAI tool exports keep public tool names under the `abi_` prefix.
- `ABI_MAMBA_ROOT` is now the preferred mamba root override; `AUTOPLASM_MAMBA_ROOT` remains compatible.
- Release and packaging metadata now build one `autoplasm-abi` wheel containing both ABI core and `abi.autoplasm`.

### Removed
- Removed the old path-priority `abi-dev-setup` workaround for split-repository shadowing.

## [0.1.0] - 2026-06-12

### Added
- Initial release as standalone package.
- Core ABI schemas: `ABISample`, `ABISampleContext`, `ABIPlanStep`, `ABIExecutionPlan`.
- Plugin system with Python `entry_points` registration.
- Built-in metatranscriptomics plugin.
- Optional metagenomic plasmid adapter.
- Local and Nextflow runtime backends.
- `ABIAgentInterface` and OpenAI-compatible descriptor export.
- Public SDK entry points for plugin authors: `abi.tools`, `abi.errors`, and `abi.testing`.
