# OpenAI-Compatible Interface Standard

ABI exports provider-neutral descriptors for agent platforms with:

```bash
abi export-openai-tools --type metagenomic_plasmid --format responses
abi export-openai-tools --type metagenomic_plasmid --format apps-sdk
abi export-openai-tools --type metagenomic_plasmid --format json
```

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

## Schema Rules

- Descriptor input schemas use `additionalProperties: false`.
- Responses descriptors set `strict: true`.
- Apps SDK descriptors include `readOnlyHint` where appropriate.
- JSON descriptors include `permission` and `requires_confirmation`.

## Agent Context

Agents can fetch compact operating context:

```bash
abi export-agent-context --type metagenomic_plasmid --format json
abi doctor-agent --type metagenomic_plasmid
```

The context lists safe call order, standard tables, important artifacts, error
codes, and recovery rules.

## Agent Skills (Claude Code)

ABI bundles 41 SKILL.md files (one for each bioinformatics tool plus an
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
abi-mcp                    # start MCP stdio server
python -m abi.mcp.server   # equivalent (if abi-mcp not available)
```

The server registers all ABI agent tools (list_types, plan, dry_run, inspect,
report, run, etc.) as MCP tools for Claude Desktop and Claude Code.

## Python API

```python
import abi
print(abi.get_agent_guide())        # compact guide for system prompt injection
print(abi.list_plugins_summary())   # [(analysis_type, name, description), ...]
```
