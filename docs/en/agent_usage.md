# Agent Usage Guide

Agents should use ABI as a lifecycle control layer rather than writing
bioinformatics pipeline code directly.

## Getting Started

### Install ABI Skills (Claude Code)

```bash
abi install-skills
```

This copies 40 bundled SKILL.md files to `~/.claude/skills/abi/`. After
installation, Claude Code automatically loads the skills and knows how to
use the `abi` CLI and its bioinformatics tools.

Use `--force` to overwrite existing files, or `--target` to customize
the destination directory.

### Claude Code, OpenCode, and Codex integrations

The repository ships a Claude Code plugin under `integrations/claude-code/abi/`
an OpenCode configuration plus Agent Skill under `integrations/opencode/`, and
a Codex plugin under `integrations/codex/abi/`. All three use the same
transport-neutral ABI interface and start the MCP server with the default
`safe` profile.

Install ABI with MCP support before loading an integration:

```bash
pip install "abi-agent[mcp]"
```

Use the unified installer for user or project scope:

```bash
abi agent install claude-code --scope project
abi agent install opencode --scope project
abi agent install codex --scope project
abi agent doctor codex --scope project
```

The installer preserves unrelated OpenCode JSON and Codex TOML settings. It
refuses to replace a different `abi` MCP entry unless `--force` is supplied.
Use `--output-json` in automation.

Installation locations are platform-native:

| Platform | Project skill | Project MCP config | User skill / config |
| --- | --- | --- | --- |
| Claude Code | `.claude/skills/abi/SKILL.md` | `.mcp.json` | `~/.claude/skills/abi`, `~/.claude.json` |
| OpenCode | `.opencode/skills/abi/SKILL.md` | `opencode.json` | `~/.config/opencode/skills/abi`, `~/.config/opencode/opencode.json` |
| Codex | `.agents/skills/abi/SKILL.md` | `.codex/config.toml` | `~/.agents/skills/abi`, `~/.codex/config.toml` |

`doctor` is read-only and exits non-zero when `abi-mcp`, the MCP runtime, the
skill, or the MCP entry is missing. It initializes the safe server without
starting stdio, so a missing `mcp` extra is detected before the agent launches.
Start a new agent session after installing a plugin or when a client does not
detect newly added skills automatically.

For Claude Code plugin development:

```bash
claude plugin validate integrations/claude-code/abi --strict
claude --plugin-dir integrations/claude-code/abi
```

For Codex plugin development, validate the distributable bundle with:

```bash
python /path/to/plugin-creator/scripts/validate_plugin.py integrations/codex/abi
```

Direct Codex installation uses `.agents/skills/abi` for project scope or
`~/.agents/skills/abi` for user scope, plus the matching `.codex/config.toml`.

### MCP Server

```bash
abi-mcp                         # safe: discovery, planning, and result tools
abi-mcp --profile discovery     # read-only discovery and inspection
abi-mcp --profile full          # adds confirmation-gated abi_run
```

The `management` profile preserves the complete compatibility surface and is
intended for administrative use, not ordinary agent sessions.

Manual MCP configuration uses:

