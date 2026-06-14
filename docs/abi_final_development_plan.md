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
ruff format --check src/abi tests
mypy src/abi/ --ignore-missing-imports
python -m build
python -m twine check dist/*
```

## Evidence Artifacts

- Golden agent traces live in `golden_traces/`.
- Plugin manifests and tool contracts live in `plugins/*/`.
- Experiment scaffold lives in `docs/experiments/`.
- Demo output must contain `execution_plan.json`, `provenance/`, `tables/`,
  and `report/`.

## Next Development Roadmap

The next phase is to move ABI from a strong control plane to a validated,
literature-backed scientific workflow.

### 1. Contract Completeness

- Extend runtime contracts to validate input size, extension, directory file
  counts, and optional/required input semantics before execution.
- Add a contract-lint command for `pipeline_dag.yaml`, `tool_registry.yaml`, and
  `tool_contracts/*.yaml`.
- Promote contract violations into stable agent-facing diagnostic codes.

### 2. Reproducibility Manifests

- Record real tool versions through per-tool version probes.
- Add database/model manifests with source, version, checksum, license note, and
  validation date.
- Support pinned conda-lock files or containers for smoke-test routes.

### 3. Biological Validation

- Add small positive and negative benchmark datasets for the default route.
- Define expected rows and thresholds in standard tables, not only raw files.
- Track known limitations for host prediction, plasmid binning, abundance, and
  correlation-network interpretation.

### 4. Literature-Backed Reporting

- Maintain a citation registry keyed by tool id and workflow stage.
- Emit methods, versions, database manifests, and citations into reports.
- Mark optional tools as `validated`, `available`, or `experimental` based on
  fixture coverage and literature review.

Detailed acceptance criteria and the initial evidence map live in
[Workflow Validation and Scientific Evidence Plan](workflow_validation.md).
