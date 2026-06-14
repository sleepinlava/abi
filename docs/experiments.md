# ABI Agent Experiments

The experiment scaffold is under `docs/experiments/`. It is designed to test
whether an untrained general agent performs better with ABI's control layer
than with unstructured or weakly structured alternatives.

**Note:** The full paper submission plan (including a three-tier Demo matrix
and 7-month timeline) is documented in [`demo_plan.md`](demo_plan.md). This
file describes the original experimental design skeleton; `demo_plan.md`
supersedes it for planning purposes.

## Groups

- README baseline
- Plain Python API baseline
- Plain tool-calling baseline
- ABI control layer

## Metrics

The initial metrics schema is in `docs/experiments/metrics.tsv` and tracks
completion rate, dry-run behavior, parameter errors, diagnostic recovery, and
human intervention count.

## Traces

Golden ABI control-layer traces live in `golden_traces/`
(`metagenomic_plasmid.jsonl`, `metatranscriptomics.jsonl`). Experimental traces
should be copied or referenced from `docs/experiments/traces.jsonl` with the
group and task id recorded.

## Task Set

Initial tasks:

- choose the correct analysis type
- generate a plan
- perform a dry-run
- diagnose missing resources
- inspect result artifacts
- summarize standard tables
- refuse to execute `run` without confirmation

## Current Plugins Used in Experiments

| Plugin | Tools | Lines | Standard Table |
| --- | --- | --- | --- |
| `metatranscriptomics` | fastp, STAR, HISAT2, featureCounts | 574 | `gene_expression.tsv` |
| `metagenomic_plasmid` | 67 tool contracts (39 engine files, 9,006 lines) | ~9,000 | `plasmid_predictions.tsv`, `abundance.tsv`, etc. (16 standard tables) |
