# 开发指南

本仓库发布一个 Python 分发包：`abi-agent`。

## 源代码树

```
src/abi/
  agent/              ABIAgentInterface、JSON 信封、Agent 上下文导出
  figures/            FigureEngine（7 渲染器）、FigureSpec — 通用图表系统
  report/             write_full_report、write_plugin_report、write_methods、
                      citations、limitations、html — 通用报告系统
  workflow/           ResourceManifest、工作流验证、figure_specs 加载
  plugins/            内置分析类型插件
    metagenomic_plasmid/   自包含插件包（引擎在 _engine/ 中，67 工具，84+ 节点）
    rnaseq_expression.py   批量 RNA-seq（6 工具）
    wgs_bacteria.py        细菌 WGS（5 工具）
    amplicon_16s.py        16S 微生物组（8 工具）
    metatranscriptomics.py 宏转录组（4 工具）
  autoplasm/          向后兼容的重导出垫片 → plugins/metagenomic_plasmid/_engine/
  sciplot/            论文级科研图形编译器 — FigureSpec → Validate → Render → Export →
                      Lint → Provenance。Pydantic schema，15 种图表类型，3 套主题，
                      11 条 lint 规则，SHA256 溯源。（v1.4.0）
  dag_planner.py      UniversalDAG — 从 pipeline_dag.yaml 声明式生成执行计划
  tsv_mapping.py      声明式 TSV 列映射器 — YAML 驱动的输出解析，3 种源类型
  _shared.py          共享工具：_read_tsv、_display_command、_plan_dict、_common_overrides
  provenance.py       RunLogger、PipelineProgressRecorder、TSV 溯源写入器
  tools.py            ToolRegistry、ToolSkill、GenericCommandSkill、SafeFormatDict、RunResult
  schemas.py          规范类型：SampleInput、ExecutionPlan、PlanStep、SampleContext
  executor.py         GenericABIExecutor — 步骤迭代、工具调用、合约执行、溯源
  dag.py              DAG 推断引擎 — L1（文献）/ L2（路径）/ L3（验证）
  contracts/          WorkflowSpec、步骤合约执行、校验和链式追踪、断言评估
  permissions.py      read_only / planning_write / execution 级别
  diagnostics.py      错误分类 + DiagnosticHint + classify_exception
  interfaces.py       ABIPlugin、ABIDryRunPlugin、ABIInitializablePlugin 协议
  json_utils.py       带 ABIJSONError 封装的 JSON 文件/负载加载
  timeouts.py         超时解析：parse_timeout_seconds、timeout_from_env_or_value
  resources.py        资源状态检查（磁盘存在性验证）
  tables.py           StandardTableManager
  tool_descriptors.py 统一工具描述符单点真相（3 格式家族、7+ LLM 提供商）
  jobs/               HTTP Job Service（服务端、客户端，force-kill 支持）
  runtimes/           local、Nextflow、HPC 运行时
  exporters/          Nextflow DSL2 导出器
  mcp/                可选 MCP stdio 服务器（通过 ``abi-mcp`` 暴露）
  skills/             Agent 技能文件 → 通过 ``abi install-skills`` 安装
  cli.py              Typer CLI（abi、abi-mcp、autoplasm、abi-sciplot 入口点）
```

`abi.autoplasm` 包是一个向后兼容的重导出垫片，代理到
`abi.plugins.metagenomic_plasmid._engine`。内部代码应从 `abi.plugins.metagenomic_plasmid._engine`
导入质粒引擎，或从 ABI 核心模块导入共享基础设施。

## 公开 SDK

| 模块 | 用途 |
| --- | --- |
| `abi.interfaces` | `ABIPlugin`、`ABIDryRunPlugin`、`ABIInitializablePlugin` 协议类 |
| `abi.schemas` | `SampleInput`、`SampleContext`、`PlanStep`、`ExecutionPlan` |
| `abi.tools` | `ToolRegistry`、`ToolSkill`、`GenericCommandSkill`、`RunResult` |
| `abi.provenance` | `RunLogger`、`PipelineProgressRecorder`、TSV 溯源写入器 |
| `abi.contracts.step_contract` | `ContractViolationError`、`validate_output_contract`、`evaluate_assertions`、校验和链式追踪 |
| `abi.contracts` | `WorkflowSpec`、`WorkflowStepSpec`、`load_workflow_spec` — L1/L2/L3 工作流验证 |
| `abi.dag` | `infer_dag`、`ABIDAG`、`StepBinding` — DAG 推断，支持文献 + 路径 + 验证三层模型 |
| `abi.dag_planner` | `UniversalDAG`、`build_plan_from_dag`、`PathTemplateContext` — 声明式计划生成，所有 5 个插件共用 |
| `abi.tsv_mapping` | `TSVMapper`、`generate_rows` — YAML 驱动 TSV/JSON/日志解析，3 种源类型 |
| `abi.sciplot` | `FigureSpec`、`render_figure`、`validate_spec`、`lint_figure` — 论文级科研图形编译器，15 种图表类型，plotnine+seaborn 后端（v1.4.0） |
| `abi.errors` | `ABIError`、`ConfigError`、`SampleSheetError`、`ToolError` |
| `abi.diagnostics` | 错误分类 + `DiagnosticHint` + `classify_exception` |
| `abi.json_utils` | 带 `ABIJSONError` 的 JSON 文件/负载加载 |
| `abi.timeouts` | `parse_timeout_seconds`、`timeout_from_env_or_value` |
| `abi.tool_descriptors` | `ABI_AGENT_TOOLS`、`TOOL_ALIASES`、`export_openai_compatible`、`export_anthropic`、`export_gemini`、`PROVIDER_PROFILES` |
| `abi.testing` | `assert_plugin_contract` |

