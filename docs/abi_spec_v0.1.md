# ABI Specification v0.1

## Lifecycle API

`ABIAgentInterface` is the stable boundary for all transports:

- `list_types`
- `plan`
- `dry_run`
- `inspect`
- `report`
- `run`
- `export_nextflow`
- `export_agent_context`
- `doctor_agent`
- `dispatch`

Every public method returns a JSON string with a uniform envelope.

## JSON Envelopes

Success:

```json
{
  "status": "success",
  "command": "plan",
  "result": {}
}
```

Confirmation gate:

```json
{
  "status": "confirmation_required",
  "command": "run",
  "result": {
    "message": "Re-run with confirm_execution=true after user approval."
  }
}
```

Error:

```json
{
  "status": "error",
  "command": "dry_run",
  "error_code": "missing_input",
  "error": "Input file does not exist.",
  "diagnostic_hints": []
}
```

## Permissions

- `read_only`: `list_types`, `inspect`, `abi_validate_result`,
  `export_agent_context`, `doctor_agent`
- `planning_write`: `plan`, `dry_run`, `report`, `export_nextflow`
- `execution`: `run`

Execution requires `confirm_execution=true`. Descriptors do not export
`abi_run` by default.

## Standard Artifacts

Planning and dry-run outputs should converge on this structure:

```text
outdir/
  execution_plan.json
  provenance/
    commands.tsv
    resolved_inputs.tsv
    tool_versions.tsv
    resources.json
    run_summary.json
    progress.jsonl
  tables/
    *.tsv
  report/
    report.md
    report.html
```

`provenance/commands.tsv` always includes the lifecycle columns from
`Rebuild.md`. Nextflow-backed runs also populate `remote_scheduler_job_id` when
the Nextflow trace exposes a scheduler/native id, for example from Slurm or
cloud batch executors.

## Error Codes

ABI uses stable error codes from `abi.diagnostics`, including
`unknown_analysis_type`, `invalid_config`, `invalid_sample_sheet`,
`missing_input`, `missing_resource`, `missing_database`, `tool_not_found`,
`permission_required`, `runtime_not_supported`, `nonzero_exit`,
`parse_failed`, `empty_result`, `artifact_missing`, and `internal_error`.

## Plugin Contracts

Each plugin must provide:

- `abi-plugin.yaml`
- `tool_registry.yaml`
- `standard_tables.yaml`
- `tool_contracts/*.yaml`

`abi.testing.assert_plugin_contract()` validates runtime Python interfaces and
machine-readable plugin assets.
