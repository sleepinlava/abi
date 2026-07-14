# Multi-LLM Tool Descriptor Export

ABI exports provider-neutral tool descriptors for AI agent platforms via the
unified `tool_descriptors` SSOT. The canonical command is:

```bash
abi export-tools --type metagenomic_plasmid --format openai --provider openai
abi export-tools --type metagenomic_plasmid --format openai --provider deepseek
abi export-tools --type metagenomic_plasmid --format anthropic
abi export-tools --type metagenomic_plasmid --format gemini
```

Supported provider profiles: OpenAI, Anthropic Claude, Google Gemini,
DeepSeek, Zhipu (GLM), Kimi (Moonshot), Qwen (Tongyi), MiniMax.

## Default Tools

Default exports include:

- `abi_list_types`
- `abi_plan`
- `abi_dry_run`
- `abi_inspect`
- `abi_report`
- `abi_export_nextflow`
- `abi_export_agent_context`
- `abi_doctor_agent`
- `abi_validate_result`

`abi_run` is omitted unless `--include-execution` is passed.

## Format Families

Three format families are supported:

- **OpenAI-compatible** (`--format openai`): function descriptors for OpenAI,
  DeepSeek, Zhipu, Kimi, Qwen, MiniMax. Uses `additionalProperties: false`,
  `strict: true` (Responses API), and `readOnlyHint` (Apps SDK).
- **Anthropic** (`--format anthropic`): `tool_use` descriptors for Claude.
- **Gemini** (`--format gemini`): `function_declarations` for Google Gemini.

## Agent Context

Agents can fetch compact operating context:

```bash
abi export-agent-context --type metagenomic_plasmid --format json
abi doctor-agent --type metagenomic_plasmid
```

The context lists safe call order, standard tables, important artifacts, error
codes, and recovery rules.

## Agent Skills (Claude Code)

ABI bundles SKILL.md files (one for each bioinformatics tool plus an
``abi_agent`` operating skill) inside the package at ``src/abi/skills/``.
Install them into Claude Code with:

```bash
abi install-skills         # → ~/.claude/skills/abi/
abi install-skills --force # overwrite existing files
```

Claude Code automatically loads all skills from ``~/.claude/skills/`` on
each session start.

## MCP Server

```bash
abi-mcp                    # safe profile: no execution or management tools
abi-mcp --profile full     # add confirmation-gated abi_run
python -m abi.mcp.server   # equivalent (if abi-mcp not available)
```

The default `safe` profile registers discovery, planning, inspection, and
reporting tools for Claude Desktop and Claude Code. Use `full` only when the
session needs `abi_run`; execution still requires `confirm_execution=true`
after explicit user approval.

## Python API

```python
import abi
print(abi.get_agent_guide())        # compact guide for system prompt injection
print(abi.list_plugins_summary())   # [(analysis_type, name, description), ...]
```
