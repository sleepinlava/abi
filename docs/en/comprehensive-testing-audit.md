# ABI Comprehensive Testing Audit Report

**Date**: 2026-06-22
**Auditor**: Automated multi-agent analysis
**Scope**: Full codebase — unit, integration, system, performance, security, user acceptance
**Baseline**: 750 collected tests, 742 passed, 4 failed (environment), 4 skipped

## Remediation status — 2026-06-22

This report is retained as the pre-remediation baseline. Its actionable
CRITICAL, HIGH, MEDIUM, and LOW engineering findings have been addressed or
converted into explicit environment-gated checks:

- Dedicated tests now cover `_shared.py`, plugin protocols, `results.py`, and
  the legacy figure engine.
- Adversarial traversal, malicious YAML, binary-parser fuzz cases, and real
  SIGTERM→SIGKILL escalation are tested.
- SciPlot now has API/CLI, adapter, lineplot, provenance, and all previously
  uncovered biological-renderer tests. It also imports lazily without the
  scientific rendering stack installed.
- Performance gates cover 100-sample planning, dry-run latency, and peak
  memory. Golden traces replay all five plugins.
- Opt-in real Docker execution and real-tool end-to-end smoke harnesses cover
  environment-dependent boundaries without downloading artifacts in CI.
- Report, agent-envelope, workflow-manifest, job-client, public-export, and
  compatibility-shim modules now have focused regression tests. Remaining
  observations in the baseline are scientific-validation or deployment-scale
  recommendations, not missing production code paths.

Current verification: `python -m pytest tests/ -q` reports **822 passed, 13 skipped**;
the coverage run reports **67.95%** against the 60% floor, and
`python -m pytest -q src/abi/sciplot/tests` reports **40 passed**. Skips are
explicit environment/tool gates, not collection failures.

---

## Executive Summary

ABI has a **solid, well-structured test suite** with 750 tests achieving a 99.5% pass rate. The testing pyramid is appropriately shaped: 33 unit test files (~6,500 lines), 14 top-level plugin/schema tests (~2,280 lines), 3 integration test files (~1,858 lines), and 8 smoke/benchmark tests (~1,916 lines). Four CI/CD workflows provide automated quality gates across 4 Python versions with linting, type-checking, coverage (≥60%), docs build, Docker image build, and wheel smoke-testing.

**Critical gaps** exist in three areas:
1. **28 source modules (~5,200+ lines) have zero dedicated test coverage**, including `figures/base.py` (586 lines — the entire FigureEngine), `_shared.py` (373 lines — 11 shared utilities used everywhere), `interfaces.py` (311 lines — plugin protocol contracts), and `results.py` (396 lines — result writing).
2. **No performance testing infrastructure whatsoever** — no benchmarks, no profiling, no memory leak detection, no stress/load tests, no large dataset handling tests.
3. **Security testing is incomplete** — no adversarial input tests (path traversal, injection), no fuzz testing, and subprocess force-kill is tested only via thread events, not actual signal delivery.

---

## 1. Test Infrastructure Assessment

### 1.1 Test Organization

```
tests/
├── conftest.py                    # 4 shared fixtures + tmp_path
├── unit/          (33 files)      # ~6,500 lines — module-level unit tests
├── integration/   (3 files)       # ~1,858 lines — CLI + dry-run + golden traces
├── smoke/         (8 files)       # ~1,916 lines — real-tool + benchmark tests
└── test_*.py      (14 files)      # ~2,280 lines — plugin/schema/sdk tests
```

**Rating: Good.** The three-layer structure (unit → integration → smoke) matches the testing pyramid. Each layer has a clear purpose and appropriate scope.

### 1.2 Fixture Quality

The single `conftest.py` (67 lines) provides 4 shared fixtures: `mock_sample`, `mock_sample_context`, `mock_contract_dict`, `tmp_project`. These are minimal but sufficient.

**Gaps:**
- No shared mock agents or test helpers exist in source (`src/abi/testing/` is present but only for benchmark assertions).
- 38 tool output fixtures under `tests/fixtures/tool_outputs/` are well-organized but are static files — no programmatic fixture generation for edge cases.
- Golden trace files (5 JSONL files) cover agent lifecycles but are hand-curated, not auto-generated from live sessions.

