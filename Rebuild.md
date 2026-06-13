# ABI 最终开发计划书

## 1. 项目名称

**ABI：Agent-Bioinformatics Interface**

全称：**Agent-Bioinformatics Interface**

定位：**面向 Agent 的生物信息学分析生命周期控制接口**

---

## 2. 最终结论

### 2.1 核心开发路线

**ABI 最终不能只做成一个 Python 库，也不能只做成某个平台专属的 Agent 工具。**

最终产品形态必须是：

```text
中厚 ABI Core
  + Agent-facing Tool Layer
  + Plugin SDK
  + Job Service
  + PyPI 分发
```

即：

```text
Python Library 是实现底座
Agent Tool Layer 是主要交互界面
Plugin SDK 是扩展机制
Job Service 是长任务执行机制
PyPI 是分发方式
```

### 2.2 架构总原则

```text
Core 要厚
Transport 要薄
Plugin 要清
Agent 不直接写底层代码
```

解释：

1. **Core 要厚**：承载生命周期、权限、诊断、provenance、standard tables、plugin discovery。
2. **Transport 要薄**：CLI、OpenAI tools、MCP、HTTP 只做调用适配。
3. **Plugin 要清**：生物学逻辑在插件，通用机制在 Core。
4. **Agent 不写代码**：Agent 通过 schema、descriptor、JSON envelope 和 diagnostic hints 调用 ABI。

---

## 3. 项目目标

### 3.1 总目标

将 **AutoPlasm** 从一个宏基因组质粒分析 CLI，重构为 **ABI** 体系下的第一个复杂插件 **`metagenomic_plasmid`**。

同时实现第二个轻量可移植性插件 **`metatranscriptomics`**，证明同一个 **ABI Core** 能驱动不同生信分析类型。

最终证明：

```text
ABI 不是 AutoPlasm 的附属接口
AutoPlasm 只是 ABI 的第一个复杂插件
ABI 是可扩展、可审计、可诊断、可被 Agent 调用的生信控制层
```

### 3.2 工程目标

1. 建立稳定的 **ABI Core API**。
2. 建立统一的 **ABIAgentInterface**。
3. 支持 **CLI JSON** 作为短期主调用路径。
4. 支持 **OpenAI-compatible tool descriptors**。
5. 支持 **optional MCP stdio transport**。
6. 支持 **HTTP Job Service**。
7. 将 **AutoPlasm** 插件化为 **`metagenomic_plasmid`**。
8. 实现第二插件 **`metatranscriptomics`**。
9. 建立 **tool contract schema**。
10. 建立 **standard table schema**。
11. 建立 **provenance artifact schema**。
12. 建立 **error taxonomy** 和 **diagnostic hints**。
13. 发布 **PyPI 包**。
14. 形成可复现实验 artifact。
15. 设计 **LLM 未训练场景对照实验**。

### 3.3 研究目标

验证以下假设：

> **未专门训练过 ABI 的通用 Agent，在看到 ABI 的 tool schema、lifecycle API、dry-run、inspect、provenance 和 diagnostic hints 后，是否比只读 README、普通 API 或普通 tool calling 更可靠地完成生信分析规划、预演、诊断和恢复。**

---

## 4. 非目标

### 4.1 短期不做的事情

1. 不做完整自然语言 **ABI Agent 平台**。
2. 不训练专属大模型。
3. 不做完整网页实验室平台。
4. 不把大型数据库打包进 PyPI。
5. 不把 conda / mamba 环境目录打包进 PyPI。
6. 不用工具数量作为核心创新点。
7. 不宣称 ABI 替代 **Nextflow / nf-core / Galaxy / CWL / Snakemake**。
8. 不宣称 ABI 覆盖所有生信分析。
9. 不让 Agent 主路径依赖直接 import Python 库。
10. 不让 `run` 默认自动执行真实生信任务。

### 4.2 后期才考虑的事情

1. 多用户 Web 平台。
2. LIMS / 医院系统 / 实验室系统集成。
3. 组织级权限、审批和审计。
4. 可视化 dashboard 产品化。
5. 云端多租户运行平台。
6. 资源配额和团队任务管理。
7. 专属 Agent UI。

---

## 5. 总体架构

### 5.1 架构图

```text
General Agent Platforms
  Codex / ChatGPT / Claude / Cursor / CI / Shell Agent
        |
        v
Transport Layer
  CLI JSON
  OpenAI-compatible Tools
  Optional MCP stdio
  HTTP Job API
        |
        v
ABIAgentInterface
  list_types / plan / dry_run / inspect / report / run / export_nextflow / dispatch
        |
        v
ABI Core
  plugin discovery
  schema validation
  execution plan
  permission model
  provenance manager
  standard table manager
  diagnostics
  generic executor
  report writer
        |
        v
ABI Plugins
  metagenomic_plasmid
  metatranscriptomics
  future nf-core adapters
        |
        v
Runtime Backends
  local
  Nextflow
  HPC
  cloud
```

### 5.2 分层职责

