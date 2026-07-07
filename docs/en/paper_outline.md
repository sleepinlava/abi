# ABI Paper Outline

## Title

ABI: Contract-Guided Agentic Bioinformatics Workflow Planning and Execution

## Abstract

Summarize the problem of reliable agent-mediated bioinformatics execution, ABI's
contract-guided planning model, the evaluation design, and the observed gains in
plan validity, command correctness, dry-run success, provenance completeness, and
human intervention count.

## Introduction

Describe why bioinformatics workflows are difficult for generic agents: many
tool-specific parameters, environment constraints, data-dependent branches,
database resources, and provenance requirements. Position ABI as a control plane
that exposes workflow intent, validation, dry-runs, and reproducible execution
surfaces.

## System Architecture

Explain the thick-core, thin-adapter architecture: plugin manifests,
`pipeline_dag.yaml`, tool registries, tool contracts, planners, runtime locks,
provenance writers, CLI/MCP adapters, and report generation.

## Contract Model

Define the contract layers used by ABI: tool contracts, DAG structure,
template-parameter linting, report artifact metadata, standard table schemas,
resource manifests, and runtime assertions.

## Evaluation Design

Use the frozen task matrix in `bench/paper_tasks/tasks.yaml` and the metric
schema in `bench/paper_tasks/metrics_schema.yaml`. Compare README/manual CLI,
Direct Python API, Generic LLM tool-calling, and ABI-mediated planning and
execution. Record final scores in `metrics.tsv`.

## Results

Report task-level and aggregate metrics: plan validity, command correctness,
dry-run success, provenance completeness, intervention count, and time to valid
plan. Include confidence intervals or repeated-run summaries where available.

## Case Studies

Discuss representative tasks from metagenomic plasmid, metatranscriptomics, and
RNA-seq expression dry-runs. Highlight where ABI's query, dry-run, validation,
and provenance surfaces prevented common planning errors.

## Limitations

Cover reliance on plugin metadata quality, remaining gaps in real-tool smoke
execution, external database availability, scheduler/environment variability,
and the distinction between dry-run success and full biological validation.

## Reproducibility Appendix

List repository version, benchmark files, environment setup, release gate,
commands, scoring instructions, and artifact locations. Reference
`bench/paper_tasks/tasks.yaml`, `bench/paper_tasks/metrics_schema.yaml`, and
`metrics.tsv` as the canonical evaluation inputs and score table.
