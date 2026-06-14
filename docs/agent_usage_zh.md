# Agent 使用指南

Agent 应将 ABI 用作生命周期控制层，而非直接编写生物信息学管线代码。

## 入门

### 安装 ABI 技能 (Claude Code)

```bash
abi install-skills
```

这会将 41 个捆绑的 SKILL.md 文件复制到 `~/.claude/skills/abi/`。安装完成后，Claude Code 会自动加载这些技能并知晓如何使用 `abi` CLI 及其生物信息学工具。

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
3. `abi_plan` — 构建执行计划
4. `abi_dry_run` — 验证命令和溯源（不执行真实工具）
5. `abi_inspect` — 检查溯源中的失败项
6. `abi_run` — **仅在用户明确批准后**执行
7. `abi_report` — 从标准表和溯源重新生成报告

## 传输方式

### CLI JSON（通用）

```bash
abi list-types --output-json
abi plan --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi inspect --result-dir results/rnaseq_demo --output-json
abi report --type metatranscriptomics --result-dir results/rnaseq_demo --output-json
```

所有命令返回带有 `success`、`confirmation_required` 或 `error` 状态的 JSON 信封。

### OpenAI 工具

```bash
# 导出函数描述符（默认出于安全考虑省略 abi_run）
abi export-openai-tools --type metagenomic_plasmid --format responses

# 包含执行工具
abi export-openai-tools --type metagenomic_plasmid --format responses --include-execution
```

### MCP

```bash
abi-mcp  # 启动 stdio 服务器，将所有 ABI 工具注册为 MCP 工具
```

### Python

```python
from abi.agent import ABIAgentInterface

agent = ABIAgentInterface()
result = agent.list_types()
plan_json = agent.plan(analysis_type="metatranscriptomics", outdir="results/")
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

## Golden Trace

已知良好的 Agent 调用序列存储在 `golden_traces/` 中，由 `tests/integration/test_golden_traces.py` 回放。