| 层级     | 名称                    | 职责                                                              | 不负责      |
| ------ | --------------------- | --------------------------------------------------------------- | -------- |
| **L1** | **Agent Platform**    | 自然语言理解、任务拆解、工具调用                                                | 生物学执行逻辑  |
| **L2** | **Transport Layer**   | CLI / MCP / OpenAI / HTTP 适配                                    | 业务逻辑     |
| **L3** | **ABIAgentInterface** | 统一生命周期 API、参数、JSON envelope、确认语义                                | 具体工具选择   |
| **L4** | **ABI Core**          | 插件发现、schema、plan、dry-run、provenance、standard tables、diagnostics | 具体生物学解释  |
| **L5** | **ABI Plugin**        | 样本表解释、路线规划、工具选择、输出解析、报告解释                                       | 通用执行机制   |
| **L6** | **Runtime Backend**   | local / Nextflow / HPC / cloud 执行                               | Agent 交互 |

---

## 6. API 形态设计

### 6.1 最终 API 类型

ABI 必须同时提供两类接口：

1. **Developer API**

   * 给人类开发者、插件作者、测试代码使用。
   * 形式是 Python Library。
   * 允许 import。

2. **Agent Tool API**

   * 给 Agent 平台使用。
   * 形式是 CLI JSON、OpenAI tools、MCP、HTTP Job API。
   * Agent 不需要知道 Python 内部类名。

### 6.2 Developer API

核心类：

```python
class ABIAgentInterface:
    def list_types(self): ...
    def plan(self, analysis_type, config_path=None, sample_sheet=None, outdir=None, log_dir=None, **kwargs): ...
    def dry_run(self, analysis_type, config_path=None, sample_sheet=None, outdir=None, log_dir=None, **kwargs): ...
    def inspect(self, result_dir): ...
    def report(self, result_dir, analysis_type=None): ...
    def run(self, analysis_type, config_path=None, sample_sheet=None, outdir=None, log_dir=None, confirm_execution=False, **kwargs): ...
    def export_nextflow(self, analysis_type, config_path=None, sample_sheet=None, outdir=None, **kwargs): ...
    def dispatch(self, tool_name, arguments): ...
```

### 6.3 Agent Tool API

Agent 主路径不应该是：

```python
from abi import ...
```

Agent 主路径应该是：

```bash
abi plan --type metagenomic_plasmid --output-json
```

或者：

```json
{
  "tool": "abi_plan",
  "arguments": {
    "analysis_type": "metagenomic_plasmid",
    "config_path": "config.yaml",
    "sample_sheet": "samples.tsv",
    "outdir": "results/demo"
  }
}
```

### 6.4 统一 JSON Envelope

所有入口必须返回统一结构。

成功：

```json
{
  "status": "success",
  "command": "plan",
  "result": {
    "analysis_type": "metagenomic_plasmid",
    "plan_path": "results/demo/execution_plan.json",
    "steps": 14
  }
}
```

需要确认：

```json
{
  "status": "confirmation_required",
  "command": "run",
  "result": {
    "analysis_type": "metagenomic_plasmid",
    "engine": "local",
    "message": "Re-run with confirm_execution=true after user approval."
  }
}
```

错误：

```json
{
  "status": "error",
  "command": "dry_run",
  "error_code": "missing_input",
  "error": "Input file does not exist.",
  "diagnostic_hints": [
    {
      "severity": "error",
      "code": "missing_input",
      "artifact": "sample_sheet.tsv",
      "field": "read1",
      "message": "Sample S1 read1 path does not exist.",
      "suggested_next_action": "Fix the read1 path in the sample sheet."
    }
  ]
}
```

---

## 7. 权限模型

### 7.1 权限等级

| 权限                 | 操作                                             | 是否默认暴露给 Agent | 是否写文件 | 是否执行真实工具 |
| ------------------ | ---------------------------------------------- | ------------: | ----: | -------: |
| **read_only**      | `list_types`, `inspect`, `validate_result`     |             是 |     否 |        否 |
| **planning_write** | `plan`, `dry_run`, `report`, `export_nextflow` |             是 |     是 |        否 |
| **execution**      | `run`                                          |             否 |     是 |        是 |

### 7.2 规则

1. **`run` 默认不执行真实任务**。
2. **`run` 必须带 `confirm_execution=true` 才能执行**。
3. **OpenAI-compatible descriptors 默认不导出 `abi_run`**。
4. **只有显式 `--include-execution` 才导出 `abi_run`**。
5. **Job API 中未确认的 execution job 不能入队**。
6. **所有 execution 操作必须写入 provenance**。
7. **所有 planning_write 操作必须在结果中声明写了哪些文件**。

---

## 8. 插件系统设计

### 8.1 插件接口

每个插件必须实现：

```python
class ABIPlugin:
    plugin_id: str
    display_name: str
    description: str
    report_title: str

    def load_config(self, config_path=None, profile=None, overrides=None): ...
    def build_plan(self, config, check_files=True): ...
    def registry(self): ...
    def table_schemas(self): ...
    def parse_outputs(self, tool_id, output_dir, sample_id): ...
    def write_report(self, plan, result_dir): ...
```

### 8.2 插件发现

使用 Python entry points：

```toml
[project.entry-points."abi.plugins"]
metagenomic_plasmid = "abi.plugins.metagenomic_plasmid:MetagenomicPlasmidPlugin"
metatranscriptomics = "abi.plugins.metatranscriptomics:MetatranscriptomicsPlugin"
```

### 8.3 插件目录结构

