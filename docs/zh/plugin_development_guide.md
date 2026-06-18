# 插件开发指南

ABI 插件在共享生命周期 API 背后暴露生物学分析类型。

## 最小 Python 接口

实现 `abi.interfaces.ABIPlugin` 协议：

- `plugin_id`
- `display_name`
- `description`
- `report_title`
- `load_config()`
- `build_plan()`
- `registry()`
- `table_schemas()`
- `parse_outputs()`
- `write_report()`

通过以下方式注册插件：

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## 插件目录

推荐布局：

```text
plugins/my_analysis/
  abi-plugin.yaml
  config_default.yaml
  sample_sheet_template.tsv
  tool_registry.yaml
  standard_tables.yaml
  tool_contracts/
    tool_a.yaml
  skills/               ← 随包捆绑的 SKILL.md 文件
    tool_a/SKILL.md
  _engine/             ← 可选：复杂引擎代码（参见 metagenomic_plasmid）
```

对于具有大量内部逻辑的复杂插件，使用带有私有 `_engine/` 子目录的自包含包。参见 `plugins/metagenomic_plasmid/` 获取规范示例。

## 技能与 Agent 集成

每个工具应在 `skills/<tool_name>/SKILL.md` 下有一个 `SKILL.md` 文件。
技能捆绑在包内 `src/abi/skills/` 中，并通过以下方式安装到 Claude Code：

```bash
abi install-skills      # → ~/.claude/skills/abi/
```

要添加新技能，在 `src/abi/skills/<tool_name>/SKILL.md` 下创建目录和 SKILL.md 文件。`abi_agent/SKILL.md` 技能教会 Claude Code 如何使用 `abi` CLI 本身；其他技能记录各个生物信息学工具。

## 工具合约

合约是机器可读的，必须与运行时注册表匹配：

- `tool_id`
- `category`
- `execution.env_name`
- `execution.executable`
- `execution.command_template`
- 声明的输入/输出模板字段
- 标准化的标准表名称

在插件测试中使用 `assert_plugin_contract(plugin)`。

## 步骤输出合约

复杂插件可以在执行计划中嵌入逐步骤合约。对于 DAG 驱动的 metagenomic plasmid 插件，`pipeline_dag.yaml` 中的每个节点声明其 `outputs` 和可选的 `assertions`；规划器将这些字段复制到 `PlanStep.params["_contract"]` 中以供运行时执行。

支持的输出检查包括：

- `min_size`：文件或目录的最小字节大小，如 `"1KB"`。
- `extensions`：允许的文件后缀，如 `[.fastq, .fastq.gz]`。
- `contains`：输出目录中必须包含的文件。
- `min_files`：目录下最少的常规文件数，适用于生成的索引。
- `min_contigs`：最少的 FASTA contig 数量。
- `required_keys`：JSON 输出必需的顶层键。
- `schema`：带有简单类型/范围约束的点分 JSON 字段。

断言在输出验证之后根据 `output_files`、`output_json` 和 `return_code` 进行评估。示例：

```yaml
assertions:
  - "output_json.summary.after_filtering.total_reads > 0"
  - "output_files.clean_read1 exists"
```

当声明创建自身输出目录的工具的输出时，继续使用 `output_dir`。通用执行器有意仅创建父目录，因为某些工具在 `output_dir` 于执行前已存在时会失败。

如果规划器输出抽象输出路径而工具写入固定名称，请确保合约的 `format` 和文件名约定是明确的。执行器在检查合约之前按 `output_dir`、format、样本 ID 和 R1/R2 双端提示解析实际文件。

## 标准表

解析器必须仅写入插件声明的表。空表仍应以稳定的表头存在，以便 Agent 在不解析原始工具输出的情况下检查结果。

## 共享基础设施

插件应从公开 SDK 导入：

| 模块 | 用途 |
| --- | --- |
| `abi.schemas` | `SampleInput`、`SampleContext`、`PlanStep`、`ExecutionPlan` |
| `abi.tools` | `ToolRegistry`、`ToolSkill`、`GenericCommandSkill`、`RunResult` |
| `abi.provenance` | `RunLogger`、`PipelineProgressRecorder`、TSV 写入器 |
| `abi.errors` | `ABIError`、`ConfigError`、`SampleSheetError`、`ToolError` |
| `abi.diagnostics` | `DiagnosticHint`、`classify_exception`、`ERROR_CODES` |
| `abi.json_utils` | `load_json_file`、`load_json_payload` 及其 `ABIJSONError` |
| `abi.interfaces` | `ABIPlugin`、`ABIDryRunPlugin`、`ABIInitializablePlugin` 协议 |
| `abi._shared` | `_read_tsv`、`_display_command`、`_plan_dict`、`_common_overrides` |

## 执行安全

插件应使 `plan` 和 `dry_run` 对 Agent 安全。真实的外部工具执行只能在显式确认后通过 `run` 进行。
