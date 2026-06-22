---
name: full-engineering-gap-audit
description: "Comprehensive engineering gap audit of entire ABI codebase — 2026-06-22. 10 dimensions: exports, tools/DAG/resources, parsers, protocols, configs, schemas, executor, contracts, DAG planner, TSV mapping, provenance, permissions, diagnostics, timeouts, static analysis, tests, docs, CLI/agent, sciplot, imports."
metadata: 
  node_type: memory
  type: project
  originSessionId: ab8752e5-48b4-43e1-ad54-fbe615506d33
---

# ABI Full Engineering Gap Audit — 2026-06-22

Comprehensive audit of the entire ABI codebase: implementation vs definition vs documentation
consistency. 3 parallel audit agents + direct exploration. 59 total findings across all layers.

**Why:** Code declares contracts, schemas, exports, and interfaces that don't match what the
implementation delivers. Three independent audit agents confirmed scattered gaps across all
layers with no automated cross-reference validation in CI.

**How to apply:** Fix CRITICAL items first (timeout wiring, query SSOT, lineplot renderer,
permissions enforcement), then systematically address HIGH items before next release.

## Remediation status — 2026-06-22

This document is the discovery snapshot; the implementation now supersedes the
open counts below.

- All 9 CRITICAL findings are resolved: timeouts and permissions are enforced,
  platform detection covers hybrid/HiFi, query and validation tools are in the
  descriptor SSOT, lineplot renders, parallel results/step IDs are retained,
  and `analysis_status` was confirmed to be live (not dead) with regression tests.
- All actionable HIGH findings are resolved. Registry/DAG/contract/environment
  tool sets are CI-cross-validated; setup-resources covers all five plugins;
  missing standard-output parsers were added; diagnostics, list-valued DAG
  edges, schema SSOT, docs, and colormap handling were corrected.
- Executor contracts from every declarative DAG now survive planning and execute
  at runtime. Contract declarations are statically linted, assertions reject
  unknown names without evaluating YAML, checksum writes are atomic, and strict
  L1/L2 workflow validation is exercised in CI for inline plugins.
- Actionable medium/low implementation gaps were corrected and regression-tested.
  Items that described intentional behavior are documented by tests:
  Nextflow populates scheduler IDs while local rows remain empty; intermediate
  mapping/report tools need no standard-table parser; `None` overrides are
  deliberately omitted by `compact_overrides`; optional resource downloads that
  require organism/database choices report `manual_required` rather than guessing.

Verification after remediation: **822 passed, 13 skipped** in the main suite,
**67.95% coverage** against the 60% floor, **40 passed** in SciPlot, zero Ruff
findings, and zero contract-lint errors or
warnings across all five plugins.

---

## Executive Summary

| Dimension | CRITICAL | HIGH | MEDIUM | LOW | Total |
|-----------|----------|------|--------|-----|-------|
| D1. Export/Interface Gaps | 0 | 0 | 6 | 3 | 9 |
| D2. Tool/DAG/Resource Gaps | 0 | 3 | 5 | 3 | 11 |
| D3. Parser Coverage Gaps | 0 | 3 | 2 | 0 | 5 |
| D4. Plugin Protocol Gaps | 0 | 0 | 2 | 1 | 3 |
| D5. Config/Schema Gaps | 1 | 3 | 6 | 3 | 13 |
| D6. Executor Gaps | 1 | 3 | 4 | 0 | 8 |
| D7. DAG Planner Gaps | 1 | 3 | 3 | 2 | 9 |
| D8. Contracts/DAG/TSV/Provenance Gaps | 0 | 5 | 9 | 9 | 23 |
| D9. Permissions/Diagnostics/Timeouts Gaps | 3 | 3 | 6 | 3 | 15 |
| D10. Static Analysis Gaps | 0 | 0 | 0 | 1 | 1 |
| D11. Test Coverage Gaps | 0 | 0 | 1 | 2 | 3 |
| D12. Documentation Gaps | 0 | 1 | 1 | 1 | 3 |
| D13. CLI/Agent Interface Gaps | 2 | 1 | 5 | 8 | 16 |
| D14. Sciplot Gaps | 1 | 1 | 3 | 2 | 7 |
| D15. Import/Module Gaps | 0 | 0 | 1 | 1 | 2 |
| **TOTAL** | **9** | **26** | **54** | **39** | **128** |

---

## 🔴 CRITICAL (9 findings)

### C1. Timeout constants never wired into tool execution
`DEFAULT_TOOL_TIMEOUT_SECONDS` and `DEFAULT_RESOURCE_TIMEOUT_SECONDS` are defined in
`src/abi/timeouts.py:8-9` but NEVER imported or used in `src/abi/executor.py:683` where
`skill.run(params, dry_run=False)` is called. Every tool executes with no timeout limit.

