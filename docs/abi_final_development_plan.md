# ABI Final Development Plan

This document is the repository-local frozen plan derived from `Rebuild.md`.
It keeps the implementation boundary explicit so future work does not drift
back into a single AutoPlasm CLI wrapper.

## Product Shape

ABI is delivered as:

- ABI Core
- Agent-facing tool layer
- Plugin SDK
- HTTP Job Service
- PyPI package: `abi-agent`

The Python import package remains `abi`, and the primary command remains `abi`.

## Architecture Rules

- Core is thick: plugin discovery, schemas, permissions, diagnostics,
  provenance, standard tables, contracts, execution planning, and reports live
  under `src/abi`.
- Transports are thin: CLI JSON, OpenAI descriptors, MCP, and HTTP jobs call
  `ABIAgentInterface` rather than reimplementing business logic.
- Plugins are clear: biological planning, parsing, tool contracts, standard
  tables, and reports belong to each analysis plugin.
- Agents do not need to import Python classes. They call CLI JSON, descriptors,
  MCP tools, or HTTP jobs.

## Built-In Plugins

- `metagenomic_plasmid`: AutoPlasm adapter and complex primary case.
- `metatranscriptomics`: lightweight portability demo using fastp,
  STAR/HISAT2, and featureCounts.

## Required Gates

The repository should keep these gates passing when the environment provides the
required tools:

```bash
pytest
ruff check src/abi tests
ruff format --check src/abi tests
mypy src/abi/ --ignore-missing-imports
python -m build
python -m twine check dist/*
```

## Evidence Artifacts

- Golden agent traces live in `golden_traces/`.
- Plugin manifests and tool contracts live in `plugins/*/`.
- Experiment scaffold lives in `docs/experiments/`.
- Demo output must contain `execution_plan.json`, `provenance/`, `tables/`,
  and `report/`.

## Current Development Status (2026-06-17)

### Completed ✅

| Phase | Description | Key Deliverables |
|-------|-------------|-----------------|
| **Phase 0** | 止血修复 (Bleeding Control) | unsafe_execution detection rewrite, claim threshold honesty (pre_registered vs revised), ablation downgrade to Appendix |
| **Phase 1** | DAG 可靠性工程 (DAG Reliability) | `WorkflowSpec`/`WorkflowStepSpec` dataclasses, `load_workflow_spec()`, `infer_dag()` L1/L2/L3 validation, all 5 plugins with `pipeline_dag.yaml` and workflow declarations |
| **Phase 4** | Benchmark 加固 (Benchmark Hardening) | 5 structured scoring checks (T01/T04/T08/T11/T12 keyword→JSON), pre_registered threshold tracking, 18 ABI-Bench tasks (T01-T18) |
| **Phase 5** | 生态扩展 (Ecosystem Expansion) | 3 new plugins: `rnaseq_expression` (4 tools), `amplicon_16s` (6 tools), `wgs_bacteria` (5 tools). 34 plugin tests. 5 fixtures. |

**Current metrics:**
- 5 plugins (1 flagship + 4 inline), all with `pipeline_dag.yaml` and workflow citations
- 86 tool contracts (67 + 4 + 6 + 5)
- 18 ABI-Bench tasks (T01-T18)
- 413 tests passing, 100% regression

### Suspended ⏸️ (2026-06-17)

The following phases from `plan_b_execution_plan.md` are documented but **not currently scheduled**:

#### Phase 2: Multi-LLM Experiments (Scaffolding Effect)

**Goal**: Validate the scaffolding hypothesis — weaker LLMs benefit more from the ABI control layer.

**Model matrix** (6+ models × 3 tiers):

| Tier | Models | Status |
|------|--------|--------|
| Strong | DeepSeek v4-pro, GPT-4o, Claude Sonnet 4 | DeepSeek data exists; GPT-4o + Claude not started |
| Medium | Qwen-72B, GPT-4o-mini, DeepSeek-v3 (optional) | Not started |
| Weak | Qwen-7B, DeepSeek-lite | Not started |

**Experiment matrix:**
```
Groups:   G1 (prompt-only), G2 (CLI+docs), G3 (full ABI)
Tasks:    MVP 8 tasks (T01-T03, T05-T06, T08-T10) or full 12
Replicates: 3 per condition
Total:   6 models × 3 groups × 8 tasks × 3 reps = 432 runs (~$200-300 API cost)
```

**Key analysis:**
- Mixed-effects model: Score ~ Group × ModelTier + (1|Task)
- Scaffolding Index: SI = (Weak_G3 − Weak_G1) − (Strong_G3 − Strong_G1)
- Bootstrap 95% CI + per-task effect sizes
- Hidden fixture re-run for T05/T06/T07 (162 additional runs)

**Success criteria:** Scaffolding effect significant (p < 0.05) in at least 1 weak/strong model pair.

**Fail-safe narrative** (if scaffolding effect absent):
"ABI benefit is consistent across model scales — the control layer addresses structural challenges in bioinformatics workflows independent of model capability."