### 1.3 CI/CD Coverage

| Workflow | Trigger | Coverage |
|----------|---------|----------|
| `ci.yml` | push/PR to main/master | Lint + format + type-check + pytest + coverage + docs + wheel smoke-test |
| `release.yml` | `v*` tags | Lint + build + twine check + wheel smoke-test + GitHub Release |
| `docker.yml` | manual, tags, docker/envs/src changes | Build 5 Docker images (multi-arch) + smoke-test each |
| `publish-pypi.yml` | published release + manual | Build + publish to PyPI |

**Rating: Strong.** Four workflows cover the full delivery pipeline. Python 3.10–3.13 matrix is comprehensive. Docker multi-arch builds with provenance attestation and SBOM generation are production-grade.

---

## 2. Unit Testing Coverage Analysis

### 2.1 Well-Covered Modules

| Module | Source Lines | Test Lines | Ratio | Assessment |
|--------|-------------|------------|-------|------------|
| `tsv_mapping.py` | 446 | 527 | 118% | **Excellent** — tests exceed source |
| `tool_descriptors.py` | 693 | 908 | 131% | **Excellent** |
| `resources.py` | 484 | 449 | 93% | **Excellent** |
| `contracts/lint.py` | 539 | 408 | 76% | **Strong** |
| `provenance.py` | 901 | 556 | 62% | **Strong** |
| `jobs/service.py` | 1,397 | 754 | 54% | **Strong** |
| `dag_planner.py` | 1,113 | 588 | 53% | **Good** |
| `contracts/step_contract.py` | 961 | 527 | 55% | **Strong** |
| `cli.py` | 2,163 | ~1,400 | 65% | **Strong** (best-tested module) |

### 2.2 Modules with Zero Dedicated Test Coverage (HIGH severity)

| Module | Lines | Role | Risk |
|--------|-------|------|------|
| **`figures/base.py`** | 586 | FigureEngine, FigureSpec, rendering | **HIGH** — entire figure system untested |
| **`results.py`** | 396 | ABIResultWriter, result validation, report triggering | **HIGH** — core post-execution pipeline |
| **`_shared.py`** | 373 | 11 utility functions used by all plugins + core | **HIGH** — regression here breaks everything |
| **`interfaces.py`** | 311 | `ABIPlugin`, `ABIDryRunPlugin`, `ABIInitializablePlugin` protocols | **HIGH** — plugin contract foundation |
| `report/html.py` | 274 | HTML report writer | **MEDIUM** |
| `workflow/manifest.py` | 258 | Resource manifest generation | **MEDIUM** |
| `agent/context.py` | 190 | Agent context export | **MEDIUM** |
| `agent/envelopes.py` | 189 | JSON envelope construction | **MEDIUM** |
| `report/methods.py` | 196 | Methods section generation | **MEDIUM** |
| `report/citations.py` | 166 | Citation management | **MEDIUM** |
| `report/limitations.py` | 99 | Limitations section generation | **LOW** |
| `jobs/client.py` | 92 | HTTP client for job service | **LOW** |
| `workflow/figure_specs.py` | 88 | Figure spec loading | **LOW** |
| `errors.py` | 139 | Exception hierarchy | **LOW** (tested implicitly) |
| `openai_contracts.py` | 27 | OpenAI tool contracts | **LOW** |
| `filesystem.py` | 20 | Filesystem utilities | **LOW** |

### 2.3 sciplot Coverage Gaps

sciplot has **3 in-tree test files** (744 lines) under `src/abi/sciplot/tests/` but no external tests in `tests/`. Approximately 50% of sciplot modules are untested:

| Untested Module | Lines | Role |
|----------------|-------|------|
| `renderers/matplotlib_renderer.py` | 217 | Central renderer dispatcher |
| `adapters.py` | 203 | Data adapters |
| `cli.py` | 153 | CLI entry point (`abi-sciplot`) |
| `api.py` | 125 | Public API |
| `provenance/__init__.py` | 97 | SHA256 provenance tracking |
| `renderers/plots/pcoa_plot.py` | 174 | PCoA ordination plot |
| `renderers/plots/phylogenetic_heatmap.py` | 149 | Phylogenetic heatmap |
| `renderers/plots/differential_volcano.py` | 134 | Differential volcano plot |
| `renderers/plots/alpha_stats_boxplot.py` | 126 | Alpha diversity boxplot |
| `renderers/plots/phylum_stacked_bar.py` | 120 | Phylum stacked bar |
| `renderers/plots/genus_heatmap.py` | 92 | Genus heatmap |
| `renderers/plots/barplot.py` | 69 | Simple barplot |

