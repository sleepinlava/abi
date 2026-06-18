# ABI 规范 v0.1

## 生命周期 API

`ABIAgentInterface` 是所有传输层的稳定边界：

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

每个公开方法返回一个带有统一信封格式的 JSON 字符串。

## JSON 信封

成功：

```json
{
  "status": "success",
  "command": "plan",
  "result": {}
}
```

确认门控：

```json
{
  "status": "confirmation_required",
  "command": "run",
  "result": {
    "message": "经用户批准后，以 confirm_execution=true 重新运行。"
  }
}
```

错误：

```json
{
  "status": "error",
  "command": "dry_run",
  "error_code": "missing_input",
  "error": "输入文件不存在。",
  "diagnostic_hints": []
}
```

## 权限

- `read_only`：`list_types`、`inspect`、`abi_validate_result`、`export_agent_context`、`doctor_agent`
- `planning_write`：`plan`、`dry_run`、`report`、`export_nextflow`
- `execution`：`run`

执行需要 `confirm_execution=true`。描述符默认不导出 `abi_run`。

## 标准产物

规划和 dry-run 的输出应收敛到以下结构：

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

`provenance/commands.tsv` 始终包含来自 `Rebuild.md` 的生命周期列。Nextflow 支持的运行在 Nextflow trace 暴露调度器/原生 ID 时（例如来自 Slurm 或云端批量执行器）也会填充 `remote_scheduler_job_id`。

## 错误码

ABI 使用来自 `abi.diagnostics` 的 14 个稳定错误码，枚举每一种已识别的失败模式：

| 代码 | 触发条件 |
| --- | --- |
| `unknown_analysis_type` | 插件 ID 未被识别 |
| `invalid_config` | YAML/JSON 配置未通过 schema 验证 |
| `invalid_sample_sheet` | 样本表缺失或格式错误 |
| `missing_input` | 必需的输入文件不存在 |
| `missing_resource` | 资源状态为 NOT_CONFIGURED 或缺失 |
| `missing_database` | 生物信息学数据库不可用 |
| `tool_not_found` | 外部工具可执行文件不在 PATH 中 |
| `permission_required` | 执行需要显式用户确认 |
| `runtime_not_supported` | 请求的引擎不是 local/nextflow |
| `nonzero_exit` | 外部命令返回非零退出码 |
| `parse_failed` | 工具输出无法解析为表格 |
| `empty_result` | 管线未产生任何输出 |
| `artifact_missing` | 必需的结果产物缺失 |
| `internal_error` | ABI 边界处意外/未分类的错误 |

这组固定错误码定义在 `abi.diagnostics.ERROR_CODES` 中，每个错误响应携带稳定的 `error_code` + 可操作的 `diagnostic_hints`。

## 插件合约

每个插件必须提供：

- `abi-plugin.yaml`
- `tool_registry.yaml`
- `standard_tables.yaml`
- `tool_contracts/*.yaml`

`abi.testing.assert_plugin_contract()` 验证运行时 Python 接口和机器可读的插件资产。

## 步骤合约与可复现性

运行时步骤合约由支持合约执行的插件嵌入在 `PlanStep.params["_contract"]` 中。对于 DAG 驱动的 `metagenomic_plasmid` 插件，此块从 `pipeline_dag.yaml` 复制。

支持的输出检查包括：

- 声明的文件或目录是否存在
- `min_size`
- `extensions`
- 目录 `contains`
- `min_files`
- FASTA `min_contigs`
- JSON `required_keys`
- 点分 JSON `schema`
- 运行时 `assertions`
- 校验和记录以供下游验证

当规划路径为抽象路径但工具写入固定文件名时，执行器可在工具成功后解析实际文件。解析后的输出（而非抽象的规划器占位符）用于输出合约和断言。

科学可复现性需要的不仅仅是 ABI 信封。生产级工作流还应固定工具版本、记录数据库/模型清单和校验和，并验证已知的基准数据集。仓库级的目标追踪见
[工作流验证与科学证据计划](workflow_validation_zh.md)。
