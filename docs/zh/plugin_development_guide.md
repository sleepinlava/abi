# 插件开发指南

ABI 插件在共享生命周期 API 背后暴露生物学分析类型。

## 推荐的声明式接口

将 `abi-plugin.yaml` 放在插件模块旁边，并继承
`DeclarativeABIPlugin`。基类会从 manifest 读取插件身份、工具注册表和
标准表路径，因此这些信息只需声明一次：

```python
from abi.plugin import DeclarativeABIPlugin


class MyPlugin(DeclarativeABIPlugin):
    def load_config(self, config_path=None, **kwargs): ...
    def build_plan(self, config, *, check_files=True): ...
    def parse_outputs(self, tool_id, output_dir, sample_id): ...
    def write_report(self, plan, result_dir): ...
```

如果 monorepo 将声明文件与 Python 模块分开存放，只需设置一个类属性，
例如 `plugin_root = Path("plugins/my_analysis")`。

基类会在导入时校验 manifest 及其声明的所有路径。插件发现还会强制
entry-point 名称、manifest 中的 `plugin_id` 与 `entry_point` 一致。运行时
注册表、工具合约和环境校验保持不变；发布前运行
`abi contract-lint --strict`。

## 底层 Python 接口

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

entry-point 的键必须与 `abi-plugin.yaml` 中的 `plugin_id` 完全一致。

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
- `execution.executable`
- `execution.command_template`
- 声明的输入/输出模板字段
- 标准化的标准表名称

环境名称不存储在单独的合约或注册表中。它们集中在 `environments.yaml` 中的
`tool_assignments:` 下（每个插件一个映射），由 `ToolRegistry` 在运行时注入正确的
`env_name`。参见：`environments.yaml`、`scripts/emit_env_yamls.py`。

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

检查项必须嵌套在输出的 `contract` 键下；将 `min_size` 等检查与 `type`
并列是无效声明，运行时不会执行：

```yaml
outputs:
  clean_read1:
    type: file
    format: fastq.gz
    path: "{outdir}/{sample_id}.clean.fastq.gz"
    contract:
      min_size: "1KB"
      extensions: [".fastq.gz"]
```

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

## 发布输出

插件可以实现 `published_outputs(plan)`，将插件特有的最终产物加入传输无关的
`RuntimeResult.outputs` 映射。只应返回稳定且已经存在的路径，并使用不会与 ABI
公共结果键冲突的标签。该钩子适合暴露带版本的产物清单等最终结果；中间文件仍
通过执行计划发现，不应逐个发布。

如果一个预设会生成多个最终报告，应发布带分支限定的标签；只有在恰好存在一套完整
报告时才添加通用别名。例如，EasyMetagenome 单分支运行发布 `report_manifest`，组合
预设则发布 `taxonomy_report_manifest` 和 `functional_report_manifest`。带版本的清单
应标明工作流，并关联其汇总的标准表和报告。

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
| `abi.interfaces` | `ABIPlugin`、`ABIDryRunPlugin`、`ABIInitializablePlugin`、`ABIPublishedOutputsPlugin` 协议 |
| `abi.plugin` | `DeclarativeABIPlugin` — 由 manifest 提供身份、注册表和标准表 schema |
| `abi._shared` | `_read_tsv`、`_display_command`、`_plan_dict`、`_common_overrides` |
| `abi.dag_planner` | `UniversalDAG`、`build_plan_from_dag`、`PathTemplateContext` — DAG 驱动的 `build_plan()`（2026-06-18 新增） |
| `abi.tsv_mapping` | `TSVMapper`、`generate_rows` — 声明式 TSV 列映射（2026-06-18 新增） |
| `abi.sciplot` | `FigureSpec`、`render_figure`、`validate_spec`、`lint_figure` — 论文级科研图形编译器。15 种图表类型（含 PCoA、火山图、堆叠柱状图、系统发育热图），plotnine+seaborn 后端。（v1.4.0，2026-06-20 新增） |
| `abi.contracts` | `WorkflowSpec`、`WorkflowStepSpec`、`load_workflow_spec`、`run_contract_lint` — L1/L2/L3 工作流声明与验证 |
| `abi.report` | `write_plugin_report`、`render_figures_via_sciplot` — 报告生成与图表渲染 |

## DAG 驱动的计划构建

与其手写遍历样本、构造 `PlanStep` 对象的 `build_plan()`（约 200 行样板代码），插件必须在 `pipeline_dag.yaml` 文件中声明工作流，并使用通用 DAG 规划器：