```text
plugins/metagenomic_plasmid/
  abi-plugin.yaml
  tool_registry.yaml
  standard_tables.yaml
  tool_contracts/
    fastp.yaml
    genomad.yaml
    bakta.yaml
  skills/
    fastp/SKILL.md
    genomad/SKILL.md
    bakta/SKILL.md
  parsers/
    genomad.py
    bakta.py
  tests/
    fixtures/
    test_contract.py
```

### 8.4 插件类型

| 插件类型                          | 用途                       | 示例                    |
| ----------------------------- | ------------------------ | --------------------- |
| **Adapter Plugin**            | 接入已有系统                   | `metagenomic_plasmid` |
| **Standalone Plugin**         | 从零实现新分析类型                | `metatranscriptomics` |
| **External Pipeline Adapter** | 包裹外部 pipeline            | `nfcore_mag`          |
| **Exporter-backed Plugin**    | 导出为 Nextflow / Snakemake | 后续                    |

---

## 9. 两个核心插件

### 9.1 `metagenomic_plasmid`

#### 目标

将 **AutoPlasm** 插件化为 **ABI** 的复杂主案例。

#### 职责

1. 复用 AutoPlasm 的 planner。
2. 复用 AutoPlasm 的 executor 或逐步迁移到 ABI generic executor。
3. 复用 AutoPlasm 的 tool registry。
4. 复用 AutoPlasm 的 standard tables。
5. 复用 AutoPlasm 的 parser。
6. 复用 AutoPlasm 的 report。
7. 暴露为 `analysis_type="metagenomic_plasmid"`。

#### 验收命令

```bash
abi list-types --output-json

abi plan \
  --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --outdir results/plasmid_demo \
  --output-json

abi dry-run \
  --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --outdir results/plasmid_demo \
  --output-json

abi inspect \
  --result-dir results/plasmid_demo \
  --output-json

abi report \
  --type metagenomic_plasmid \
  --result-dir results/plasmid_demo \
  --output-json
```

### 9.2 `metatranscriptomics`

#### 目标

作为可移植性 demo，证明 ABI 不是质粒专用。

#### 最小工具链

```text
fastp
  ↓
STAR 或 HISAT2
  ↓
featureCounts
```

#### 标准表

```text
gene_expression.tsv
```

#### 验收命令

```bash
abi plan \
  --type metatranscriptomics \
  --outdir results/rnaseq_demo \
  --output-json

abi dry-run \
  --type metatranscriptomics \
  --outdir results/rnaseq_demo \
  --output-json

abi inspect \
  --result-dir results/rnaseq_demo \
  --output-json

abi report \
  --type metatranscriptomics \
  --result-dir results/rnaseq_demo \
  --output-json
```

---

## 10. ABI Core 模块拆分

### 10.1 推荐源码结构

```text
src/abi/
  __init__.py

  agent/
    interface.py
    envelopes.py
    dispatch.py

  plugins/
    __init__.py
    discovery.py
    contracts.py
    metagenomic_plasmid.py
    metatranscriptomics.py

  schemas.py
  config.py
  plan.py
  executor.py
  diagnostics.py
  permissions.py
  provenance.py
  tables.py
  report.py

  transports/
    cli_json.py
    openai_tools.py
    mcp_server.py
    http_jobs.py

  jobs/
    service.py
    client.py
    store.py

  runtimes/
    local.py
    nextflow.py
    hpc.py
    cloud.py

  exporters/
    nextflow.py

  contracts/
    plugin_manifest.py
    tool_contract.py
    standard_table.py

  cli.py
```

### 10.2 模块职责

| 模块                             | 职责                                             |
| ------------------------------ | ---------------------------------------------- |
| **agent/interface.py**         | `ABIAgentInterface` 主入口                        |
| **agent/envelopes.py**         | 统一 JSON envelope                               |
| **plugins/discovery.py**       | entry point 插件发现                               |
| **schemas.py**                 | `ABIExecutionPlan`, `ABIPlanStep`, `ABISample` |
| **executor.py**                | generic executor                               |
| **diagnostics.py**             | 错误分类和恢复建议                                      |
| **permissions.py**             | read_only / planning_write / execution         |
| **provenance.py**              | commands.tsv、resolved_inputs.tsv、logs          |
| **tables.py**                  | standard table 创建与写入                           |
| **report.py**                  | generic report                                 |
| **transports/openai_tools.py** | OpenAI-compatible descriptors                  |
| **jobs/service.py**            | HTTP Job Service                               |
| **runtimes/nextflow.py**       | Nextflow backend                               |
| **exporters/nextflow.py**      | ABI plan 到 Nextflow DSL2 导出                    |

---

## 11. Tool Contract 设计

### 11.1 目标

将原来的 **SKILL.md** 从人类可读文档，升级为 **机器可校验 tool contract**。

### 11.2 文件示例

