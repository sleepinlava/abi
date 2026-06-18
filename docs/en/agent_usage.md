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
3. `abi_query` — lightweight metadata query (stages, tools, platforms, step I/O)
4. `abi_plan` — build execution plan (includes `summary` field — no need to read `execution_plan.json`)
5. `abi_dry_run` — validate commands and provenance (no real tools)
6. `abi_inspect` — check provenance for failures
7. `abi_run` — execute **only after explicit user approval**
8. `abi_report` — regenerate reports from standard tables and provenance

## Transport Methods

### CLI JSON (universal)

```bash
abi list-types --output-json
abi query --type metatranscriptomics --what stages --output-json
abi plan --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo --output-json
abi inspect --result-dir results/rnaseq_demo --output-json
abi report --type metatranscriptomics --result-dir results/rnaseq_demo --output-json
```

All commands return JSON envelopes with status `success`, `confirmation_required`,
or `error`.

### Multi-LLM Tools

ABI exports tool descriptors for all major LLM providers from a single source of truth.

```bash
# OpenAI-compatible providers (Chat Completions API)
abi export-tools --type metagenomic_plasmid --format openai --provider openai
abi export-tools --type metagenomic_plasmid --format openai --provider deepseek
abi export-tools --type metagenomic_plasmid --format openai --provider zhipu   # 智谱 GLM
abi export-tools --type metagenomic_plasmid --format openai --provider kimi     # Moonshot
abi export-tools --type metagenomic_plasmid --format openai --provider qwen     # 通义千问
abi export-tools --type metagenomic_plasmid --format openai --provider minimax  # MiniMax

# Anthropic Claude (tool_use format)
abi export-tools --type metagenomic_plasmid --format anthropic

# Google Gemini (function_declarations format)
abi export-tools --type metagenomic_plasmid --format gemini

# Include execution tools in export
abi export-tools --type metagenomic_plasmid --format openai --include-execution
```

### OpenAI Tools (legacy, backward compat)

```bash
abi export-openai-tools --type metagenomic_plasmid --format responses
```

### MCP

```bash
abi-mcp  # start stdio server, registers all ABI tools as MCP tools
```

### Python

```python
from abi.agent import ABIAgentInterface

# Default: compact error envelopes (no error_type for token efficiency)
agent = ABIAgentInterface()
result = agent.list_types()
plan_json = agent.plan(analysis_type="metatranscriptomics", outdir="results/")

# For debugging: include error_type in error envelopes
agent_debug = ABIAgentInterface(verbose_errors=True)
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

## Contract and Reproducibility Checks

When asked whether a workflow is constrained, verifiable, or reproducible, check
the artifacts rather than relying on dry-run alone:

1. `execution_plan.json` has the expected analysis type, samples, steps, and
   output paths.
2. `provenance/commands.tsv` has no failed or unintended skipped steps.
3. `provenance/resolved_inputs.tsv` has no missing required inputs.
4. `provenance/checksums.json` exists after real execution with enforced
   contracts.
5. `provenance/tool_versions.tsv` and `provenance/resources.json` identify the
   executables and resources used.
6. `tables/*.tsv` contain the biological result rows used by reports.
7. The workflow route and interpretation limits are checked against
   `docs/workflow_validation.md`.

Do not claim that a dry-run proves biological validity. Dry-run validates
planning and command rendering. Scientific claims require real tool outputs,
configured databases, version/resource manifests, and benchmark acceptance
checks.

## Plan Summarization

`abi plan` envelopes now include a `summary` field with pipeline stages, key tools,
and platforms. Agents can understand the workflow structure without reading the full
`execution_plan.json` — saving 78-95% tokens on plan output for complex pipelines.

For lightweight metadata queries without plan overhead, use `abi query`:

```bash
# Pipeline-level metadata
abi query --type metagenomic_plasmid --what stages
abi query --type metagenomic_plasmid --what tools
abi query --type metagenomic_plasmid --what platforms

# Step-level I/O detail
abi query --type metagenomic_plasmid --step qc_fastp --what inputs
abi query --type metagenomic_plasmid --step qc_fastp --what outputs
```

All `abi query` commands support `--output-json` for agent consumption.

## Golden Traces

Known-good agent call sequences are stored in `golden_traces/` and replayed by
`tests/integration/test_golden_traces.py`.