**Total untested sciplot source: ~1,722 lines** (38% of sciplot).

### 2.4 autoplasm/ Backward-Compat Layer

The entire `autoplasm/` shim layer (39 files, 579 lines of boilerplate proxies) has **no dedicated test verifying the shim mechanism**. The proxy pattern (`sys.modules` manipulation) is exercised implicitly via plugin tests that import through `abi.autoplasm`, but the "does this shim actually redirect to the right engine module?" question is never directly tested.

**Risk: LOW** — the engine modules themselves are extensively tested, and any shim breakage would immediately manifest as import errors in the plugin test suite.

---

## 3. Integration Testing Assessment

### 3.1 Dry-Run Integration (`tests/integration/test_dry_run.py` — 1,184 lines)

The largest and most comprehensive integration test file. Covers:

| Test | Platform | Samples | Tools | Coverage |
|------|----------|---------|-------|----------|
| Basic dry-run | Assembly | 1 | fastp→unicycler→quast→genomad→abricate→coverm | Provenance + tables |
| Assembly full route | Assembly | 2 | quast→genomad→mob_typer→plasmidfinder→bakta→mob_suite | Multi-sample + parallel |
| Illumina mock run | Illumina | 1 | 13 tools (fastp→...→coverm) | Full Illumina pipeline |
| ONT mock run | ONT | 1 | nanoplot→filtlong→metaflye→...→coverm | Long-read pipeline |
| HiFi mock run | PacBio HiFi | 1 | hifiadapterfilt→hifiasm_meta→...→coverm | HiFi pipeline |
| Parallel execution | Assembly | 2 | ThreadPoolExecutor | Progress + ordering |

**Rating: Strong.** All four sequencing platforms (Illumina, ONT, PacBio HiFi, Assembly) are covered with end-to-end mock execution. Parallel execution is tested. Multi-sample scenarios are covered.

### 3.2 CLI Integration (`tests/integration/test_abi_cli.py` — 597 lines)

18 tests covering: dry-run, inspect, report, validate-result, export-nextflow, run (with/without confirmation), agent context export, doctor-agent, check/setup resources, JSON output wrapper, progress artifacts.

**Rating: Strong.** Comprehensive CLI coverage from the Typer `CliRunner` level.

### 3.3 Golden Trace Replay (`tests/integration/test_golden_traces.py` — 77 lines)

Replays agent lifecycle traces for metatranscriptomics and metagenomic_plasmid.

**Rating: Adequate.** Only 2 of 5 plugins have golden trace files that are actually replayed in tests (metatranscriptomics + metagenomic_plasmid). The other 3 (rnaseq_expression, wgs_bacteria, amplicon_16s) have trace files in `golden_traces/` but no dedicated replay test.

---

## 4. System / End-to-End Testing Assessment

### 4.1 Smoke Tests

| Test | Plugin | Type | Requires Tools |
|------|--------|------|---------------|
| `test_tool_smoke.py` | rnaseq_expression | Real tool execution with synthetic reads | Yes |
| `test_amplicon_smoke.py` | amplicon_16s | Real pipeline end-to-end | Yes |
| `test_dry_run_smoke.py` | All | Plan generation + DAG validation | No |
| 5 benchmark tests | All 5 plugins | Value-level output assertion | Yes |

**Rating: Good.** Real-tool smoke tests exist for 2 of 5 plugins (rnaseq_expression, amplicon_16s). The benchmark framework enables quantitative output validation (not just "did it run?" but "did it produce biologically plausible results?").

**Gap:** No real-tool smoke tests for wgs_bacteria, metatranscriptomics, or metagenomic_plasmid (plasmid has benchmark assertions but no end-to-end real execution smoke test in the smoke/ directory — the `test_plasmid_benchmark.py` tests run against pre-computed results).

### 4.2 Docker/Container Testing

