# Agent 使用指南

Agent 应将 ABI 用作生命周期控制层，而非直接编写生物信息学管线代码。

## 入门

### 安装 ABI 技能 (Claude Code)

```bash
abi install-skills
```

这会将 40 个捆绑的 SKILL.md 文件复制到 `~/.claude/skills/abi/`。安装完成后，Claude Code 会自动加载这些技能并知晓如何使用 `abi` CLI 及其生物信息学工具。

使用 `--force` 覆盖已有文件，或使用 `--target` 自定义目标目录。

### MCP 服务器 (Claude Desktop / Claude Code)

```bash
abi-mcp
```

在 `claude_desktop_config.json` 中配置：

```json
{
  "mcpServers": {
    "abi": { "command": "abi-mcp" }
  }
}
```

### Python API（用于自定义 Agent 代码）

```python
import abi

# 用于系统提示注入的紧凑操作指南
print(abi.get_agent_guide())

# 列出所有已安装的分析插件
for p in abi.list_plugins_summary():
    print(f"{p['analysis_type']}: {p['name']}")
```

## 安全调用序列

1. `abi_list_types` — 发现已安装的分析插件
2. `abi_export_agent_context` 或 `abi_doctor_agent` — 获取操作上下文
3. `abi_query` — 轻量级元数据查询（阶段、工具、平台、步骤 I/O）
4. `abi_plan` — 构建执行计划（包含 `summary` 字段 — 无需读取 `execution_plan.json`）
5. `abi_dry_run` — 验证命令和溯源（不执行真实工具）
6. `abi_inspect` — 检查溯源中的失败项
7. `abi_run` — **仅在用户明确批准后**执行
8. `abi_report` — 从标准表和溯源重新生成报告

## 传输方式

### CLI JSON（通用）

```bash
abi list-types --output-json
abi query --type metatranscriptomics --what stages --output-json
abi plan --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi inspect --result-dir results/rnaseq_demo --output-json
abi report --type metatranscriptomics --result-dir results/rnaseq_demo --output-json
```

所有命令返回带有 `success`、`confirmation_required` 或 `error` 状态的 JSON 信封。

### 多 LLM 工具描述符

ABI 从单一真相源为所有主流大模型提供者导出工具描述符。

```bash
# OpenAI 兼容提供商（Chat Completions API）
abi export-tools --type metagenomic_plasmid --format openai --provider openai
abi export-tools --type metagenomic_plasmid --format openai --provider deepseek
abi export-tools --type metagenomic_plasmid --format openai --provider zhipu   # 智谱 GLM
abi export-tools --type metagenomic_plasmid --format openai --provider kimi     # Moonshot
abi export-tools --type metagenomic_plasmid --format openai --provider qwen     # 通义千问
abi export-tools --type metagenomic_plasmid --format openai --provider minimax  # MiniMax

# Anthropic Claude（tool_use 格式）
abi export-tools --type metagenomic_plasmid --format anthropic

# Google Gemini（function_declarations 格式）
abi export-tools --type metagenomic_plasmid --format gemini

# 包含执行工具
abi export-tools --type metagenomic_plasmid --format openai --include-execution
```

### OpenAI 工具（旧版，向后兼容）

```bash
abi export-openai-tools --type metagenomic_plasmid --format responses
```

### MCP

```bash
abi-mcp  # 启动 stdio 服务器，将所有 ABI 工具注册为 MCP 工具
```

### Python

```python
from abi.agent import ABIAgentInterface

# 默认：紧凑错误信封（不含 error_type，节省 token）
agent = ABIAgentInterface()
result = agent.list_types()
plan_json = agent.plan(analysis_type="metatranscriptomics", outdir="results/")

# 调试模式：错误信封包含 error_type
agent_debug = ABIAgentInterface(verbose_errors=True)
```

## JSON 信封合约

每个 `ABIAgentInterface` 方法返回一个 JSON 字符串，具有以下三种状态之一：

| 状态 | 含义 | 关键字段 |
|--------|---------|------------|
| `success` | 操作完成 | `result` 持有负载数据 |
| `confirmation_required` | 用户必须批准（仅 run） | 退出码 2，以 `confirm_execution=true` 重新调用 |
| `error` | 操作失败 | `error_code` + `diagnostic_hints` 用于自动恢复 |

## 错误恢复

遇到错误时，按以下顺序检查：

1. JSON 信封中的 `error_code` 和 `diagnostic_hints`
2. `result_dir/provenance/commands.tsv` — 查找 `failed` 行
3. `result_dir/provenance/resolved_inputs.tsv` — 检查缺失/占位输入
4. `result_dir/provenance/step_logs/<step_id>.stderr.log` — 原始工具错误输出

不要首先解析原始工具输出。优先使用 `tables/` 下的标准表。