```python
# 在插件的 build_plan() 中：
def build_plan(self, config, *, check_files=True):
    context = self.build_sample_context(config, check_files=check_files)
    from abi.dag_planner import build_plan_from_dag
    return build_plan_from_dag(
        self.root / "pipeline_dag.yaml", config, context
    )
```

### `pipeline_dag.yaml` 结构

```yaml
pipeline_id: my_analysis
platforms: [illumina]

# 类别 → 子目录映射
category_dirs:
  qc: 01_qc
  alignment: 02_alignment

nodes:
  qc_fastp:
    tool_id: fastp
    category: qc
    scope: per_sample        # per_sample（默认）或 cross_sample
    depends_on: []
    inputs:
      read1: {type: file, source: sample_sheet}
      read2: {type: file, source: sample_sheet}
    outputs:
      clean_read1:
        type: file
        path: "{outdir}/{category_dir}/{sample_id}/{sample_id}_R1.clean.fastq.gz"
      output_dir:
        type: directory
        path: "{outdir}/{category_dir}/{sample_id}"

  aggregation_step:
    tool_id: my_aggregator
    scope: cross_sample      # 运行一次，收集所有 per-sample 输出
    depends_on: [qc_fastp]
    inputs:
      per_sample_data: {aggregate: per_sample_outputs}
```

### 声明式 TSV 解析

对于输出简单 TSV/JSON/日志的工具，在 `parsers.yaml` 中声明列映射，代替手写 Python 解析器函数。支持三种源类型：

| 源类型 | 用途 | 示例工具 |
|---|---|---|
| `tsv_mapping` | CSV/TSV 列重映射 | AMRFinderPlus、featureCounts |
| `json_mapping` | 嵌套 JSON 展平 | fastp（summary before/after 块） |
| `key_value_log` | 分隔符日志解析 | STAR（Log.final.out 管道分隔） |

`tsv_mapping` 示例：

```yaml
parsers:
  my_tool:
    source:
      type: tsv_mapping
      pattern: "*.tsv"
      delimiter: "\t"
    target_table: my_standard_table
    columns:
      gene_name: {sources: [Gene, gene_name], default: ""}
      coverage:  {sources: [Coverage, cov_pct], default: "0"}
    constants:
      tool: my_tool
```

在 `parse_outputs()` 中接入：

```python
def parse_outputs(self, tool_id, output_dir, sample_id):
    if self._tsv_mapper.has_parser(tool_id):
        rows = self._tsv_mapper.parse(tool_id, output_dir, sample_id=sample_id)
        if rows:
            return {self._tsv_mapper.get_target_table(tool_id): rows}
    # 复杂解析器保留为 Python
    ...
```

## 测试插件

每个插件必须包含测试。新插件的最小测试套件覆盖三个方面：合约合规、注册表加载和计划生成。

### 最小测试文件 (`tests/test_my_plugin.py`)

```python
import pytest
from abi.testing import assert_plugin_contract
from your_package.plugin import MyPlugin  # 你的已安装插件入口点


def test_plugin_contract():
    """插件满足 ABIPlugin 协议。"""
    plugin = MyPlugin()
    assert_plugin_contract(plugin)


def test_registry_loads():
    """工具注册表 YAML 解析无错误。"""
    plugin = MyPlugin()
    registry = plugin.registry()
    tools = registry.list_tools()
    assert len(tools) > 0
    # 验证预期工具已注册
    tool_ids = [t["id"] for t in tools]
    assert "fastp" in tool_ids


def test_build_plan(mock_sample_context, tmp_path):
    """build_plan() 对默认配置返回有效的 ExecutionPlan。"""
    plugin = MyPlugin()
    config = plugin.load_config()
    config["outdir"] = str(tmp_path)
    plan = plugin.build_plan(config)
    assert len(plan.steps) > 0
    # QC 步骤始终最先
    assert plan.steps[0].step_id.startswith("qc_")


def test_parse_outputs_handles_missing_files(tmp_path):
    """解析器对缺失文件返回空结果（而非错误）。"""
    plugin = MyPlugin()
    result = plugin.parse_outputs("fastp", tmp_path, "S1")
    assert isinstance(result, dict)


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_real_execution_smoke(tmp_path):
    """使用合成数据执行完整管线。"""
    # 生成最小测试数据，运行真实工具，验证输出……
    pass
```

### 插件测试可用的 Fixtures

`tests/conftest.py` 中的所有 fixtures 无需导入即可使用：