```json
{
  "mcpServers": {
    "abi": {
      "command": "abi-mcp",
      "args": ["--profile", "safe"]
    }
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

## Run a Biological Analysis Through a Plugin

ABI does not create a separate MCP function for every plugin. The agent calls shared lifecycle tools such as `abi_plan` and `abi_dry_run`, then selects the plugin with the `analysis_type` argument.

### 1. Translate the biological question into an analysis request

Before selecting a plugin, establish:

- the biological question and expected result;
- input data type and sequencing platform;
- sample IDs, groups, contrasts, or paired-end relationships;
- available reference genomes, annotations, databases, and indexes;
- the intended runtime, compute limits, and output location.

Ask the user when missing information would change the plugin, workflow branch, reference, or biological interpretation. Do not guess a reference genome, sample grouping, or database profile.

### 2. Discover and select the plugin

| Biological goal | `analysis_type` |
| --- | --- |
| Profile a 16S microbial community | `amplicon_16s` |
| Compare bulk RNA-seq expression | `rnaseq_expression` |
| Analyze a bacterial isolate genome | `wgs_bacteria` |
| Quantify metatranscriptomic expression | `metatranscriptomics` |
| Profile shotgun metagenomic reads | `easymetagenome` |
| Identify and characterize viruses | `viral_viwrap` |
| Reconstruct and characterize plasmids | `metagenomic_plasmid` |

Use the installed environment as the source of truth:

```text
abi_list_types({})
abi_export_agent_context({"analysis_type": "rnaseq_expression"})
abi_query({"analysis_type": "rnaseq_expression", "what": "stages"})
abi_query({"analysis_type": "rnaseq_expression", "what": "tools"})
```

`abi_export_agent_context` returns the plugin description, standard tables, important artifacts, permissions, error codes, and recovery rules. Use it before constructing a plan.

Its `safe_sequence` field is a compact compatibility baseline. For a biological run, follow the expanded sequence below, including preflight checks and post-run result validation.

### 3. Prepare configuration and sample metadata

The Agent lifecycle tools accept paths; they do not invent biological metadata. Use an existing reviewed config and sample sheet, or initialize templates outside MCP with:

```bash
abi init --type rnaseq_expression --outdir my-analysis
```

The user or agent must replace placeholder paths and verify sample metadata. Keep source data read-only and write each attempt to a new result directory.

### 4. Plan, check, and dry-run

Use the same `analysis_type`, config, sample sheet, and output assumptions in every call:

```text
abi_plan({
  "analysis_type": "rnaseq_expression",
  "config_path": "my-analysis/config/rnaseq_expression.yaml",
  "sample_sheet": "my-analysis/samples.tsv",
  "outdir": "my-analysis/results/plan"
})

abi_check({
  "analysis_type": "rnaseq_expression",
  "config_path": "my-analysis/config/rnaseq_expression.yaml",
  "sample_sheet": "my-analysis/samples.tsv",
  "engine": "local",
  "check_runtime": true
})

