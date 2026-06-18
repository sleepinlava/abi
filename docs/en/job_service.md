# ABI Job Service

The Job Service lets agents submit long-running work without blocking the
interactive tool call.

## Start

```bash
# In-process workers (default — no force-kill)
abi job-service --host 127.0.0.1 --port 18791 --workers 1 --store jobs.json

# Subprocess workers (force-kill enabled via SIGTERM)
abi job-service --workers 2 --subprocess-workers
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

## Force-Kill

When started with `--subprocess-workers`, each job runs in an isolated
`abi dispatch` subprocess. Cancelling a running job sends **SIGTERM** to the
worker process. If the process does not exit within 3 seconds, **SIGKILL** is
sent.

When `--subprocess-workers` is not enabled (default), cancel sets
`cancel_requested=true`. The dispatch runs to completion but the final status is
marked `cancelled`.

The job record stores `worker_pid` for auditability.

## Remote Scheduler Tracking

For Nextflow, HPC, and cloud backends, the Job Service extracts
`remote_scheduler_job_id` from the dispatch result envelope. This field
survives persistence round-trips and can be used to correlate ABI jobs with
external scheduler job IDs (Slurm, AWS Batch, etc.).

## Artifact Index

Artifacts include paths for `outdir`, `execution_plan.json`, provenance files,
`provenance/job.json`, tables, reports, explicit `written_files`, and runtime
outputs when available. `provenance/job.json` records the queued command,
backend, status timestamps, cancellation flag, worker PID, remote scheduler job
ID, and any Job Service error fields so a copied result directory carries its
own job-level scheduling provenance.

## Restart Semantics

- `queued` jobs are requeued.
- `running` and `cancel_requested` jobs are marked failed on restart.
- terminal jobs remain inspectable.