```yaml
abi_version: "0.1"
tool_id: "fastp"
name: "fastp"
category: "qc"
purpose: "Trim and quality-control paired-end reads."

when_to_use:
  - paired_end_reads
  - quality_control_required

inputs:
  read1:
    type: file
    formats: ["fastq", "fastq.gz"]
    required: true
  read2:
    type: file
    formats: ["fastq", "fastq.gz"]
    required: true
  threads:
    type: integer
    minimum: 1
    default: 4

outputs:
  clean_read1:
    type: file
    format: fastq.gz
  clean_read2:
    type: file
    format: fastq.gz
  html_report:
    type: file
    format: html
  json_report:
    type: file
    format: json

execution:
  env_name: abi-qc
  executable: fastp
  command_template: >
    fastp -i {read1} -I {read2}
    -o {clean_read1} -O {clean_read2}
    --thread {threads}
    --html {html_report}
    --json {json_report}
  network: false
  writes_output: true

normalization:
  parser: "plugin.parsers.fastp:parse_fastp"
  tables:
    - qc_summary

failure_handling:
  missing_input:
    hint: "Check sample sheet read1/read2 paths."
  tool_not_found:
    hint: "Install fastp in the abi-qc environment."
  nonzero_exit:
    hint: "Read provenance/step_logs/{step_id}.stderr.log."
```

### 11.3 验收标准

1. 所有核心工具有 `tool_contracts/*.yaml`。
2. 所有 contract 可通过 JSON Schema 校验。
3. `tool_registry.yaml` 与 `tool_contracts/*.yaml` 一致。
4. `SKILL.md` 保留为人类说明，但不作为 Agent 主接口。
5. `assert_plugin_contract()` 能检查插件合规性。

---

## 12. Standard Tables 设计

### 12.1 目标

让 Agent 不直接解析工具原始输出，而是读取稳定的标准表。

### 12.2 规则

1. 每个插件必须声明 `standard_tables.yaml`。
2. 表格统一使用 TSV。
3. 表头必须稳定。
4. 空表也要保留表头。
5. parser 只能写已声明表。
6. 每行建议保留 `tool` 和 `source_file`。
7. 不允许 parser 随意创建未知表。

### 12.3 示例

```yaml
abi_version: "0.1"
tables:
  gene_expression:
    description: "Gene-level expression table."
    primary_key: ["sample_id", "gene_id"]
    columns:
      sample_id:
        type: string
        required: true
      gene_id:
        type: string
        required: true
      count:
        type: number
        required: false
      tpm:
        type: number
        required: false
      tool:
        type: string
        required: true
      source_file:
        type: path
        required: false
```

---

## 13. Provenance 设计

### 13.1 目标

所有 plan、dry-run、run 都要生成可审计 artifact。

### 13.2 标准输出结构

```text
outdir/
  execution_plan.json
  provenance/
    config.resolved.yaml
    commands.tsv
    resolved_inputs.tsv
    tool_versions.tsv
    resources.json
    environment.yml
    run_summary.json
    progress.json
    progress.jsonl
    step_logs/
      {step_id}.stdout.log
      {step_id}.stderr.log
  tables/
    *.tsv
  report/
    report.md
    report.html
```

### 13.3 `commands.tsv` 必需列

| 列                 | 含义                                       |
| ----------------- | ---------------------------------------- |
| `step_id`         | 步骤 ID                                    |
| `sample_id`       | 样本 ID                                    |
| `step_name`       | 生物学步骤名                                   |
| `tool_id`         | 工具 ID                                    |
| `category`        | 工具类别                                     |
| `command`         | 渲染后的命令                                   |
| `status`          | dry_run / success / failed / skipped     |
| `return_code`     | 外部工具返回码                                  |
| `reason`          | 跳过或失败原因                                  |
| `parsed_status`   | parsed / no_standard_rows / parse_failed |
| `standard_tables` | 写入的标准表                                   |

---

## 14. Error Taxonomy 与 Diagnostic Hints

### 14.1 标准错误码

```text
unknown_analysis_type
invalid_config
invalid_sample_sheet
missing_input
missing_resource
missing_database
tool_not_found
permission_required
runtime_not_supported
nonzero_exit
parse_failed
empty_result
artifact_missing
internal_error
```

### 14.2 每个错误必须包含

```json
{
  "status": "error",
  "command": "dry_run",
  "error_code": "missing_input",
  "error": "Input file does not exist.",
  "diagnostic_hints": [
    {
      "severity": "error",
      "code": "missing_input",
      "artifact": "sample_sheet.tsv",
      "field": "read1",
      "message": "Sample S1 read1 path does not exist.",
      "suggested_next_action": "Fix sample_sheet.tsv read1 path."
    }
  ]
}
```

### 14.3 诊断目标

1. Agent 能判断失败类别。
2. Agent 能找到相关 artifact。
3. Agent 能提出正确下一步。
4. 用户能复查失败原因。
5. CI 能自动判断错误是否符合预期。

---

## 15. Agent Tool Layer

### 15.1 CLI JSON

短期主路径：

```bash
abi list-types --output-json
abi plan --type metagenomic_plasmid --output-json
abi dry-run --type metagenomic_plasmid --output-json
abi inspect --result-dir results/demo --output-json
abi report --type metagenomic_plasmid --result-dir results/demo --output-json
abi run --type metagenomic_plasmid --output-json
abi run --type metagenomic_plasmid --confirm-execution --output-json
```

### 15.2 OpenAI-compatible Tool Export

命令：

```bash
abi export-openai-tools \
  --type metagenomic_plasmid \
  --format responses

abi export-openai-tools \
  --type metagenomic_plasmid \
  --format apps-sdk

abi export-openai-tools \
  --type metagenomic_plasmid \
  --format json
```

默认导出：

```text
abi_list_types
abi_plan
abi_dry_run
abi_inspect
abi_report
abi_export_nextflow
```