- `tests/unit/test_container_runtime.py` (155 lines): Docker/Singularity command wrapping, image resolution, resource flags
- `tests/unit/test_hpc_runtime.py` (401 lines): HPC runtime configuration
- `tests/unit/test_nextflow_runtime.py` (121 lines): Nextflow runtime

**Gap:** No integration test that actually launches a Docker container and verifies tool execution inside it. All container tests are at the command-generation level, not the execution level.

### 4.3 Database/Resource Testing

`tests/unit/test_resources.py` (449 lines) provides strong coverage of resource discovery and setup. Integration tests verify `check-resources` and `setup-resources` CLI commands.

---

## 5. Security Testing Assessment

### 5.1 Permission Model: STRONG

- 8 dedicated tests in `tests/unit/test_permissions.py`
- Three-tier model (READ_ONLY / PLANNING_WRITE / EXECUTION) verified
- Unknown tools default to READ_ONLY (principle of least privilege)
- All registered tools validated against valid permission levels

### 5.2 Confirmation Gating: STRONG

- Tested at Python API layer (raises `ConfirmationRequiredError`)
- Tested at HTTP API layer (returns HTTP 409)
- Tested at CLI layer (exit code 2, structured JSON error)
- Both plain and JSON output modes verified

### 5.3 Checksum Validation: STRONG

- `tests/unit/test_step_contract.py` (527 lines) provides 20+ tests
- Covers: SHA256 computation, mismatched detection, missing files, atomic save, merge, invalidation, symlink following
- Checksum chaining across steps verified

### 5.4 Contract Enforcement: STRONG

- 25+ tests covering: file existence, min_size, extensions, contains, min_files, min_contigs, JSON schema, JSON required_keys
- Assertion evaluation with file_exists, comparison, and invalid expression handling
- Violation error formatting with structured diagnostics

### 5.5 Path Traversal Prevention: PARTIAL

Guards exist in 4 locations (`_shared.py`, `tools.py`, sample_sheet.py, nextflow.py) but **no adversarial tests** explicitly feed `../../etc/passwd` and assert rejection. The guards are tested indirectly through normal path resolution tests.

### 5.6 Injection Testing: MINIMAL

No tests for:
- SQL injection (not applicable — no SQL databases)
- Command injection (justified: subprocess calls use token lists, not shell strings)
- XSS (not applicable — no web UI)
- YAML deserialization attacks (relevant: config files are YAML)

### 5.7 Subprocess Force-Kill: PARTIAL

Cancel tested via threading events, not actual SIGTERM/SIGKILL delivery. No test verifies that a stuck subprocess is actually killed after the 3-second grace period.

---

## 6. Performance Testing Assessment

### 6.1 Current State: NONE

**ABI has zero performance testing infrastructure.** There are:

- No benchmark harness (no `pytest-benchmark`, no custom perf framework)
- No profiling scripts or configurations
- No memory leak detection tests
- No stress/load tests
- No large dataset handling tests
- No concurrent access / race condition tests beyond the single parallel execution test

### 6.2 What Exists

- `tests/unit/test_timeouts.py` (85 lines): Timeout parsing and configuration — this is correctness testing, not performance testing
- `tests/integration/test_dry_run.py::test_parallel_sample_run_writes_progress_and_ordered_commands`: Verifies parallel execution produces correct output, but does not measure throughput, latency, or resource utilization
- `data/benchmarks/`: 5 plugin benchmark configs with `expected_assertions.yaml` — these are **correctness assertions**, not performance benchmarks

### 6.3 Recommended Baseline

| Metric | Current | Recommended |
|--------|---------|-------------|
| Plan generation latency | Not measured | <5s for 100-sample plasmid plan |
| Dry-run throughput | Not measured | <30s for 100-sample dry-run |
| Per-tool execution overhead | Not measured | <500ms executor overhead per step |
| Memory usage (dry-run) | Not measured | <500MB for 100-sample plan |
| Parallel scaling efficiency | Not measured | >80% efficiency at 4 workers |
| Subprocess spawn latency | Not measured | <200ms per subprocess |

---

## 7. User Acceptance Testing Assessment

### 7.1 CLI Usability: ADEQUATE

- Basic CLI behavior tested (help text, required args, subcommand routing)
- 20+ CLI argument mappings validated in job service payload builder
- Error messages verified to mention required flags

