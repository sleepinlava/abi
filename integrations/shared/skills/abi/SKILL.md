---
name: abi
description: Use ABI to discover, plan, validate, execute, inspect, and report reproducible bioinformatics workflows. Use for sequencing, metagenomics, transcriptomics, plasmid, bacterial WGS, amplicon, and related bioinformatics analysis requests.
license: MIT
compatibility: Requires abi-agent with the MCP extra installed.
metadata:
  package: abi-agent
  interface: mcp
---

# ABI Bioinformatics Operator

ABI is a control plane for reproducible bioinformatics workflows. Use its lifecycle tools instead of composing or running bioinformatics commands directly.

## Required lifecycle

1. Call `abi_list_types` to discover installed analysis types.
2. Call `abi_export_agent_context` for the selected analysis type.
3. Use `abi_query` for lightweight questions about stages, tools, platforms, resources, inputs, or outputs.
4. Call `abi_plan` to resolve inputs and create an execution plan.
5. Call `abi_check` to validate inputs, resources, and the selected runtime.
6. Call `abi_dry_run` to render commands and provenance without executing real tools.
7. Review the plan and dry-run results with the user.
8. Execute only after explicit user approval.
9. Call `abi_inspect` and `abi_validate_result` before interpreting results.
10. Call `abi_report` to regenerate human-readable reports.

Do not skip directly from discovery to execution.

## Execution safety

The default ABI MCP profile is `safe` and does not advertise `abi_run`. If the user wants real execution, explain that the MCP server must be started with `--profile full`.

Even under the `full` profile, first call `abi_run` without confirmation or otherwise obtain explicit approval. Only after the user approves may you call it with `confirm_execution=true`.

Treat `confirmation_required` as a safety state, not an error. Never infer approval from earlier planning or dry-run requests.

Use the HTTP Job Service for work expected to outlive an interactive tool call. Submit the confirmed job, retain its job ID, poll status, and inspect artifacts after completion.

## JSON envelopes

Every ABI lifecycle tool returns a JSON string with one of these statuses:

- `success`: read the payload from `result`.
- `confirmation_required`: ask the user before continuing.
- `error`: inspect `error_code` and `diagnostic_hints`; do not parse traceback text first.

When correcting an error, update the config, sample sheet, resource mapping, or runtime selection, then repeat plan, check, and dry-run.

## Result interpretation

Prefer ABI's canonical artifacts:

- `execution_plan.json` for the resolved workflow.
- `provenance/commands.tsv` for step status and commands.
- `provenance/resolved_inputs.tsv` for concrete inputs.
- `provenance/tool_versions.tsv` for tool identity.
- `provenance/resources.json` for databases and models.
- `provenance/step_logs/` for failure investigation.
- `tables/*.tsv` for structured biological results.
- `report/report.md` and `report/report.html` for reporting.

Do not treat a successful dry-run as biological validation. Scientific conclusions require real outputs, configured resources, version evidence, and appropriate benchmark or quality checks.

## Operating rules

- Do not hand-run registered bioinformatics tools when ABI provides the workflow.
- Do not delete result directories as a recovery step.
- Do not read raw tool stdout as the primary result when standard tables exist.
- Do not claim a workflow or resource is available without checking ABI dynamically.
- Keep analysis paths explicit and prefer absolute paths when the agent platform may use a different working directory.