## 本地设置

```bash
pip install -e ".[dev]"
```

常用检查：

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short
```

`mypy` 有意限定在 `src/abi/` 范围内；捆绑管线首先由运行时测试和 ruff 覆盖，更严格的类型检查留待后续加固。

## 运行时合约执行

通用执行器强制执行嵌入在每个 `PlanStep.params["_contract"]` 中的步骤级合约。DAG 驱动的规划器从 `pipeline_dag.yaml` 复制此块，因此 DAG 是输出和运行时断言的唯一真相来源。

执行时的合约处理按以下顺序进行：

1. 根据 `provenance/checksums.json` 验证上游输入校验和。
2. 运行外部工具。
3. 当规划路径为抽象路径时，从 `output_dir` 解析实际输出文件。
4. 验证输出合约并记录输出校验和。
5. 根据解析后的输出评估断言。

输出验证支持文件/目录存在性、`min_size`、`extensions`、目录 `contains`、目录/文件 `min_files`、FASTA `min_contigs`、JSON `required_keys` 以及点分 JSON `schema` 约束。

执行器有两个有意的设计细节，应予以保留：

- `output_dir` 本身不会被预创建。某些组装器和工作流工具在其输出目录已存在时会失败。执行器仅创建其父目录和任何不相关的文件输出父目录。
- 实际输出解析是确定性的且能感知双端测序。如果工具写入 `S1_R1.clean.fastq.gz` 和 `S1_R2.clean.fastq.gz`，而计划中包含 `S1.fastp.clean_read1` 等抽象路径，合约检查将使用实际的 R1/R2 文件。

回归测试覆盖位于 `tests/unit/test_executor.py` 和 `tests/unit/test_step_contract.py` 中。

## 运行时资产

小型源资产被跟踪：

- `config/`
- `envs/`
- `skills/`（位于 ``src/abi/skills/`` — 随包捆绑，通过 ``abi install-skills`` 安装）
- `plugins/`
- `examples/`
- `data/examples/`
- `scripts/`

大型或生成的运行时状态被忽略：

- `.mamba/`
- `resources/`
- `results/`
- `log/`
- Nextflow 工作目录

工具执行默认从 `.mamba/envs/<env_name>/bin` 解析环境。可通过 `ABI_MAMBA_ROOT` 覆盖；为兼容性仍接受 `AUTOPLASM_MAMBA_ROOT`。

## Agent 接口

`ABIAgentInterface` 是与传输无关的边界。保持 CLI JSON（``--output-json``）、MCP（``abi-mcp``）、OpenAI 描述符（``abi export-openai-tools``）、技能（``abi install-skills``）、``abi dispatch`` 和 Job Service 行为与之对齐。

执行必须保持门控：`abi run`、`abi_run` 和 Job Service 执行提交应返回 `confirmation_required`，除非显式传入确认。

### 面向 Agent 的命令

| 命令 | 用途 |
|---------|---------|
| `abi list-types --output-json` | 发现已安装插件 |
| `abi query --type <plugin> --what stages` | 轻量级流水线元数据查询（~50ms） |
| `abi export-agent-context --type <plugin>` | 机器可读的操作上下文 |
| `abi doctor-agent --type <plugin>` | 人类可读的操作指南 |
| `abi install-skills` | 将 SKILL.md 文件安装到 `~/.claude/skills/abi/` |
| `abi export-openai-tools --type <plugin>` | OpenAI 函数调用描述符 |
| `abi-mcp` | 启动 MCP stdio 服务器 |

### Python Agent API

```python
import abi
abi.get_agent_guide()          # 返回紧凑操作指南（str）
abi.list_plugins_summary()     # 返回 list[dict]，包含 (analysis_type, name, description)
```