| Fixture | 类型 | 用途 |
|---------|------|------|
| `mock_sample` | `ABISample` | 带有 illumina 平台的单样本输入 |
| `mock_sample_context` | `ABISampleContext` | 包含两个分组的单样本上下文 |
| `mock_contract_dict` | `dict` | 用于脚手架的最小有效工具合约 |
| `tmp_project` | `Path` | 包含 results/logs/provenance/tables/ 的临时目录 |

### 基准测试

对于数值级验证，使用 `run_benchmark()`：

```python
from abi.testing.benchmark import run_benchmark

@pytest.mark.smoke
@pytest.mark.requires_tools
def test_my_plugin_benchmark(tmp_path):
    result = run_benchmark(
        plugin_id="my_analysis",
        dataset_path=Path("data/benchmarks/my_analysis"),
        outdir=tmp_path / "results",
    )
    assert result.total > 0
    assert result.passed >= result.total * 0.7  # 开发阶段阈值
```

参见 `docs/zh/testing.md` 获取完整测试指南。

## 资源管理

ABI 为生物信息学数据库提供资源发现和自动安装系统。插件作者声明资源需求；ABI 负责检查、下载和安装后钩子。

### 声明资源

资源在 `plugins/<name>/abi-plugin.yaml` 中声明：

```yaml
resources:
  my_database:
    name: "My Database"
    description: "MyTool 的参考数据库"
    url: "https://example.com/my_database.tar.gz"
    size_gb: 2.5
    required_by: [my_tool]
    install_post: "makeblastdb -in {resource_dir}/sequences.fasta -dbtype nucl"
    env_name: my_env
```

### ResourceSpec 字段

| 字段 | 类型 | 描述 |
|------|------|------|
| `name` | `str` | 人类可读的名称 |
| `description` | `str` | 资源提供的内容 |
| `url` | `str` | 下载 URL（支持 http/https/S3） |
| `size_gb` | `float` | 大约下载大小 |
| `required_by` | `list[str]` | 依赖此资源的工具 ID |
| `install_post` | `str` 或 `None` | 下载后运行的 shell 命令（如 `makeblastdb`） |
| `env_name` | `str` | 提供安装后工具的 conda 环境 |

### CLI 命令

```bash
# 检查哪些资源可用/缺失
abi check-resources --type my_analysis

# 下载并安装缺失的资源（需要确认）
abi setup-resources --type my_analysis --confirm
```

### 环境解析

工具 → 环境分配在 `environments.yaml` 中，而非在单个工具合约中。注册工具时，将其环境分配添加到 `environments.yaml`：

```yaml
tool_assignments:
  my_analysis:
    my_tool: my_env
```

`ToolRegistry` 在运行时注入正确的 `env_name`。运行 `scripts/emit_env_yamls.py` 重新生成每个环境的 `envs/*.yml` 文件。

## 断言表达式参考

步骤合约支持以简单表达式语言编写的断言。断言在工具执行后根据解析后的输出进行评估。

### 变量

| 变量 | 类型 | 示例 |
|------|------|------|
| `output_json.<key>` | Any | `output_json.summary.after_filtering.total_reads` |
| `output_files.<name>` | Path | `output_files.clean_read1` |
| `output_dir` | Path | `output_dir` |
| `return_code` | int | `return_code` |

### 运算符

| 运算符 | 示例 | 含义 |
|--------|------|------|
| `>` | `output_json.total > 0` | 大于 |
| `>=` | `output_json.qual >= 30` | 大于等于 |
| `<` | `output_json.errors < 10` | 小于 |
| `<=` | `return_code <= 0` | 小于等于 |
| `==` | `output_json.status == "complete"` | 等于 |
| `!=` | `return_code != 1` | 不等于 |
| `exists` | `output_files.clean_read1 exists` | 文件/目录存在 |
| `contains` | `output_json.log contains "done"` | 字符串包含 |

### 在 pipeline_dag.yaml 中编写断言

```yaml
nodes:
  qc_fastp:
    tool_id: fastp
    # ...
    assertions:
      - "output_json.summary.after_filtering.total_reads > 0"
      - "output_json.summary.after_filtering.q30_rate >= 0.8"
      - "output_files.clean_read1 exists"
      - "output_files.clean_read2 exists"
      - "return_code == 0"
```

### 断言评估

断言在输出验证之后进行评估。如果任何断言失败，步骤将被标记为失败，并抛出包含失败断言详情的 `ContractViolationError`。所有断言必须通过步骤才能成功。

## 执行安全

插件应使 `plan` 和 `dry_run` 对 Agent 安全。真实的外部工具执行只能在显式确认后通过 `run` 进行。
