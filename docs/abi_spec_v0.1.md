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

ABI uses 14 stable error codes from `abi.diagnostics`, enumerating every
recognized failure mode:

| Code | Triggers when |
| --- | --- |
| `unknown_analysis_type` | plugin ID not recognized |
| `invalid_config` | YAML/JSON config failed schema validation |
| `invalid_sample_sheet` | sample sheet missing or malformed |
| `missing_input` | a required input file does not exist |
| `missing_resource` | a resource is NOT_CONFIGURED or missing |
| `missing_database` | a bioinformatics database is unavailable |
| `tool_not_found` | an external tool executable is not on PATH |
| `permission_required` | execution requires explicit user confirmation |
| `runtime_not_supported` | the requested engine is not local/nextflow |
| `nonzero_exit` | an external command returned non-zero |
| `parse_failed` | tool output could not be parsed into tables |
| `empty_result` | the pipeline produced no output |
| `artifact_missing` | a required result artifact is absent |
| `internal_error` | unexpected/unclassified error at the ABI boundary |

The frozen set is defined in `abi.diagnostics.ERROR_CODES` and each error
response carries a stable `error_code` + actionable `diagnostic_hints`.

## Plugin Contracts

Each plugin must provide:

- `abi-plugin.yaml`
- `tool_registry.yaml`
- `standard_tables.yaml`
- `tool_contracts/*.yaml`

`abi.testing.assert_plugin_contract()` validates runtime Python interfaces and
machine-readable plugin assets.

## Step Contracts and Reproducibility

Runtime step contracts are embedded in `PlanStep.params["_contract"]` by
plugins that support contract enforcement. For the DAG-driven
`metagenomic_plasmid` plugin, this block is copied from `pipeline_dag.yaml`.

Supported output checks include:

- existence of declared files or directories
- `min_size`
- `extensions`
- directory `contains`
- `min_files`
- FASTA `min_contigs`
- JSON `required_keys`
- dotted JSON `schema`
- runtime `assertions`
- checksum recording for downstream verification

Executors may resolve actual files after a tool succeeds when a planner path is
abstract but the tool writes fixed filenames. Resolved outputs, not abstract
planner placeholders, are used for output contracts and assertions.

Scientific reproducibility requires more than the ABI envelope. Production
workflows should also pin tool versions, record database/model manifests and
checksums, and validate known benchmark datasets. The repository-level target is
tracked in [Workflow Validation and Scientific Evidence Plan](workflow_validation.md).