## 合约与可复现性检查

当被问及工作流是否受约束、可验证或可复现时，检查产物而非仅依赖 dry-run：

1. `execution_plan.json` 包含预期的分析类型、样本、步骤和输出路径。
2. `provenance/commands.tsv` 没有失败或意外跳过的步骤。
3. `provenance/resolved_inputs.tsv` 没有缺失的必需输入。
4. `provenance/checksums.json` 在启用合约的真实执行后存在。
5. `provenance/tool_versions.tsv` 和 `provenance/resources.json` 标识所使用的可执行文件和资源。
6. `tables/*.tsv` 包含报告所使用的生物学结果行。
7. 工作流路线和解释限制对照 `docs/workflow_validation_zh.md` 进行检查。

不要声称 dry-run 能证明生物学有效性。Dry-run 验证的是规划和命令渲染。科学声明需要真实工具输出、已配置的数据库、版本/资源清单以及基准验收检查。

## Plan 摘要化

`abi plan` 信封现在包含 `summary` 字段（流水线阶段、关键工具、平台）。Agent 无需读取完整 `execution_plan.json` 即可理解工作流结构 — 复杂流水线 plan 输出可节省 78-95% token。

如需无需完整 plan 开销的轻量级元数据查询，使用 `abi query`：

```bash
# 流水线级元数据
abi query --type metagenomic_plasmid --what stages
abi query --type metagenomic_plasmid --what tools
abi query --type metagenomic_plasmid --what platforms

# 步骤级 I/O 详情
abi query --type metagenomic_plasmid --step qc_fastp --what inputs
abi query --type metagenomic_plasmid --step qc_fastp --what outputs
```

所有 `abi query` 命令均支持 `--output-json` 供 Agent 使用。

## `run` vs `dispatch`

两者都执行真实工具，但调用模型不同：

| 方面 | `run` | `dispatch` |
|------|-------|------------|
| 调用方式 | CLI 命令 | HTTP 端点 (Job Service) |
| 阻塞 | 是（同步） | 立即返回（异步） |
| 确认 | `--confirm-execution` 标志 | 作业队列 + payload 中的 `confirm_execution` |
| 进度 | 内联进度条/日志 | `GET /jobs/{id}` 轮询 |
| 取消 | Ctrl+C (SIGINT, 尽力而为) | `POST /jobs/{id}/cancel` (SIGTERM → SIGKILL) |
| 适用场景 | 交互式 Agent 调用 | 长时间运行的批处理作业、远程执行 |

交互式会话优先使用 `run`。当执行时间超过 Agent 超时或在远程机器上运行时使用 `dispatch`。

## 常见故障排查

### 工具未找到 (`TOOL_NOT_FOUND`)

工具可执行文件不在 PATH 上。检查：

```bash
# 验证 conda 环境已激活
conda activate <env_name>

# 或列出哪些工具可用
abi check-resources --type <analysis_type>
```

### 资源缺失 (`MISSING_RESOURCE`)

缺少必需的数据库或参考文件：

```bash
# 查看缺失项
abi check-resources --type <analysis_type>

# 安装缺失的资源
abi setup-resources --type <analysis_type> --confirm
```

### 合约违规 (`CONTRACT_VIOLATION`)

工具输出与预期合约不匹配：

1. 检查 `provenance/step_logs/<step_id>.stderr.log` 获取工具错误
2. 验证输入文件存在且非空
3. 检查工具版本是否变更 — 输出格式可能不同
4. 如果合约过于严格，调整工具合约中的 `min_size` 或 `assertions`

### Dry-run 成功但真实执行失败

1. 验证 conda 环境已安装：`ls envs/`
2. 检查所需数据库是否已下载：`abi check-resources --type <analysis_type>`
3. 确保输入 FASTQ 文件存在且可读
4. 检查磁盘空间和内存：某些工具需要 16GB+ RAM

### 权限拒绝

ABI 实施三级权限模型：

- `read_only` 操作 (`list_types`、`query`、`inspect`) — 始终允许
- `planning_write` 操作 (`plan`、`dry_run`、`report`) — 仅写入计划/溯源
- `execution` (`run`) — **需要 `confirm_execution=true`**

如果 `run` 返回 `confirmation_required`，使用 `--confirm-execution` 重新调用。

### 并行执行未加速

检查配置中的 `config.execution.parallel` 和 `config.execution.workers`：

```yaml
execution:
  parallel: true
  workers: 8
```

并行执行是样本级别的。步骤较少的单样本管线不会受益。多样本管线将达到 worker 数量以内的近线性加速。

## Golden Trace

已知良好的 Agent 调用序列存储在 `golden_traces/` 中，由 `tests/integration/test_golden_traces.py` 回放。
