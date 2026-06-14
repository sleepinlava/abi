# Agent Usage Guide

Agents should use ABI as a lifecycle control layer rather than writing
bioinformatics pipeline code directly.

## Getting Started

### Install ABI Skills (Claude Code)

```bash
abi install-skills
```

This copies 41 bundled SKILL.md files to `~/.claude/skills/abi/`. After
installation, Claude Code automatically loads the skills and knows how to
use the `abi` CLI and its bioinformatics tools.

Use `--force` to overwrite existing files, or `--target` to customize
the destination directory.

### MCP Server (Claude Desktop / Claude Code)

```bash
abi-mcp
```

Configure in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "abi": { "command": "abi-mcp" }
  }
}
```

### Python API (for custom agent code)

```python
import abi

# Compact operating guide for system prompt injection
print(abi.get_agent_guide())

# List all installed analysis plugins
for p in abi.list_plugins_summary():
    print(f"{p['analysis_type']}: {p['name']}")
```

## Safe Sequence

1. `abi_list_types` — discover installed analysis plugins
2. `abi_export_agent_context` or `abi_doctor_agent` — get operating context
3. `abi_plan` — build execution plan
4. `abi_dry_run` — validate commands and provenance (no real tools)
5. `abi_inspect` — check provenance for failures
6. `abi_report` — regenerate reports
7. `abi_run` — execute **only after explicit user approval**

## Transport Methods

### CLI JSON (universal)

```bash
abi list-types --output-json
abi plan --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi inspect --result-dir results/rnaseq_demo --output-json
abi report --type metatranscriptomics --result-dir results/rnaseq_demo --output-json
```

All commands return JSON envelopes with status `success`, `confirmation_required`,
or `error`.

### OpenAI Tools

```bash
# Export function descriptors (omit abi_run by default for safety)
abi export-openai-tools --type metagenomic_plasmid --format responses

# Include execution tools
abi export-openai-tools --type metagenomic_plasmid --format responses --include-execution
```

### MCP

```bash
abi-mcp  # start stdio server, registers all ABI tools as MCP tools
```

### Python

```python
from abi.agent import ABIAgentInterface

agent = ABIAgentInterface()
result = agent.list_types()
plan_json = agent.plan(analysis_type="metatranscriptomics", outdir="results/")
```

## JSON Envelope Contract

Every `ABIAgentInterface` method returns a JSON string with one of three statuses:

| Status | Meaning | Key fields |
|--------|---------|------------|
| `success` | Operation completed | `result` holds the payload |
| `confirmation_required` | User must approve (run only) | Exit code 2, re-invoke with `confirm_execution=true` |
| `error` | Operation failed | `error_code` + `diagnostic_hints` for automated recovery |

## Error Recovery

On error, inspect in order:

1. `error_code` and `diagnostic_hints` in the JSON envelope
2. `result_dir/provenance/commands.tsv` — find `failed` rows
3. `result_dir/provenance/resolved_inputs.tsv` — check for missing/placeholder inputs
4. `result_dir/provenance/step_logs/<step_id>.stderr.log` — raw tool error output

Do not parse raw tool outputs first. Prefer standard tables under `tables/`.

## Golden Traces

Known-good agent call sequences are stored in `golden_traces/` and replayed by
`tests/integration/test_golden_traces.py`.