### C2. `detect_platform()` does not detect `hybrid` or `pacbio_hifi`
`src/abi/dag_planner.py:523-560`. PacBio samples are misdetected as ONT; hybrid samples
fall through to `illumina`. These platforms can ONLY be used when explicitly set in the
sample sheet. The `VALID_PLATFORMS` includes them but detection has zero logic for them.

### C3. Permissions module not wired into agent dispatch
`src/abi/permissions.py:127-157` vs `src/abi/agent/interface.py:610-670`. The 3-tier
permission system (READ_ONLY / PLANNING_WRITE / EXECUTION) exists in code but is NEVER
called during tool dispatch. Adding a tool to `TOOL_PERMISSIONS` has NO effect on
enforcement. The `confirm_execution` check is done manually in `_run()` — not through
`requires_confirmation()`.

### C4. `query` tool missing from `ABI_AGENT_TOOLS` SSOT
`src/abi/tool_descriptors.py:127-256`. The `query` method exists on `ABIAgentInterface`,
has a CLI command, has `TOOL_ALIASES` — but is NOT in `ABI_AGENT_TOOLS`. Invisible to
MCP server and ALL exporters (OpenAI, Anthropic, Gemini, JSON). Agents cannot discover it.

### C5. `autoplasm_validate_result` missing from `ABI_AGENT_TOOLS`
Same SSOT gap. Only manually registered in MCP server, invisible to LLM exporters.

### C6. `lineplot` declared but no renderer implementation
`src/abi/sciplot/schema/figure_spec.py:32`. `lineplot` is in `SUPPORTED_FIGURE_TYPES`
and `MatplotlibRenderer.SUPPORTED_TYPES` but has NO renderer file and NO entry in
`PLOT_FUNCTIONS`. Any `FigureSpec` with `figure_type: "lineplot"` passes validation
then crashes at render time with `"No plot function for 'lineplot'"`.

### C7. `analysis_status` table — dead schema in metagenomic_plasmid
Declared in both `standard_tables.yaml` and `TABLE_SCHEMAS` with 7 columns but NO parser
and NO normalizer anywhere in the codebase writes to it. 100% dead schema.

### C8. `_last_step_id` not updated in parallel execution path
`src/abi/executor.py:280-343`. When an exception escapes `_execute_step` in parallel
mode, `_last_step_id` is `"unknown"` — error messages lose traceability.

### C9. `_run_sample_chain` returns always-empty list
`src/abi/executor.py:320`. The function creates `results: List[tuple] = []` but NEVER
appends to it. Real data is collected via side effects on shared mutable state.

---

## 🟠 HIGH (26 findings)

### Schemas

**H1.** `PlanStep.reason` never populated by universal DAG planner — `dag_planner.py:676,730`.
The legacy metagenomic planner did set it; this is a regression for all plugins using
`build_plan_from_dag()`.

**H2.** `PlanStep.skipped` never set by DAG planner. Optional nodes are excluded by omission
rather than marked skipped — no record of "why was this node excluded" survives.

**H3.** `SampleInput.ensure_parent()` is dead code — `schemas.py:501-517`. Defined,
re-exported by metagenomic_plasmid, but zero call sites exist anywhere.

### Executor

**H4.** Race condition on `self._checksums` in parallel mode — `executor.py:762,775`.
`_run_external_step` mutates `self._checksums` and calls `save_checksums_atomic`
WITHOUT holding `_state_lock`. Two worker threads can concurrently read-modify-write.

**H5.** `remote_scheduler_job_id` column in commands.tsv never populated — `executor.py:599-610`.
Every row has an empty cell. Field only meaningful for Nextflow/HPC runtimes.

**H6.** `write_methods_md` is dead code — `provenance.py:265-361`. Full implementation,
exported in `__all__`, but zero call sites anywhere.

### DAG Planner

**H7.** Cross-sample `sample_id` set to `"ALL"` instead of `None` — `dag_planner.py:732`.
Schema contract says `None` for project-level steps. Downstream code checking
`sample_id is None` will miss cross-sample steps.

**H8.** Single-sample aggregation produces scalar, multi-sample produces list — type
mismatch at `dag_planner.py:864-867`. Downstream tools expecting a list receive a
string for single-sample projects.

### Tool/DAG/Resource

**H9.** 11 phantom tools registered but unreachable from DAG (see D2 above).

**H10.** 43/65 DAG tools in metagenomic_plasmid have NO ResourceSpec.