**Gap:** No systematic usability testing — no test that a new user can complete the "5-minute quickstart" without errors, no test of error message clarity for common mistakes (typo in sample sheet, missing required column, wrong platform name).

### 7.2 Error Message Quality: ADEQUATE

- Structured error envelopes verified (status + error_code + diagnostic_hints)
- Contract violation messages include file paths and expected vs. actual values
- Timeout parsing errors include the invalid value

**Gap:** No catalog of all possible error messages, no test that each error message is actionable (tells the user what to do, not just what went wrong).

### 7.3 Documentation Testing: STRONG

- `tests/test_documentation_artifacts.py` (88 lines): Verifies 27 documentation paths exist in both English and Chinese
- CI builds Sphinx docs on every push
- PyPI distribution exclusions verified
- Release workflow smoke tests validated

### 7.4 Report Generation: ADEQUATE

- Markdown report generation tested (content verification: "Core Result Summary", "Assembly QC Summary", contig counts)
- HTML report generation tested (file existence)
- Progress tracking (progress.json + progress.jsonl) always written, verified in multiple scenarios

**Gap:** No test that report content is scientifically accurate — assertions check for string presence, not biological correctness of computed values.

---

## 8. Gap Severity Matrix

### CRITICAL (must fix — blocks production readiness)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| C1 | `_shared.py` (373 lines) has zero tests | Regression in any of 11 shared utilities breaks all 4 inline plugins | 4–6 hours |
| C2 | `interfaces.py` (311 lines) has zero tests | Plugin protocol contract violations not caught until runtime | 2–4 hours |
| C3 | `results.py` (396 lines) has zero tests | Post-execution result pipeline untested — silent data corruption possible | 4–6 hours |

### HIGH (should fix — significant risk)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| H1 | `figures/base.py` (586 lines) has zero tests | Entire FigureEngine untested — figure generation failures undetected | 6–8 hours |
| H2 | No adversarial path traversal tests | Guards exist but unverified — path traversal could succeed silently after refactoring | 2–4 hours |
| H3 | No subprocess SIGTERM/SIGKILL tests | Force-kill mechanism untested — zombie processes possible in production | 4–6 hours |
| H4 | sciplot ~1,722 lines untested (38%) | 7 of 14 plot types + API + CLI + adapters all untested | 8–12 hours |
| H5 | No performance baseline or regression detection | Performance regressions undetectable — cannot set SLAs | 8–16 hours |

### MEDIUM (should fix — moderate risk)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| M1 | `report/html.py`, `methods.py`, `citations.py`, `limitations.py` (735 lines total) have zero tests | Report generation failures undetected until user-facing output | 6–8 hours |
| M2 | `agent/context.py` + `agent/envelopes.py` (379 lines) have zero tests | Agent integration breakage undetected | 3–5 hours |
| M3 | `workflow/manifest.py` + `figure_specs.py` (346 lines) have zero tests | Resource manifest / figure spec loading untested | 3–5 hours |
| M4 | No real-tool smoke tests for wgs_bacteria, metatranscriptomics, metagenomic_plasmid | These 3 plugins lack end-to-end execution validation | 8–16 hours |
| M5 | Golden trace replay only for 2 of 5 plugins | Agent lifecycle regression undetected for 3 plugins | 2–4 hours |
| M6 | No Docker container execution integration test | Container wrapping verified but never actually executed | 4–6 hours |
| M7 | No fuzz testing framework | Edge case handling unverified for all input parsers | 4–8 hours |

### LOW (nice to have)

| # | Gap | Impact | Effort |
|---|-----|--------|--------|
| L1 | `jobs/client.py` (92 lines) has zero tests | HTTP client untested | 2–3 hours |
| L2 | `errors.py` (139 lines) tested only implicitly | Exception hierarchy not directly verified | 1–2 hours |
| L3 | `openai_contracts.py` (27 lines) has zero tests | Thin wrapper — low risk | 0.5 hours |
| L4 | `filesystem.py` (20 lines) has zero tests | Thin wrapper — low risk | 0.5 hours |
| L5 | autoplasm shim mechanism (579 lines) untested | Low risk — engine modules extensively tested | 2–3 hours |
| L6 | No large dataset stress tests | Performance with 100+ samples unknown | 8–16 hours |
| L7 | No systematic error message catalog | Error message quality varies | 4–8 hours |
| L8 | No concurrent access / race condition tests | Thread safety unverified beyond basic parallel test | 6–10 hours |