默认不导出：

```text
abi_run
```

显式导出 execution：

```bash
abi export-openai-tools \
  --type metagenomic_plasmid \
  --format json \
  --include-execution
```

### 15.3 MCP

原则：

1. MCP 是 optional transport。
2. MCP SDK 不进入 Python 3.9 主依赖。
3. MCP server 暴露同一套 `ABIAgentInterface`。
4. MCP 不承载业务逻辑。

### 15.4 HTTP Job API

用于长任务：

```text
POST /jobs
GET /jobs
GET /jobs/{id}
GET /jobs/{id}/artifacts
POST /jobs/{id}/cancel
```

Job 状态：

```text
queued
running
succeeded
failed
cancel_requested
cancelled
```

### 15.5 Agent Context Export

新增命令：

```bash
abi export-agent-context \
  --type metagenomic_plasmid \
  --format json
```

输出内容：

```json
{
  "analysis_type": "metagenomic_plasmid",
  "safe_sequence": [
    "list_types",
    "plan",
    "dry_run",
    "inspect",
    "report",
    "run"
  ],
  "execution_requires_confirmation": true,
  "standard_tables": [
    "plasmid_predictions",
    "plasmid_consensus",
    "annotations",
    "abundance"
  ],
  "important_artifacts": [
    "execution_plan.json",
    "provenance/commands.tsv",
    "provenance/resolved_inputs.tsv",
    "tables/*.tsv",
    "report/report.html"
  ]
}
```

### 15.6 Doctor Agent

新增命令：

```bash
abi doctor-agent --type metagenomic_plasmid
```

作用：

1. 输出给 Agent 的最短操作规范。
2. 列出安全调用顺序。
3. 列出禁止行为。
4. 列出常见错误恢复方式。
5. 不替代 README。

---

## 16. Job Service 设计

### 16.1 目标

让长任务不占用交互式 Agent 会话。

### 16.2 基础功能

1. 本地 HTTP service。
2. 内存队列。
3. 后台 worker。
4. Job status 查询。
5. Artifact 查询。
6. Cancel 请求。
7. local backend。
8. Nextflow backend。
9. HPC / cloud 参数透传。

### 16.3 后续 hardening

1. 持久化 job store。
2. 运行中任务强制终止。
3. 远程 HPC scheduler job id 跟踪。
4. cloud runner provider adapter。
5. 鉴权。
6. 多用户隔离。
7. 审计日志。

---

## 17. PyPI 分发策略

### 17.1 包名建议

不建议使用：

```text
abi
```

推荐使用：

```text
autoplasm-abi
```

### 17.2 安装方式

```bash
pip install autoplasm-abi
```

### 17.3 包含内容

| 内容                              |      是否进入 PyPI | 说明         |
| ------------------------------- | -------------: | ---------- |
| **ABI Core**                    |              是 | 主体         |
| **ABIAgentInterface**           |              是 | Agent 工具边界 |
| **CLI JSON**                    |              是 | 短期主路径      |
| **Plugin SDK**                  |              是 | 第三方扩展      |
| **OpenAI descriptors exporter** |              是 | Agent 平台适配 |
| **MCP server**                  | optional extra | 避免污染主依赖    |
| **HTTP Job Service**            |              是 | 长任务接口      |
| **两个 demo 插件**                  |              是 | 证明可移植性     |
| **大型数据库**                       |              否 | 由资源管理器处理   |
| **完整 mamba 环境**                 |              否 | 由环境定义文件处理  |

### 17.4 `pyproject.toml` 关键配置

```toml
[project]
name = "autoplasm-abi"
version = "0.1.0a1"
requires-python = ">=3.9,<3.13"

[project.scripts]
abi = "abi.cli:main"

[project.optional-dependencies]
mcp = [
  "mcp; python_version >= '3.10'"
]
dev = [
  "pytest",
  "ruff",
  "black",
  "mypy",
  "build",
  "twine"
]

[project.entry-points."abi.plugins"]
metagenomic_plasmid = "abi.plugins.metagenomic_plasmid:MetagenomicPlasmidPlugin"
metatranscriptomics = "abi.plugins.metatranscriptomics:MetatranscriptomicsPlugin"
```

---

## 18. 资源管理策略

### 18.1 原则

PyPI 只发代码，不发大型资源。

### 18.2 不进入 PyPI 的内容

1. geNomad database。
2. Bakta database。
3. MOB-suite database。
4. PlasmidFinder database。
5. Kraken2 database。
6. MetaPhlAn database。
7. 大型 FASTQ / FASTA / BAM。
8. mamba 环境目录。

### 18.3 推荐方式

1. `resources.yaml` 声明资源。
2. `abi check-resources` 检查资源。
3. `abi setup-resources --dry-run` 展示下载计划。
4. `abi setup-resources` 下载和校验。
5. 使用 hash 校验。
6. 支持断点续传。
7. 支持镜像源。

---

## 19. 测试计划

### 19.1 单元测试

覆盖：

1. `ABIAgentInterface`。
2. JSON envelope。
3. permission model。
4. plugin discovery。
5. tool contract validation。
6. standard table validation。
7. error taxonomy。
8. diagnostic hints。
9. CLI argument mapping。
10. OpenAI descriptor export。

### 19.2 集成测试

