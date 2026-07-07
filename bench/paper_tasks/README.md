# ABI Paper Evaluation Tasks

This directory freezes the task matrix and scoring schema used for the ABI
publication evaluation. The tasks are intentionally dry-run oriented so each
arm can be compared without requiring external bioinformatics databases or
long-running tools.

## Files

- `tasks.yaml` defines the benchmark task IDs, workflows, and canonical commands.
- `metrics_schema.yaml` defines the metrics collected for each task and arm.

## Comparison Arms

1. README/manual CLI: participant follows repository documentation and examples.
2. Direct Python API: participant uses ABI Python APIs without the CLI planner.
3. Generic LLM tool-calling: generic agent receives tools and repository context.
4. ABI-mediated planning and execution: agent uses ABI query, dry-run, provenance,
   and validation surfaces.

Each task should be scored with the same metrics and a fixed starting context.
Generated run outputs belong under ignored result directories, not in this
benchmark definition.
