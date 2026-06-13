# ABI Job Service

The Job Service lets agents submit long-running work without blocking the
interactive tool call.

## Start

```bash
abi job-service --host 127.0.0.1 --port 18791 --workers 1 --store jobs.json
```

`--store` is optional. When provided, job records are persisted as JSON and
completed jobs can be inspected after restarting the service.

## HTTP API

- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{id}`
- `GET /jobs/{id}/artifacts`
- `POST /jobs/{id}/cancel`

## CLI Client

```bash
abi job submit --command run --analysis-type metatranscriptomics --confirm-execution
abi job list
abi job status JOB_ID
abi job artifacts JOB_ID
abi job cancel JOB_ID
```

Execution jobs are rejected with `confirmation_required` unless
`confirm_execution=true` is present.

Cancelling a queued job marks it `cancelled`. Cancelling a running job records
`status: cancel_requested` immediately and keeps `cancel_requested: true` on the
job record even if the underlying dispatch later finishes as `succeeded` or
`failed`.

## Artifact Index

Artifacts include paths for `outdir`, `execution_plan.json`, provenance files,
`provenance/job.json`, tables, reports, explicit `written_files`, and runtime
outputs when available. `provenance/job.json` records the queued command,
backend, status timestamps, cancellation flag, and any Job Service error fields
so a copied result directory carries its own job-level scheduling provenance.

## Restart Semantics

- `queued` jobs are requeued.
- `running` and `cancel_requested` jobs are marked failed on restart.
- terminal jobs remain inspectable.