覆盖：

1. `metagenomic_plasmid plan`。
2. `metagenomic_plasmid dry-run`。
3. `metagenomic_plasmid inspect`。
4. `metagenomic_plasmid report`。
5. `metatranscriptomics plan`。
6. `metatranscriptomics dry-run`。
7. OpenAI descriptor export。
8. MCP server import。
9. Job Service submit / status / artifacts / cancel。

### 19.3 Golden Trace 测试

保存标准 Agent 调用轨迹：

```jsonl
{"tool":"abi_list_types","arguments":{}}
{"tool":"abi_plan","arguments":{"analysis_type":"metagenomic_plasmid","config_path":"config.yaml","sample_sheet":"samples.tsv","outdir":"results/demo"}}
{"tool":"abi_dry_run","arguments":{"analysis_type":"metagenomic_plasmid","config_path":"config.yaml","sample_sheet":"samples.tsv","outdir":"results/demo"}}
{"tool":"abi_inspect","arguments":{"result_dir":"results/demo"}}
{"tool":"abi_report","arguments":{"analysis_type":"metagenomic_plasmid","result_dir":"results/demo"}}
```

### 19.4 CI 质量门

必须包含：

```bash
pytest
ruff check
black --check
mypy
python -m build
twine check dist/*
```

### 19.5 Artifact 验收

每个 demo 必须产出：

```text
execution_plan.json
provenance/commands.tsv
provenance/resolved_inputs.tsv
provenance/tool_versions.tsv
provenance/resources.json
provenance/progress.jsonl
tables/*.tsv
report/report.md
report/report.html
```

---

## 20. LLM / Agent 对照实验

### 20.1 实验目的

证明 **ABI control layer** 对未训练模型有价值。

### 20.2 实验组

| 组别                        | Agent 可用信息                                                  | 目的             |
| ------------------------- | ----------------------------------------------------------- | -------------- |
| **A. LLM + README**       | README、CLI 文档、shell                                         | 测试非结构化文档下的能力   |
| **B. Plain Python API**   | 普通函数和 docstring                                             | 测试模型是否能正确写代码   |
| **C. Plain tool calling** | 零散工具函数                                                      | 测试只给工具接口是否足够   |
| **D. ABI control layer**  | lifecycle API、schema、provenance、standard tables、diagnostics | 测试 ABI 是否提升成功率 |

### 20.3 指标

1. 任务完成率。
2. 正确工具选择率。
3. 参数错误率。
4. 是否跳过 dry-run。
5. 是否未经确认直接 run。
6. 缺失输入诊断成功率。
7. 缺失数据库诊断成功率。
8. 工具不存在诊断成功率。
9. 人工介入次数。
10. 从自然语言需求到 successful dry-run 的时间。
11. 是否能基于 `inspect` 提出正确下一步。

### 20.4 预期结论

预期 **ABI control layer** 在以下方面优于其他组：

1. 更少参数幻觉。
2. 更少错误执行。
3. 更高 dry-run 成功率。
4. 更强失败诊断。
5. 更少人工介入。
6. 更稳定结果读取。

---

## 21. 开发阶段规划

### Phase 0：设计冻结

时间：第 0 周

目标：

1. 冻结 ABI 开发边界。
2. 明确不自研完整 Agent 平台。
3. 明确 Core / Transport / Plugin 分层。
4. 明确 PyPI 分发策略。
5. 明确两个 demo 插件。
6. 明确论文叙事边界。

交付物：

```text
docs/abi_final_development_plan.md
docs/abi_spec_v0.1.md
docs/openai_interface_standard.md
```

验收标准：

1. 所有人接受 **中厚 Core + 薄 Transport + 清晰 Plugin** 方案。
2. 不再以工具数量作为主目标。
3. 不再把 AutoPlasm 当作唯一主体。

---

### Phase 1：ABI Core 稳定化

时间：第 1–2 周

目标：

1. 稳定 `ABIAgentInterface`。
2. 统一 JSON envelope。
3. 统一参数命名。
4. 加入 permission model。
5. 加入 error taxonomy。
6. 加入 diagnostic hints。
7. 稳定 execution plan schema。
8. 稳定 standard table manager。
9. 稳定 provenance manager。

任务：

```text
src/abi/agent/interface.py
src/abi/agent/envelopes.py
src/abi/permissions.py
src/abi/diagnostics.py
src/abi/schemas.py
src/abi/provenance.py
src/abi/tables.py
```

验收命令：

```bash
abi list-types --output-json
abi plan --type metatranscriptomics --output-json
abi dry-run --type metatranscriptomics --output-json
abi inspect --result-dir results/abi_metatranscriptomics_demo --output-json
```

验收标准：

1. 所有命令返回统一 envelope。
2. 所有错误有 `error_code`。
3. `run` 默认返回 `confirmation_required`。
4. `plan` 和 `dry_run` 不执行真实工具。
5. dry-run 写出完整 provenance。

---

### Phase 2：AutoPlasm 插件化

时间：第 2–3 周

目标：

将 AutoPlasm 变为 ABI 的 **`metagenomic_plasmid`** 插件。

任务：