---

## 9. Recommendations

### Phase 1: Critical Coverage (Week 1–2)

1. **Write unit tests for `_shared.py`** — the 11 utility functions (`_read_tsv`, `_display_command`, `_plan_dict`, `_common_overrides`, `_clean`, `_resolve_path`, `_parse_fastp`, `_parse_star`) are the most reused code in the project. Test each with valid, edge, and error inputs.
2. **Write unit tests for `interfaces.py`** — create mock plugins that implement each protocol and verify the protocol contract is enforceable.
3. **Write unit tests for `results.py`** — test `ABIResultWriter` with mock plans and outputs, verifying all provenance artifacts are written correctly.

### Phase 2: Security Hardening (Week 2–3)

4. **Add adversarial path traversal tests** — feed `../../etc/passwd`, absolute paths, symlink escapes to `_resolve_path` and `_safe_output_path`, assert rejection.
5. **Add subprocess force-kill tests** — spawn a process that ignores SIGTERM, verify SIGKILL is delivered after grace period.
6. **Add YAML deserialization safety tests** — verify that malicious YAML (e.g., `!!python/object`) is rejected by the config loader.

### Phase 3: sciplot + Figures (Week 3–4)

7. **Write unit tests for `figures/base.py`** — test FigureEngine with valid/invalid FigureSpecs, verify rendering pipeline.
8. **Write unit tests for untested sciplot modules** — prioritize `matplotlib_renderer.py`, `adapters.py`, `api.py`, `cli.py`, and the 7 untested plot renderers.

### Phase 4: Performance Foundation (Week 4–6)

9. **Establish a performance baseline harness** — measure plan generation, dry-run, and per-step overhead for each plugin at 1/10/100 sample scales.
10. **Add CI performance regression detection** — fail if plan generation time increases >20% from baseline.
11. **Add memory profiling** — measure peak RSS during dry-run and run for each plugin.

### Phase 5: Completeness (Week 6–8)

12. **Fill remaining MEDIUM gaps** — report modules, agent modules, workflow modules, Docker integration tests.
13. **Add real-tool smoke tests for wgs_bacteria, metatranscriptomics, metagenomic_plasmid**.
14. **Add golden trace replay for rnaseq_expression, wgs_bacteria, amplicon_16s**.
15. **Add fuzz testing for TSV/JSON parsers** — generate malformed inputs and verify graceful error handling.

---

## 10. Test Suite Statistics

| Metric | Value |
|--------|-------|
| Total test files | 64 |
| Total test lines | ~14,372 |
| Total collected tests | 750 |
| Passed | 742 (99.5%) |
| Failed | 4 (environment: `abi` not on PATH) |
| Skipped | 4 |
| Unit test files | 33 |
| Integration test files | 3 |
| Smoke test files | 8 |
| Top-level test files | 14 |
| sciplot in-tree tests | 3 |
| Source modules with zero dedicated tests | 28 (~5,200 lines) |
| CI workflows | 4 |
| Python versions tested | 4 (3.10–3.13) |
| Coverage threshold (CI) | 60% |
| Docker images | 5 (multi-arch: amd64 + arm64) |
| Benchmark configurations | 5 plugins |

---

## 11. Conclusion

ABI's test suite is **production-grade for correctness** — 750 tests, 99.5% pass rate, comprehensive CI/CD, multi-platform integration coverage, and strong contract/security enforcement testing. The test architecture (unit → integration → smoke) is well-designed and appropriate for a bioinformatics control plane.

The primary gap is **test coverage completeness**: 28 source modules (~5,200 lines, or ~15% of the codebase) have no dedicated tests. The highest-risk untested modules are `_shared.py` (utilities used everywhere), `interfaces.py` (plugin protocols), `results.py` (result pipeline), and `figures/base.py` (figure engine).

The secondary gap is **performance testing**: the project has zero infrastructure for measuring, tracking, or regression-testing performance. For a tool that processes bioinformatics pipelines with potentially hundreds of samples, this is a significant blind spot.

Addressing the 3 CRITICAL and 5 HIGH gaps would bring the test suite to a **fully production-hardened state** suitable for academic publication and clinical research workflows.