abi_dry_run({
  "analysis_type": "rnaseq_expression",
  "config_path": "my-analysis/config/rnaseq_expression.yaml",
  "sample_sheet": "my-analysis/samples.tsv",
  "outdir": "my-analysis/results/dry-run"
})
```

Stop before execution if preflight reports missing inputs, tools, or resources. A successful dry-run proves that planning and command rendering work; it does not prove biological validity.

### 5. Present an approval summary

Before requesting execution approval, summarize:

- selected plugin and biological purpose;
- samples, platforms, groups, and contrasts;
- planned stages and key tools;
- references, databases, and unresolved warnings;
- runtime backend, output directory, and expected resource demand;
- the exact action that will cross the execution boundary.

Do not invent runtime or storage estimates. Report only estimates supplied by the plan, configuration, scheduler, or user.

### 6. Execute only after explicit approval

The default MCP `safe` profile does not expose `abi_run`. Start the full profile only when execution is needed:

```bash
abi-mcp --profile full
```

First call `abi_run` with `confirm_execution: false` to preserve the approval boundary. After the user explicitly approves the summarized plan, repeat the same request with `confirm_execution: true`.

```text
abi_run({
  "analysis_type": "rnaseq_expression",
  "config_path": "my-analysis/config/rnaseq_expression.yaml",
  "sample_sheet": "my-analysis/samples.tsv",
  "outdir": "my-analysis/results/run-001",
  "engine": "local",
  "confirm_execution": true
})
```

Approval applies only to the displayed plugin, inputs, configuration, output path, and runtime. Re-plan and ask again if any of them changes materially.

### 7. Validate and interpret the result

```text
abi_inspect({"result_dir": "my-analysis/results/run-001"})
abi_validate_result({"result_dir": "my-analysis/results/run-001"})
abi_report({
  "analysis_type": "rnaseq_expression",
  "result_dir": "my-analysis/results/run-001"
})
```

Read biological values from declared standard tables, not from ad hoc parsing of raw logs. Use provenance for methods and reproducibility, and use plugin reports for limitations and interpretation context.

The Agent should separate three conclusions: execution completed, result contracts passed, and biological acceptance criteria passed. None of these automatically proves the other two.

## Safe Sequence

1. `abi_list_types` — discover installed analysis plugins
2. `abi_export_agent_context` or `abi_doctor_agent` — get operating context
3. `abi_query` — lightweight metadata query (stages, tools, platforms, step I/O)
4. `abi_plan` — build the execution plan and review its `summary`
5. `abi_check` — preflight inputs, resources, executables, and runtime
6. `abi_dry_run` — write commands, provenance, table skeletons, and report preview
7. `abi_inspect` or `abi_validate_result` — verify the dry-run artifacts
8. Present the plugin, inputs, resources, runtime, output path, and warnings
9. `abi_run` — execute **only after explicit user approval**
10. `abi_inspect`, `abi_validate_result`, and `abi_report` — validate and interpret results

## Transport Methods

### CLI JSON (universal)

```bash
abi list-types --output-json
abi query --type metatranscriptomics --what stages --output-json
abi plan --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/agent-plan --output-json
abi check --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --no-check-runtime --output-json
abi dry-run --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/agent-dry-run --output-json
abi inspect --result-dir results/agent-dry-run --output-json
abi validate-result --result-dir results/agent-dry-run --allow-empty-tables --output-json
abi report --type metatranscriptomics --result-dir results/agent-dry-run --output-json
```

All commands return JSON envelopes with status `success`, `confirmation_required`,
or `error`.

For `abi check`, a successful transport envelope may contain `result.status: "fail"` and a non-zero CLI exit when preflight finds missing inputs or resources. Agents must inspect both status levels.

The bundled example contains placeholder reference paths. Use it for planning and dry-run only; configure real references before biological execution.

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
abi-mcp                  # safe profile (default)
abi-mcp --profile full   # includes abi_run
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

## `run` vs `dispatch`

Both execute real tools, but differ in invocation model:

| Aspect | `run` | `dispatch` |
|--------|-------|------------|
| Invocation | CLI command | HTTP endpoint (Job Service) |
| Blocking | Yes (synchronous) | Returns immediately (async) |
| Confirmation | `--confirm-execution` flag | Job queue with `confirm_execution` in payload |
| Progress | Inline progress bars / logs | `GET /jobs/{id}` polling |
| Cancel | Ctrl+C (SIGINT, best-effort) | `POST /jobs/{id}/cancel` (SIGTERM → SIGKILL) |
| Use case | Interactive agent calls | Long-running batch jobs, remote execution |

Prefer `run` for interactive sessions. Use `dispatch` when execution time exceeds
agent timeout or when running on remote machines via Job Service.

## Troubleshooting Common Failures

### Tool not found (`TOOL_NOT_FOUND`)

The tool executable is not on PATH. Check:

```bash
# Verify conda environment is activated
conda activate <env_name>

# Or list which tools are available
abi check-resources --type <analysis_type>
```

### Missing resource (`MISSING_RESOURCE`)

A required database or reference file is missing:

```bash
# See what's missing
abi check-resources --type <analysis_type>

# Install missing resources
abi setup-resources --type <analysis_type> --confirm
```

### Contract violation (`CONTRACT_VIOLATION`)

A tool's output didn't match the expected contract:

1. Check `provenance/step_logs/<step_id>.stderr.log` for tool errors
2. Verify input files exist and are not empty
3. Check if the tool version changed — output formats may differ
4. If the contract is too strict, adjust `min_size` or `assertions` in the tool contract

### Dry-run succeeds but real execution fails

1. Verify conda environments are installed: `ls envs/`
2. Check if required databases are downloaded: `abi check-resources --type <analysis_type>`
3. Ensure input FASTQ files exist and are readable
4. Check disk space and memory: some tools need 16GB+ RAM

### Permission denied

ABI enforces a 3-tier permission model:

- `read_only` operations (`list_types`, `query`, `inspect`) — always allowed
- `planning_write` operations (`plan`, `dry_run`, `report`) — write plans/provenance only
- `execution` (`run`) — **requires `confirm_execution=true`**

If `run` returns `confirmation_required`, re-invoke with `--confirm-execution`.

### Parallel execution not speeding up

Check `config.execution.parallel` and `config.execution.workers` in your config:

```yaml
execution:
  parallel: true
  workers: 8
```

Parallel execution is sample-level. Single-sample pipelines with few steps won't
benefit. Multi-sample pipelines will see near-linear speedup up to worker count.

## Golden Traces

Known-good agent call sequences are stored in `golden_traces/` and replayed by
`tests/integration/test_golden_traces.py`.
