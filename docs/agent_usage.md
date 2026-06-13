# Agent Usage Guide

Agents should use ABI as a lifecycle control layer rather than writing
bioinformatics pipeline code directly.

## Safe Sequence

1. `abi_list_types`
2. `abi_export_agent_context` or `abi_doctor_agent`
3. `abi_plan`
4. `abi_dry_run`
5. `abi_inspect`
6. `abi_report`
7. `abi_run` only after explicit user approval

## CLI JSON

```bash
abi list-types --output-json
abi plan --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi inspect --result-dir results/rnaseq_demo --output-json
abi report --type metatranscriptomics --result-dir results/rnaseq_demo --output-json
```

## Recovery

On error, inspect:

- `error_code`
- `diagnostic_hints`
- `result_dir/provenance/commands.tsv`
- `result_dir/provenance/resolved_inputs.tsv`

Do not parse raw tool outputs first. Prefer standard tables under `tables/`.

## Golden Traces

Known-good agent call sequences are stored in `golden_traces/` and replayed by
`tests/integration/test_golden_traces.py`.
