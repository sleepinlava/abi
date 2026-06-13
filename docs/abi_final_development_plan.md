# ABI Final Development Plan

This document is the repository-local frozen plan derived from `Rebuild.md`.
It keeps the implementation boundary explicit so future work does not drift
back into a single AutoPlasm CLI wrapper.

## Product Shape

ABI is delivered as:

- ABI Core
- Agent-facing tool layer
- Plugin SDK
- HTTP Job Service
- PyPI package: `abi-agent`

The Python import package remains `abi`, and the primary command remains `abi`.

## Architecture Rules

- Core is thick: plugin discovery, schemas, permissions, diagnostics,
  provenance, standard tables, contracts, execution planning, and reports live
  under `src/abi`.
- Transports are thin: CLI JSON, OpenAI descriptors, MCP, and HTTP jobs call
  `ABIAgentInterface` rather than reimplementing business logic.
- Plugins are clear: biological planning, parsing, tool contracts, standard
  tables, and reports belong to each analysis plugin.
- Agents do not need to import Python classes. They call CLI JSON, descriptors,
  MCP tools, or HTTP jobs.

## Built-In Plugins

- `metagenomic_plasmid`: AutoPlasm adapter and complex primary case.
- `metatranscriptomics`: lightweight portability demo using fastp,
  STAR/HISAT2, and featureCounts.

## Required Gates

The repository should keep these gates passing when the environment provides the
required tools:

```bash
pytest
ruff check src/abi tests
mypy src/abi/ --ignore-missing-imports
black --check src/abi tests
python -m build
python -m twine check dist/*
```

The current development sandbox has shown directory-level `black --check`
process-hang behavior; per-file `black --check` and `twine check` remain
release criteria.

## Evidence Artifacts

- Golden agent traces live in `golden_traces/`.
- Plugin manifests and tool contracts live in `plugins/*/`.
- Experiment scaffold lives in `docs/experiments/`.
- Demo output must contain `execution_plan.json`, `provenance/`, `tables/`,
  and `report/`.
