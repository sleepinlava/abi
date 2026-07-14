# 多 LLM 工具描述符导出

ABI 通过统一的 `tool_descriptors` SSOT 为 AI Agent 平台导出与提供商无关的工具描述符。标准命令为：

```bash
abi export-tools --type metagenomic_plasmid --format openai --provider openai
abi export-tools --type metagenomic_plasmid --format openai --provider deepseek
abi export-tools --type metagenomic_plasmid --format anthropic
abi export-tools --type metagenomic_plasmid --format gemini
```

支持的提供商配置文件：OpenAI、Anthropic Claude、Google Gemini、
DeepSeek、智谱 (GLM)、Kimi (Moonshot)、通义 (Qwen)、MiniMax。

## 默认工具

默认导出包括：

- `abi_list_types`
- `abi_plan`
- `abi_dry_run`
- `abi_inspect`
- `abi_report`
- `abi_export_nextflow`
- `abi_export_agent_context`
- `abi_doctor_agent`
- `abi_validate_result`

`abi_run` 默认不导出，除非传入 `--include-execution`。

## 格式家族

支持三种格式家族：

- **OpenAI 兼容** (`--format openai`): 适用于 OpenAI、DeepSeek、智谱、
  Kimi、通义、MiniMax 的函数描述符。使用 `additionalProperties: false`、
  `strict: true` (Responses API) 和 `readOnlyHint` (Apps SDK)。
- **Anthropic** (`--format anthropic`): Claude 的 `tool_use` 描述符。
- **Gemini** (`--format gemini`): Google Gemini 的 `function_declarations`。

## Agent 上下文

Agent 可以获取紧凑的操作上下文：

```bash
abi export-agent-context --type metagenomic_plasmid --format json
abi doctor-agent --type metagenomic_plasmid
```

上下文列出安全调用顺序、标准表、重要产物、错误码以及恢复规则。

## Agent 技能 (Claude Code)

ABI 在包内的 `src/abi/skills/` 中捆绑了 SKILL.md 文件（每个生物信息学工具一个，外加一个 `abi_agent` 操作技能）。通过以下命令安装到 Claude Code：

```bash
abi install-skills         # → ~/.claude/skills/abi/
abi install-skills --force # 覆盖已有文件
```

Claude Code 在每次会话启动时自动加载 `~/.claude/skills/` 中的所有技能。

## MCP 服务器

```bash
abi-mcp                    # safe profile：不包含执行和管理工具
abi-mcp --profile full     # 加入受确认门控的 abi_run
python -m abi.mcp.server   # 等效命令（如果 abi-mcp 不可用）
```

默认 `safe` profile 为 Claude Desktop 和 Claude Code 注册发现、规划、检查和报告工具。
只有会话确实需要 `abi_run` 时才使用 `full`；真实执行仍须在用户明确批准后传入
`confirm_execution=true`。

## Python API

```python
import abi
print(abi.get_agent_guide())        # 用于系统提示注入的紧凑指南
print(abi.list_plugins_summary())   # [(analysis_type, name, description), ...]
```