**H11.** No setup_resources for wgs_bacteria and metatranscriptomics plugins.

### Parser Coverage

**H12.** amplicon_16s: 4 DAG tools (`vsearch_otu`, `phylogeny_combine`, `phylogeny_mafft`,
`phylogeny_tree`) return `{}` from parse_outputs.

**H13.** rnaseq_expression: `build_count_matrix` returns `{}` despite producing output files.

**H14.** metagenomic_plasmid: `bowtie2`, `samtools`, `report_markdown` in core_contracts
but have NO parsers.

### Contracts/DAG/Provenance

**H15.** No `contract_violation` error code in diagnostics taxonomy — `diagnostics.py:84-99`.
`ContractViolationError` falls through to `internal_error`.

**H16.** Lists as input values silently dropped in DAG L2 inference — `dag.py:270-281`.
Cross-sample aggregation steps lose dataflow edges entirely.

**H17.** `write_methods_md` dead code (duplicate of H6, different module).

**H18.** `enrichment_results` table in rnaseq — declared but never produced.

**H19.** `standard_tables.yaml` in metagenomic_plasmid NEVER read at runtime — plugin reads
from `TABLE_SCHEMAS` Python module. YAML file is dead weight that can silently diverge.

### Permissions/Diagnostics

**H20.** Docstring says fallback is `PLANNING_WRITE` but code returns `READ_ONLY` —
`permissions.py:51-52 vs :139`. Code is safer than documented but doc is misleading.

**H21.** No `contract_violation` error code (duplicate of H15, cross-module impact).

**H22.** `_extract_path` missing key bioinformatics extensions (`.fasta`, `.fastq`, `.bam`,
`.sam`, `.gff`, `.csv`, `.html`, `.pdf`) — `diagnostics.py:383-402`.

### Documentation

**H23.** `abi.plugins.my_analysis` referenced in docs but doesn't exist — template name
never renamed.

### CLI/Agent

**H24.** `export-openai-tools --format` limited to legacy OpenAI sub-formats. New
`export-tools` command supports Anthropic/Gemini but no cross-reference in help text.

### Sciplot

**H25.** Palette/colormap confusion — adapter uses matplotlib colormap names (`"viridis"`,
`"RdBu_r"`) as sciplot palette names. These are NOT the same namespace.

### Plugin Internals

**H26.** amplicon_16s `core_contracts` severely mismatched vs DAG — missing `vsearch_mergepairs`,
uses legacy `phylogeny_build` instead of 3 actual DAG nodes.

---

## 🟡 MEDIUM (54 findings)

### Export gaps: 6 modules with phantom `__all__` exports
`src/abi/__init__.py` (`__version__`, `ABIAgentInterface`), `schemas.py` (11 old aliases),
`openai_contracts.py` (4 names), `tool_descriptors.py` (5 names), `diagnostics.py`
(`ERROR_CODES`), `permissions.py` (`TOOL_PERMISSIONS`), `contracts/__init__.py` (2 names),
`jobs/__init__.py` (5 names), `sciplot/__init__.py` (15 names).

### Schema gaps
- `ExecutionPlan.skipped_steps` always empty from DAG planner
- `ExecutionPlan.provenance_dir` set but executor ignores it and derives its own
- `VALID_PLASMID_STRATEGIES` defined in core schemas but never validated by core
- `SampleInput.to_dict()` includes `attributes` dict — may leak into input resolution
- `_contract` key in outputs could collide with user keys

### Config gaps
- wgs_bacteria: `typing.mlst_scheme` — dead config key
- metatranscriptomics: `analysis_type`, `dry_run`, `mock_tools`, `execution.progress` — dead
- All 4 inline plugins duplicate same config template (DRY violation)

### Executor gaps
- Tool stderr overwritten when `skill.run()` raises `ToolError` — original stderr lost
- Parallel fail-fast: `break` only stops current thread, others continue executing
- Timeout never passed to tool execution from config
- `PlanStep.outputs` dict may leak `_contract` key at runtime

### DAG Planner gaps
- `_CONFIG_SECTION_PARAMS` hardcoded for `deseq2` only — no extension mechanism
- `workflow.include_nodes` can silently produce empty active list
- Missing template variables: `pod5`, `bam`, `host_reference`, `notes` not exposed

