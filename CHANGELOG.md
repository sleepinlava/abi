# Changelog

## [0.1.0] - 2025-06-11

### Added
- Initial release as standalone package
- Core ABI schemas: ABISample, ABISampleContext, ABIPlanStep, ABIExecutionPlan
- Plugin system with Python entry_points registration
- Built-in metatranscriptomics plugin (fastp → STAR → featureCounts)
- Optional metagenomic_plasmid adapter plugin (requires autoplasm)
- GenericABIExecutor for plan execution with full provenance
- StandardTableManager for schema-driven TSV table management
- DAG inference by path matching for dependency resolution
- Local and Nextflow runtime backends
- ABIAgentInterface for transport-neutral agent integration
- OpenAI function calling tool descriptor export
- CLI via Typer: list-types, init, plan, dry-run, inspect, report, run, export-nextflow, export-openai-tools
