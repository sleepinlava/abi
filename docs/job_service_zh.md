# ABI Job Service

Job Service 允许 Agent 提交长时间运行的工作而不阻塞交互式工具调用。

## 启动

```bash
# 进程内 worker（默认 — 无强制终止）
abi job-service --host 127.0.0.1 --port 18791 --workers 1 --store jobs.json

# 子进程 worker（通过 SIGTERM 启用强制终止）
abi job-service --workers 2 --subprocess-workers
```

`--store` 是可选的。当提供时，作业记录以 JSON 格式持久化，重启服务后仍可检查已完成的作业。

## HTTP API

- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{id}`
- `GET /jobs/{id}/artifacts`
- `POST /jobs/{id}/cancel`

## CLI 客户端

```bash
abi job submit --command run --analysis-type metatranscriptomics --confirm-execution
abi job list
abi job status JOB_ID
abi job artifacts JOB_ID
abi job cancel JOB_ID
```

执行类作业除非带有 `confirm_execution=true`，否则会以 `confirmation_required` 状态被拒绝。

## 强制终止

当以 `--subprocess-workers` 启动时，每个作业在隔离的 `abi dispatch` 子进程中运行。取消正在运行的作业会向 worker 进程发送 **SIGTERM**。如果进程在 3 秒内未退出，则发送 **SIGKILL**。

当未启用 `--subprocess-workers`（默认）时，取消操作仅将 `cancel_requested` 设为 `true`。dispatch 运行至完成，但最终状态标记为 `cancelled`。

作业记录存储 `worker_pid` 以供审计。

## 远程调度器追踪

对于 Nextflow、HPC 和云端后端，Job Service 从 dispatch 结果信封中提取 `remote_scheduler_job_id`。该字段在持久化往返中保留，可用于将 ABI 作业与外部调度器作业 ID（Slurm、AWS Batch 等）关联。

## 产物索引

产物包括 `outdir`、`execution_plan.json`、provenance 文件、`provenance/job.json`、表格、报告、显式声明的 `written_files` 以及可用的运行时输出路径。`provenance/job.json` 记录排队的命令、后端、状态时间戳、取消标志、worker PID、远程调度器作业 ID 以及任何 Job Service 错误字段，使得复制的结果目录携带自身的作业级调度溯源信息。

## 重启语义

- `queued` 作业被重新排队。
- `running` 和 `cancel_requested` 作业在重启时标记为 failed。
- 终端状态的作业保持可检查。
