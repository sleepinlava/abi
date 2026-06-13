# ABI Agent Experiments

The experiment scaffold is under `docs/experiments/`. It is designed to test
whether an untrained general agent performs better with ABI's control layer
than with unstructured or weakly structured alternatives.

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

Golden ABI control-layer traces live in `golden_traces/`. Experimental traces
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
