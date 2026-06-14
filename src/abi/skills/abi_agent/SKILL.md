---
name: abi-agent
description: Use this skill when working with the ABI (Agent-Bioinformatics Interface) CLI for AI-driven bioinformatics analysis. Covers plugin discovery, planning, dry-run, execution, and result inspection. Use when the task involves running metagenomic plasmid analysis, metatranscriptomics, or any ABI-registered analysis type.
---

# ABI Agent Operator

Use this skill when the task involves the `abi` CLI for bioinformatics analysis. ABI is a **control plane** between AI agents and bioinformatics tools — it provides structured JSON envelopes, provenance tracking, and execution gating.

## Core Rule

Always preserve the ABI control path:

1. **Discover** available plugins.
2. **Plan** the execution.
3. **Dry-run** to validate commands and provenance.
4. **Inspect** provenance before real execution.
5. **Run** only after explicit user confirmation.
6. **Report** results from standard tables.

Do NOT hand-run bioinformatics tools directly. Always go through `abi` so that commands, provenance, and standard tables are recorded.

## CLI Invocation

ABI is installed via `pip install abi-agent`. The CLI entry point is `abi`:

```bash
abi --help
```

**For agent consumption, always use `--output-json`:**

```bash
abi <command> --output-json ...
```

This returns a JSON envelope with three possible statuses:
- `success` — `result` holds the payload
- `confirmation_required` — the operation needs user approval (used by `run`)
- `error` — `error_code` + `diagnostic_hints` guide automated recovery

## Lifecycle Commands

### Step 1: Discover installed plugins

```bash
abi list-types --output-json
# or
abi list --output-json
```

Returns `{"analysis_types": [{"analysis_type": "...", "name": "...", "description": "..."}], "count": N}`.

### Step 2: Get operating guide for a plugin

```bash
abi doctor-agent --type <analysis_type>
```

Prints a condensed operating guide. Paste this into your system prompt to understand the plugin's capabilities, standard tables, and safe call order.

### Step 3: Plan

```bash
abi plan \
  --type <analysis_type> \
  --config <config.yaml> \
  --sample-sheet <samples.tsv> \
  --outdir <output_dir> \
  --output-json
```

Writes `execution_plan.json` to the output directory. The plan encodes every step: tool_id, inputs, params, outputs.

### Step 4: Dry-run (safe validation)

```bash
abi dry-run \
  --type <analysis_type> \
  --config <config.yaml> \
  --sample-sheet <samples.tsv> \
  --outdir <output_dir> \
  --output-json
```

Renders all commands and provenance artifacts WITHOUT executing external tools. Every step is marked `dry_run` in the provenance. This is the safest way to validate a complete workflow.

### Step 5: Inspect provenance

```bash
abi inspect --result-dir <output_dir> --output-json
```

Reads `provenance/commands.tsv` and `provenance/resolved_inputs.tsv` to surface:
- Failed/skipped steps
- Missing or placeholder inputs
- Overall run status

### Step 6: Run (REQUIRES USER CONFIRMATION)

```bash
abi run \
  --type <analysis_type> \
  --config <config.yaml> \
  --sample-sheet <samples.tsv> \
  --outdir <output_dir> \
  --confirm-execution \
  --output-json
```

**CRITICAL**: Without `--confirm-execution`, the command returns `confirmation_required` status (exit code 2). This is a deliberate safety gate. Always present the confirmation prompt to the user before re-invoking with `--confirm-execution`.

### Step 7: Report

```bash
abi report --result-dir <output_dir> --output-json
```

Regenerates `report/report.md` and `report/report.html` from existing results.

## Transport Methods

ABI supports four transport layers for agent integration:

### 1. CLI JSON (most universal)
Use `abi <command> --output-json`. Works with any agent that can run shell commands.

### 2. MCP Server (Claude Desktop / Claude Code native)
```bash
abi-mcp
# or: python -m abi.mcp.server
```
Registers all ABI tools as MCP tools. Configure in Claude Desktop `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "abi": {
      "command": "abi-mcp"
    }
  }
}
```