1. 新建 `abi.plugins.metagenomic_plasmid`。
2. 实现 `load_config()`。
3. 实现 `build_plan()`。
4. 接入 AutoPlasm planner。
5. 接入 AutoPlasm executor。
6. 接入 AutoPlasm standard tables。
7. 接入 AutoPlasm parser。
8. 接入 AutoPlasm report。
9. 建立插件 manifest。
10. 建立插件 contract 测试。

验收标准：

```bash
abi plan --type metagenomic_plasmid --config examples/config_minimal.yaml --output-json
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --output-json
abi inspect --result-dir results/plasmid_demo --output-json
abi report --type metagenomic_plasmid --result-dir results/plasmid_demo --output-json
```

必须产出：

```text
execution_plan.json
provenance/commands.tsv
provenance/resolved_inputs.tsv
tables/*.tsv
report/report.md
report/report.html
```

---

### Phase 3：第二插件实现

时间：第 3–4 周

目标：

实现 **`metatranscriptomics`** 作为可移植性 demo。

任务：

1. 新建插件目录。
2. 定义 `abi-plugin.yaml`。
3. 定义 `tool_registry.yaml`。
4. 定义 `standard_tables.yaml`。
5. 定义 `tool_contracts/fastp.yaml`。
6. 定义 `tool_contracts/star.yaml` 或 `hisat2.yaml`。
7. 定义 `tool_contracts/featurecounts.yaml`。
8. 实现 `build_plan()`。
9. 实现 `_parse_featurecounts()`。
10. 实现 generic report。

验收标准：

```bash
abi plan --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi inspect --result-dir results/rnaseq_demo --output-json
abi report --type metatranscriptomics --result-dir results/rnaseq_demo --output-json
```

必须证明：

```text
同一个 ABIAgentInterface
驱动两个不同 analysis_type
生成不同 execution_plan
写出相同结构 provenance
写出不同 standard tables
生成统一报告结构
```

---

### Phase 4：Agent Tool Layer 完成

时间：第 4–5 周

目标：

让通用 Agent 平台无需训练过 ABI，也能通过 schema 和 descriptor 调用 ABI。

任务：

1. 稳定 CLI JSON。
2. 稳定 OpenAI-compatible descriptors。
3. 所有 schema 添加 `additionalProperties: false`。
4. 默认不导出 `abi_run`。
5. `--include-execution` 才导出 `abi_run`。
6. 实现 `abi export-agent-context`。
7. 实现 `abi doctor-agent`。
8. 输出 golden traces。
9. MCP 作为 optional transport 保持可用。

验收标准：

```bash
abi export-openai-tools --type metagenomic_plasmid --format json
abi export-openai-tools --type metagenomic_plasmid --format json --include-execution
abi export-agent-context --type metagenomic_plasmid --format json
abi doctor-agent --type metagenomic_plasmid
```

---

### Phase 5：Job Service Hardening

时间：第 5–6 周

目标：

让长任务可提交、查询、取消和读取 artifact。

任务：

1. 稳定 `/jobs` API。
2. 增加 job store 持久化。
3. 增加 job artifact index。
4. 增加强制终止机制。
5. 增加 backend metadata。
6. 记录 remote scheduler job id。
7. 增加 job-level provenance。

验收命令：

```bash
abi job-service --host 127.0.0.1 --port 18791 --workers 1

abi job submit \
  --command run \
  --analysis-type metatranscriptomics \
  --engine nextflow \
  --outdir /tmp/abi_job_demo \
  --confirm-execution

abi job status JOB_ID
abi job artifacts JOB_ID
abi job cancel JOB_ID
```

验收标准：

1. 未确认 execution job 不入队。
2. 已确认 job 能查询状态。
3. artifacts 能返回 outdir、report、provenance。
4. cancel 对 queued job 有效。
5. running job 至少记录 cancel_requested。

---

### Phase 6：PyPI Alpha 发布

时间：第 6 周

目标：

发布 **`autoplasm-abi`** alpha 包。

任务：

1. 整理 `pyproject.toml`。
2. 整理 README。
3. 加入 license。
4. 加入 package data。
5. 加入 console script。
6. 加入 optional extras。
7. 构建 wheel 和 sdist。
8. 上传 TestPyPI。
9. 验证安装。
10. 上传正式 PyPI alpha。

命令：

```bash
python -m build
twine check dist/*
twine upload --repository testpypi dist/*
pip install -i https://test.pypi.org/simple/ autoplasm-abi
abi list-types
abi dry-run --type metatranscriptomics
```

正式发布：

```bash
twine upload dist/*
```

验收标准：

1. 新环境中可以 `pip install autoplasm-abi`。
2. `abi --help` 可用。
3. `abi list-types` 可用。
4. `abi dry-run --type metatranscriptomics` 可用。
5. 不要求自动安装大型生信数据库。
6. 不要求自动创建 mamba 环境。

---

### Phase 7：对照实验与论文 Artifact

时间：第 7–8 周

目标：

形成可发表证据。

任务：

1. 设计 LLM + README baseline。
2. 设计 Plain Python API baseline。
3. 设计 Plain tool calling baseline。
4. 设计 ABI control layer 实验。
5. 固定任务集。
6. 记录成功率、错误率、人工介入次数。
7. 保存 golden traces。
8. 保存 demo artifacts。
9. 整理论文图表。
10. 完成 system design 文档。

交付物：

```text
docs/experiments/
  README_baseline/
  plain_api_baseline/
  plain_tool_calling/
  abi_control_layer/
  metrics.tsv
  traces.jsonl
  artifacts/
```