#### Phase 3: Real Execution Demos

##### Demo A: metatranscriptomics End-to-End (2 weeks)

| Week | Content | Key Deliverables |
|------|---------|-----------------|
| Week 1 | Environment setup + human baseline | E. coli K-12 reference, STAR index, fastp/STAR/featureCounts installed. Manual baseline `gene_expression.tsv` |
| Week 2 | Fault injection + real execution | 2 fault-recovery traces (≤3 steps each). ABI output vs human baseline Pearson r ≥ 0.95 |

**Success criteria (5):**
- A1: Agent + ABI completes full lifecycle (provenance artifacts complete)
- A2: ≥2 config errors detected at dry-run stage
- A3: Agent fixes each error ≤3 steps
- A4: Pearson r ≥ 0.95 vs human expert
- A5: All provenance artifacts generated

##### Demo B: metagenomic_plasmid Sub-pipeline (4-5 weeks)

**Selected path:** fastp → assembly → geNomad → annotation → CoverM → plasmid_typing → statistics (6-8 tools)

| Phase | Week | Content |
|-------|------|---------|
| Phase 1 | 1 | Data download + DB setup (geNomad DB, annotation DB) |
| Phase 2 | 1 | Human expert baseline (manual execution of all tools) |
| Phase 3 | 1 | Fault injection (4 scenarios: missing_resource, missing_input, tool_not_found, compound) |
| Phase 4 | 1 | Real execution + result validation (≥90% overlap with human) |
| Phase 5 | 1 | Buffer + documentation |

**Success criteria (6):**
- B1: Agent completes 6-8 tool pipeline via ABI
- B2: ≥3 fault types correctly detected
- B3: Agent ≤3 steps per fault recovery
- B4: Output table structure matches human expert
- B5: Plasmid calls ≥90% overlap with human
- B6: All provenance artifacts complete

##### Demo D: Multi-Model Real Execution Comparison (3 weeks)

**Design:** Qwen-7B + ABI vs GPT-4o + ABI vs Human Expert on Demo B pipeline

**Hypothesis:** GPT-4o+ABI ≈ Human (≥95%), Qwen-7B+ABI ≥ Human (≥85%)

| Week | Content |
|------|---------|
| 1-2 | Reuse Demo B config, execute with Qwen-7B + GPT-4o |
| 3 | Cross-model comparison + case study material |

#### Phase 6: Data Analysis & Statistics (3 weeks)

**Pipeline:**
```bash
aggregate_scores.py → all_models_leaderboard.tsv + summary.json
claim_preflight.py  → preflight.json (all models)
compute_statistics.py → bootstrap CI + effect sizes + scaffolding index
```

**Output tables:** Leaderboard (Table 1), Per-task effects (Table 2), Model×Group interaction (Table 3), Failure taxonomy (Table 4), Cross-plugin comparison (Table 5), Case study summary (Table 6)

**Output figures:** Motivating example (F1), Architecture (F2), Score by group/model (F3), Scaffolding interaction (F4), Radar chart (F5), Efficiency (F6), Cross-plugin rates (F7), Human agreement scatter (F8)

#### Phase 7: Paper Writing (8 weeks)

| Week | Content |
|------|---------|
| 1-2 | Figures 1-8 production |
| 3 | §1 Introduction |
| 4 | §2 Related Work |
| 5 | §3 ABI Architecture |
| 6 | §4 ABI Design + Plugin System |
| 7 | §5 ABI-Bench Design |
| 8 | §6 Experiments + Case Study |
| 9 | Internal review (pre-submission-reviewer) |
| 10 | Revisions + final polish |

**Target venues:** ISMB 2027 (primary) → Bioinformatics (Oxford) (backup) → PLOS Comp Bio (safety)

### Active Tasks (for current sprint)

- [ ] `abi contract-lint --strict` command (DAG/contract static validation — CLI entry point exists, strict mode TBD)
- [ ] Review `docs/pipeline_biological_validity.md` §1 (metagenomic_plasmid) for user-flagged issues
- [ ] Fix any regressions from multi-plugin expansion if not covered by existing tests

### Blocked / Dependencies

| Blocker | Blocks | Resolution |
|---------|--------|------------|
| Phase 2 (multi-LLM experiments) | Phase 6 (statistics), Phase 7 (paper) | Requires API budget + experiment time (~$200-350, 6-8 weeks) |
| Phase 3 (real execution demos) | Phase 6 (case study tables), Phase 7 (paper) | Requires compute resources (databases 20-50 GB, 16+ GB RAM for assembly) |
| Literature review completeness | Phase 7 (§2 Related Work) | Ongoing tracking of MCP/agent-tool papers |

### Reference

Full execution details: [plan_b_execution_plan.md](plan_b_execution_plan.md)
Journal targeting analysis: [submission_strategy_analysis.md](submission_strategy_analysis.md)
Biological validity assessment: [pipeline_biological_validity.md](pipeline_biological_validity.md)
