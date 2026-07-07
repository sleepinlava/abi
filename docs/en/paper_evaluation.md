# Paper Evaluation Protocol

The ABI paper evaluation compares four ways to produce valid bioinformatics
workflow plans from the same repository context:

1. README/manual CLI.
2. Direct Python API.
3. Generic LLM tool-calling.
4. ABI-mediated planning and execution.

The frozen task matrix is stored in `bench/paper_tasks/tasks.yaml`. Metrics are
defined in `bench/paper_tasks/metrics_schema.yaml` and include plan validity,
command correctness, dry-run success, provenance completeness, intervention
count, and time to a valid plan.

All arms start from the same clean checkout and may only use the inputs named in
the task file. Dry-run output JSON is treated as the authoritative execution
trace for scoring. Human interventions should be counted whenever the evaluator
must correct a command, choose an omitted parameter, or explain a failed plan.

Generated artifacts should be written to ignored result directories such as
`/tmp/abi-paper-*` or `results/`; only the benchmark definition and final metric
tables should be committed.