---

## 22. 验收总清单

### 22.1 功能验收

| 项目                          | 必须通过 |
| --------------------------- | ---: |
| `abi list-types`            |    是 |
| `abi plan`                  |    是 |
| `abi dry-run`               |    是 |
| `abi inspect`               |    是 |
| `abi report`                |    是 |
| `abi run` confirmation gate |    是 |
| `abi export-openai-tools`   |    是 |
| `abi export-agent-context`  |    是 |
| `abi doctor-agent`          |    是 |
| `abi job-service`           |    是 |
| `metagenomic_plasmid` 插件    |    是 |
| `metatranscriptomics` 插件    |    是 |
| PyPI 安装                     |    是 |

### 22.2 Artifact 验收

每个插件必须产生：

```text
execution_plan.json
provenance/commands.tsv
provenance/resolved_inputs.tsv
provenance/tool_versions.tsv
provenance/resources.json
provenance/progress.jsonl
tables/*.tsv
report/report.md
report/report.html
```

### 22.3 Agent 验收

Agent 必须能：

1. 调用 `list_types`。
2. 选择 analysis type。
3. 生成 plan。
4. 执行 dry-run。
5. inspect 结果。
6. 解释错误。
7. 不未经确认调用真实 run。
8. 基于 diagnostic hints 提出下一步。
9. 读取 standard tables。
10. 生成简短报告摘要。

---

## 23. 风险与应对

### 23.1 风险表

| 风险            | 严重性 | 表现                      | 应对                                                     |
| ------------- | --: | ----------------------- | ------------------------------------------------------ |
| 被认为只是 wrapper |   高 | 只封装 CLI 或工具函数           | 强调 lifecycle control layer                             |
| 模型没训练过 ABI    |   高 | 编造 API、参数错              | 用 schema、descriptor、agent context、golden traces        |
| Core 太薄       |   高 | 退化为普通函数库                | 保留 plan / dry-run / inspect / provenance / diagnostics |
| Transport 太厚  |   中 | 业务逻辑散落 CLI/MCP/HTTP     | 所有业务逻辑进 ABIAgentInterface                              |
| 插件边界混乱        |   中 | AutoPlasm-specific 工具泄漏 | 每个插件独立 registry / standard tables                      |
| 诊断能力不足        |   高 | Agent 失败后无法恢复           | 标准 error_code + diagnostic_hints                       |
| PyPI 包过重      |   中 | 安装慢、失败多                 | 大型资源外置                                                 |
| claim 过大      |   高 | 审稿人质疑                   | 第一篇只 claim bioinformatics ABI + 两插件验证                  |
| 长任务阻塞 Agent   |   中 | 会话超时                    | Job Service                                            |
| 真实 run 复现困难   |   中 | 数据库和环境难配置               | dry-run artifact + resource checker                    |

---

## 24. 论文叙事边界

### 24.1 推荐表述

> ABI is a domain control layer that makes bioinformatics workflows agent-operable through machine-readable tool contracts, lifecycle-level planning, permission-gated execution, provenance-aware inspection, and standardized result tables.

中文表述：

> **ABI 是一个面向 Agent 的生物信息学控制层，通过机器可读工具契约、生命周期级规划、权限门控执行、可审计 provenance 和标准结果表，让复杂生信 workflow 能被通用 Agent 稳定调用、检查和诊断。**

### 24.2 不推荐表述

1. 不说 **ABI 替代 Nextflow / nf-core / Galaxy**。
2. 不说 **ABI 已覆盖所有生物信息学**。
3. 不说 **ABI 的创新是工具数量多**。
4. 不说 **自然语言能力由 ABI 自己完成**。
5. 不说 **两个插件证明所有领域都能迁移**。

---

## 25. 最终交付形态

### 25.1 软件交付

```text
autoplasm-abi PyPI package
GitHub repository
ABI Core
CLI JSON
OpenAI-compatible descriptors
optional MCP server
HTTP Job Service
metagenomic_plasmid plugin
metatranscriptomics plugin
```

### 25.2 文档交付

```text
docs/abi_spec_v0.1.md
docs/abi_final_development_plan.md
docs/plugin_development_guide.md
docs/openai_interface_standard.md
docs/job_service.md
docs/agent_usage.md
docs/experiments.md
```

### 25.3 实验交付

```text
golden_traces/
demo_artifacts/
baseline_comparison/
metrics.tsv
figures/
```

---

## 26. 最终判断

**ABI 的最终开发方向已经确定：**

```text
不是普通 Python 库
不是单一 Agent 平台插件
不是更多工具 wrapper
不是 AutoPlasm CLI 的薄封装
```

而是：

```text
中厚 ABI Core
+ provider-neutral Agent Tool Layer
+ plugin-based bioinformatics extension system
+ permission-gated execution
+ provenance-aware inspection
+ standardized result tables
+ Job Service for long tasks
+ PyPI-distributed developer package
```

这条路线能同时满足三个目标：

1. **工程上可实现**：Core / Transport / Plugin 分层清楚。
2. **Agent 上可调用**：模型不需要训练过 ABI，只需要读取 schema 和 descriptor。
3. **论文上可防守**：创新点不是工具数量，而是 agent-facing lifecycle control layer。
