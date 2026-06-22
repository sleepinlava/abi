# ABI HPC 开发指南

ABI 的 `hpc` 运行时以 Slurm 为生产目标，并保留 PBS 脚本与依赖提交兼容性。每个
worker 步骤生成独立 JSON 载荷和批处理脚本；driver 预检步骤在首次提交前同步执行。

```bash
abi check --type easymetagenome --config p1.yaml --engine hpc
abi run --type easymetagenome --config p1.yaml --engine hpc \
  --scheduler slurm --partition compute --account project \
  --hpc-timeout 604800 --confirm-execution
```

Slurm 提交使用真实 `afterok` 作业依赖。运行时通过 `squeue` 监控活动作业，并用
`sacct` 获取已结束作业状态；超时作业会调用 `scancel`。每个作业以原子方式写入
`provenance/step_results/`，汇总阶段生成标准表、命令记录和 `hpc_jobs.json`。

共享 Conda 根目录由 `--mamba-root` 或 `ABI_MAMBA_ROOT` 指定。插件工具通过
`environments.yaml` 的 tool→env 分配解析环境。ViWrap 的环境集合继续由
`resources.conda_env_dir` 指定。使用 `--resume` 时，ABI 仅复用非空且 SHA256
校验与 `provenance/checksums.json` 一致的输出。