### 3. OpenAI Tools export
```bash
abi export-openai-tools --type <analysis_type> --format responses
```
Generates OpenAI-compatible function definitions for use with the `tools` parameter.

### 4. HTTP Job Service
```bash
abi job-service                    # Start the server
abi job submit --command dry-run ...  # Submit a job
abi job status --job-id <id>       # Check status
```

## Important Output Files

After a run, always reference these canonical artifacts:

| Path | Purpose |
|------|---------|
| `execution_plan.json` | The full execution plan |
| `provenance/commands.tsv` | All commands with status (success/failed/skipped) |
| `provenance/resolved_inputs.tsv` | All resolved input paths |
| `provenance/tool_versions.tsv` | Tool versions used |
| `provenance/run_summary.json` | Overall run summary |
| `provenance/step_logs/*.log` | Per-step stdout/stderr logs |
| `tables/*.tsv` | **Standard result tables** (READ THESE for results) |
| `report/report.md` | Human-readable report |
| `report/report.html` | HTML report |

**Always read `tables/*.tsv` for structured results.** Never parse raw tool stdout.

## commands.tsv Status Values

- `dry_run` — planned, not executed
- `success` — external command returned 0
- `failed` — command returned non-zero or could not run
- `skipped` — planner intentionally skipped this step

## Error Recovery

When a command fails:

1. Find the first `failed` row in `provenance/commands.tsv`
2. Read its `reason` and `return_code`
3. Check the matching stderr log under `provenance/step_logs/`
4. Verify inputs, database paths, and executable paths exist
5. Fix config or sample sheet
6. Re-run `plan` and `dry-run` before re-executing

Check the `error_code` and `diagnostic_hints` in the JSON error envelope for automated recovery suggestions.

## Available Analysis Types

ABI ships with two built-in plugins:

| Type | Name | Description |
|------|------|-------------|
| `metagenomic_plasmid` | Metagenomic Plasmid Analysis | Plasmid detection, annotation, abundance from metagenomic assemblies |
| `metatranscriptomics` | Metatranscriptomics | RNA-seq quantification with fastp/STAR/HISAT2/featureCounts |

Third-party plugins installed via pip are auto-discovered via entry points.

## Config File Locations

For `metagenomic_plasmid`, config defaults and templates are at:
- Config templates: `<abi_package>/plugins/metagenomic_plasmid/config_default.yaml`
- Sample sheet template: `<abi_package>/plugins/metagenomic_plasmid/sample_sheet_template.tsv`

Use `abi init --type <analysis_type> --outdir <workspace>` to scaffold a workspace from templates.

## Common Recipes

### Minimal exploration
```bash
abi list-types --output-json
abi doctor-agent --type metagenomic_plasmid
```

### Dry-run validation
```bash
abi dry-run \
  --type metagenomic_plasmid \
  --config config/my_project.yaml \
  --sample-sheet samples.tsv \
  --outdir results/my_project \
  --output-json
```

### Real execution (after user confirmation)
```bash
abi run \
  --type metagenomic_plasmid \
  --config config/my_project.yaml \
  --sample-sheet samples.tsv \
  --outdir results/my_project \
  --confirm-execution \
  --output-json
```

### Post-mortem inspection
```bash
abi inspect --result-dir results/my_project --output-json
abi report --result-dir results/my_project --output-json
```

### Export for HPC/cloud (Nextflow)
```bash
abi export-nextflow \
  --type metagenomic_plasmid \
  --config config/my_project.yaml \
  --output workflow.nf
```

## Resource Management

```bash
# Check if required databases/models exist
abi check-resources --type metagenomic_plasmid --config config/my_project.yaml

# Download/mock resources
abi setup-resources --type metagenomic_plasmid --config config/my_project.yaml
```

## Boundaries

- Dry-run proves planning and command rendering ONLY. It does NOT produce biological results.
- Do NOT delete user outputs as a recovery tactic.
- Do NOT treat globally installed tools as satisfying plugin requirements — plugins use their own mamba/conda environments.
- `confirmation_required` is NOT an error — it is the safety gate. Always prompt the user.
