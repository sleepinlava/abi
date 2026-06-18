# OpenAI 兼容接口标准

ABI 为 Agent 平台导出与提供商无关的描述符：

```bash
abi export-openai-tools --type metagenomic_plasmid --format responses
abi export-openai-tools --type metagenomic_plasmid --format apps-sdk
abi export-openai-tools --type metagenomic_plasmid --format json
```

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

## Schema 规则

- 描述符输入 schema 使用 `additionalProperties: false`。
- Responses 描述符设置 `strict: true`。
- Apps SDK 描述符在适当位置包含 `readOnlyHint`。
- JSON 描述符包含 `permission` 和 `requires_confirmation`。

## Agent 上下文

Agent 可以获取紧凑的操作上下文：

```bash
abi export-agent-context --type metagenomic_plasmid --format json
abi doctor-agent --type metagenomic_plasmid
```

上下文列出安全调用顺序、标准表、重要产物、错误码以及恢复规则。

## Agent 技能 (Claude Code)

ABI 在包内的 `src/abi/skills/` 中捆绑了 41 个 SKILL.md 文件（每个生物信息学工具一个，外加一个 `abi_agent` 操作技能）。通过以下命令安装到 Claude Code：

```bash
abi install-skills         # → ~/.claude/skills/abi/
abi install-skills --force # 覆盖已有文件
```

Claude Code 在每次会话启动时自动加载 `~/.claude/skills/` 中的所有技能。

## MCP 服务器

```bash
abi-mcp                    # 启动 MCP stdio 服务器
python -m abi.mcp.server   # 等效命令（如果 abi-mcp 不可用）
```

该服务器将所有 ABI Agent 工具（list_types、plan、dry_run、inspect、report、run 等）注册为 MCP 工具，供 Claude Desktop 和 Claude Code 使用。

## Python API

```python
import abi
print(abi.get_agent_guide())        # 用于系统提示注入的紧凑指南
print(abi.list_plugins_summary())   # [(analysis_type, name, description), ...]
```