### Contracts/DAG/TSV/Provenance
- `lint_resource_blocks` not called during plugin validation — only via CLI
- `contract:` key on outputs required but undocumented — silent skip otherwise
- L3 cross-validation only logs WARNING, not ERROR — easily lost
- `_is_shared_output_path` heuristic fragile for extensionless files
- `fasta_count` source type in TSV mapper documented but not implemented
- No numeric type coercion in TSV mapping — all values returned as strings
- Duplicate step logging: RunLogger + PipelineProgressRecorder write same events
- `write_minimal_progress_artifacts` falsy coercion bug for `sample_id`
- `StepBinding` "last occurrence wins" for duplicate tool_ids
- `save_checksums` (non-atomic) still public API alongside atomic version

### Permissions/Diagnostics/Timeouts
- `confirm_execution` checked manually, not through permissions module
- `internal_error` diagnostic message unactionable for agents ("report a bug")
- `command` parameter underused in diagnostics — could enhance hints
- `0` value means "disabled" not "zero timeout" in `parse_timeout_seconds`
- `mapping_block` utility misplaced in timeouts.py (belongs in config)
- Plugin tools not listed in `TOOL_PERMISSIONS`

### Plugin Protocol
- All 4 inline plugins missing `execute_dry_run` — `ABIDryRunPlugin` fails isinstance check
- All 4 have extra methods (`build_sample_context`, `root`) not in any Protocol

### Parser
- metagenomic_plasmid duplicate `parse_fastp()` instead of using `_parse_fastp` from `_shared`
- `_parse_sample_sheet_tabular()` in _shared.py never called — plugins have local copies

### CLI/Agent
- `install-skills --output-json` bypasses envelope contract — errors produce non-JSON stderr
- `install-skills` not accessible via MCP/HTTP — no ABIAgentInterface method
- MCP `_JSON_TO_PY_TYPE` mapping incomplete (only `string`, `integer`, `boolean`)
- Job service: `cancel_requested` undocumented intermediate status
- `error_envelope` diagnostic_hints don't include `command` context
- Skills README.md not installed alongside SKILL.md files

### Sciplot
- `write_plugin_report()` swallows ALL figure rendering exceptions (`except Exception: pass`)
- `abi.workflow.manifest` import may not exist at runtime
- `LabelSpec.legend_title` never populated by adapter
- `ProvenanceSpec.input_data_role` never displayed in any report output

### Test
- 4 smoke tests fail because `abi` CLI not on PATH
- Tests import from old `abi.autoplasm.*` paths

### Import
- `abi.sciplot` import fails in repo root (numpy source dir conflict)
- `_fetch_url_safe()` in _shared.py defined but never called

---

## 🟢 LOW (39 findings)

Minor issues including:
- `SampleInput.notes` populated but never read
- `RunLogger.log_event()` thread-safety claim overly optimistic for NFS
- No warning on non-standard platform values in `detect_platform`
- Absolute paths in StepBinding reduce Nextflow portability
- Assertion eval missing `round` from safe builtins
- `json_mapping` no recursive flattening beyond one level
- Whitespace stripping in key_value_log may lose structure
- Duplicate `write_tool_versions` in executor vs provenance
- Non-standard platform values silently trigger auto-detection
- Config `deep_merge()` cannot use `None` to unset defaults
- Non-dict handler results wrapped as `{"value": result}` — unpredictable shape
- Skills installation not fully atomic

---

## Root Causes

1. **No automated cross-reference validation.** Tool registries, DAG nodes, parsers,
   standard tables, `__all__` lists, `core_contracts`, permissions, and `ABI_AGENT_TOOLS`
   are maintained independently with no CI check that they agree.

2. **SSOT fragmentation.** `ABI_AGENT_TOOLS` is declared as SSOT but `query` and
   `autoplasm_validate_result` are missing, requiring manual MCP registration and
   TOOL_ALIASES workarounds.

3. **Timeout infrastructure built but disconnected.** `DEFAULT_TOOL_TIMEOUT_SECONDS`,
   `DEFAULT_RESOURCE_TIMEOUT_SECONDS`, and `parse_timeout_seconds` exist but are never
   wired into `executor.py`. Tools run with no time limit.

4. **Permissions module is documentation, not enforcement.** The 3-tier system is
   implemented but dispatch never calls it. Gating is done manually per-handler.

5. **Shared utilities underused.** `_parse_fastp`, `_clean`, `_common_overrides`,
   `_parse_sample_sheet_tabular` are duplicated in metagenomic_plasmid.

6. **Stale abi-plugin.yaml manifests.** `core_contracts` lists are outdated in 3/5 plugins.

7. **Platform detection incomplete.** `hybrid` and `pacbio_hifi` have NO auto-detection
   logic despite being in `VALID_PLATFORMS`.

## Related Memories

- [[tool-engineering-gap-audit]] — focused audit of tools/registry/DAG/resource gaps
