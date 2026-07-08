# ABI Plugin Production Manual Acceptance Checklist

This document is used for manual acceptance of ABI plugins before going live in a real production environment. The checks are categorized into the following two environments:

1. **Local IDE / General Machine Acceptance**: Verify configuration, plans, command rendering, path resolution, safety gates, mock/smoke, and artifact contracts.
2. **HPC / Production Platform Acceptance**: Verify real tools, real databases, schedulers, shared storage, performance, concurrency, and failure recovery.

> Passing local `dry-run`, `--mock`, or `--smoke` only proves that the software contracts and control flow are basically correct; it cannot substitute for real production runs on HPC, nor can it prove that biological results are correct.

## 1. Acceptance Scope

There are currently 7 built-in plugins:

```text
amplicon_16s
easymetagenome
metagenomic_plasmid
metatranscriptomics
rnaseq_expression
viral_viwrap
wgs_bacteria
```

It is recommended to create a separate acceptance record for each plugin, retaining at least the following information:

| Field | Content |
|---|---|
| Plugin | `<analysis_type>` |
| ABI Version | wheel version, Git commit |
| Acceptance Environment | Local/HPC, OS, node name |
| Configuration File | path and SHA-256 |
| Sample Sheet | path and SHA-256 |
| Database Version | name, version, date, checksum |
| Tool Version | tool, environment, actual executable path, version |
| Execution Command | complete CLI command |
| Tester | name |
| Test Time | ISO datetime |
| Result | Pass / Conditional Pass / Fail / Blocked |
| Evidence | logs, screenshots, output directory, issue tickets |

## 2. Acceptance Judgment Rules

- **Pass**: Actual results are fully consistent with expectations, with complete evidence.
- **Fail**: Incorrect results, unexpected side effects, undetected errors, or incomplete artifacts.
- **Blocked**: Unable to execute due to external network, scheduler, license, or database permission issues.
- **Not Applicable**: Must provide a reason; cannot be left blank.
- Any issue involving safety gates, incorrect real tool invocation, database misuse, or results that falsely appear successful is treated as a blocking defect.

---

# Part 1: Local IDE / General Machine Acceptance

## 3. Base Installation and Plugin Discovery

- [ ] **L-001** Run `abi --help`; the main command displays normally.
- [ ] **L-002** Run `abi list-types`; accurately returns 7 built-in plugins, no duplicates or omissions.
- [ ] **L-003** Run `abi list-types --output-json`; stdout is parseable plain JSON containing `status=success`.
- [ ] **L-004** Install the built wheel in a fresh Python 3.10 virtual environment, not just verify an editable install.
- [ ] **L-005** After wheel installation, `plugins/`, `config/`, `envs/`, examples, and maintenance scripts are all discoverable.
- [ ] **L-006** Start ABI with a read-only installation directory and confirm the runtime does not attempt to modify the package installation directory.
- [ ] **L-007** Unknown plugin IDs return a clear error and list available plugins.

Run for each plugin:

```bash
abi contract-lint --type <TYPE> --strict
abi query --type <TYPE> --what stages
abi query --type <TYPE> --what tools
abi query --type <TYPE> --what platforms
```

- [ ] **L-008** No DAG cycles.
- [ ] **L-009** No broken dependencies, illegal assertions, or tool registration inconsistencies.

## 4. `init` Workspace Initialization

```bash
abi init --type <TYPE> --outdir /tmp/abi-uat/<TYPE>
```

- [ ] **L-010** All 7 plugins generate a plugin configuration file and a `samples.tsv` sample sheet template.
- [ ] **L-011** File contents are consistent with plugin templates; paths are correct.
- [ ] **L-012** Re-executing without `--force` refuses to overwrite.
- [ ] **L-013** With `--force`, complete overwrite succeeds.
- [ ] **L-014** Explicit failure when the target directory is not writable.
- [ ] **L-015** No residual half-initialized files remain on init failure.
- [ ] **L-016** Chinese characters, spaces, and long paths are handled correctly.

### Current Implementation Status

All 7 built-in plugins now provide `sample_sheet_template.tsv`. Among them,
`amplicon_16s`, `metagenomic_plasmid`, and `viral_viwrap` templates have been supplemented; regression tests
L-010 through L-016 must be executed for each, not just spot-checking the original 4 plugins.

The main `abi init` performs a unified check of all source templates and overwrite conflicts before writing;
if any template is missing or a write fails, no half-initialized configuration or sample sheet shall remain.

## 5. `plan` Acceptance

```bash
abi plan \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --sample-sheet <SAMPLES.tsv> \
  --profile dry_run \
  --outdir /tmp/abi-uat/<TYPE>/plan \
  --log-dir /tmp/abi-uat/<TYPE>/logs \
  --output-json
```

### 5.1 Positive Checks

- [ ] **L-020** Exit code is 0; `execution_plan.json` is generated.
- [ ] **L-021** `analysis_type`, project name, sample count, thread count, mode, and output directory are correct.
- [ ] **L-022** Each step includes `step_id`, `tool_id`, inputs, parameters, outputs, and command.
- [ ] **L-023** Step IDs are unique; dependency graph has no cycles.
- [ ] **L-024** Upstream outputs are exactly consistent with downstream input paths.
- [ ] **L-025** All outputs are located within the configured `outdir`; no `../` escape.
- [ ] **L-026** Two consecutive generations with the same configuration are deterministically consistent except for allowed time-varying fields.
- [ ] **L-027** Thread, database, container, and resource parameters in commands are consistent with configuration.
- [ ] **L-028** CLI parameter overrides for configuration file parameters follow predictable priority.
- [ ] **L-029** Under `--check-files`, passes when inputs exist.
- [ ] **L-030** Under `--check-files`, fails when inputs do not exist.
- [ ] **L-031** `--no-check-files` can generate an offline plan, but the plan retains original input paths.
- [ ] **L-032** `--output-json` output is not interleaved with logs, progress bars, or warning text.

### 5.2 Plugin Branching Checks

- [ ] **L-033** `metagenomic_plasmid` separately validates Illumina, ONT, HiFi, Hybrid, and assembly-only.
- [ ] **L-034** When feature toggles are disabled, corresponding steps do not enter the execution plan and the skip reason is recorded.
- [ ] **L-035** Single-sample, multi-sample, grouped, and ungrouped scenarios produce correct branching.
- [ ] **L-036** `rnaseq_expression` generates count matrix and DESeq2 steps for multi-sample.
- [ ] **L-037** `amplicon_16s` steps change correctly when OTU clustering is enabled/disabled.
- [ ] **L-038** `easymetagenome` taxonomy/functional preset selects correct tools and databases.
- [ ] **L-039** `viral_viwrap` parameters are accurately passed to upstream ViWrap.

### 5.3 Invalid Input Checks

- [ ] **L-040** Fails when sample ID is missing.
- [ ] **L-041** Fails when sample IDs are duplicated.
- [ ] **L-042** Empty sample sheet or header-only is handled per plugin contract.
- [ ] **L-043** Fails when FASTQ pairing is incomplete.
- [ ] **L-044** Fails on illegal platform, illegal mode, and illegal YAML data types.
- [ ] **L-045** Illegal thread count, memory, walltime, accelerator, and container runtime produce clear errors.
- [ ] **L-046** Paths containing spaces, Chinese characters, parentheses, and symlinks do not cause incorrect command argument splitting.
- [ ] **L-047** Output path escape, read-only directories, and directories without permissions are rejected.

## 6. Tool Path Checks

Expected tool path resolution order:

1. Explicitly specified absolute path or path with directory component;
2. `$ABI_MAMBA_ROOT/<env>/bin`;
3. `$ABI_MAMBA_ROOT/envs/<env>/bin`;
4. System `PATH`.

- [ ] **L-050** After setting `ABI_MAMBA_ROOT`, confirm it has the highest priority.
- [ ] **L-051** When the environment variable is not set, check the repository `.mamba`.
- [ ] **L-052** When `.mamba` does not exist, check the sibling directory `abi-envs` fallback.
- [ ] **L-053** Record env name, executable name, and actual resolved path for each tool.
- [ ] **L-054** Actual file exists and passes `test -x <path>`.
- [ ] **L-055** Execute the tool version command; version meets the production baseline.
- [ ] **L-056** Place a fake tool with the same name on system `PATH`; confirm mamba environment tool takes priority.
- [ ] **L-057** Remove the tool from the environment; confirm system `PATH` fallback behavior is as expected.
- [ ] **L-058** Explicitly configuring a nonexistent tool path must report missing.
- [ ] **L-059** File exists but without execute permission must be judged as failure.
- [ ] **L-060** When dynamic libraries or interpreters are missing, it must not pass merely because the main file exists.
- [ ] **L-061** `provenance/tool_versions.tsv` records all actually used tools and their version status.

`metagenomic_plasmid` can run:

```bash
autoplasm check-tools --config <CONFIG.yaml>
```

### Current Implementation Status

All 7 built-in plugins have implemented input, tool, and resource preflight. Acceptance must still, on a per-plugin basis, manufacture missing inputs,
missing tools, and missing resources, and confirm a `fail` return code and non-zero exit code; do not conclude the runtime environment is ready based solely on a single `pass` result from a valid configuration.

Explicit tool path checks currently mainly verify file existence; execute permission checking is insufficient and must also be supplemented through manual checks.

## 7. `check` - Side-effect-free Preflight

```bash
abi check \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --sample-sheet <SAMPLES.tsv> \
  --engine local \
  --output-json
```

- [ ] **L-065** The command does not create outputs, download resources, or run analysis tools.
- [ ] **L-066** When inputs are missing, status is fail, exit code is non-zero.
- [ ] **L-067** When tools are missing, status is fail, not an empty-check pass.
- [ ] **L-068** When databases are not configured, missing, or have no permissions, actionable advice is given.
- [ ] **L-069** `--no-check-runtime` only skips runtime checks, not configuration and input checks.

## 8. `dry-run` Acceptance

```bash
abi dry-run \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --sample-sheet <SAMPLES.tsv> \
  --outdir /tmp/abi-uat/<TYPE>/dry-run \
  --log-dir /tmp/abi-uat/<TYPE>/logs \
  --output-json
```

- [ ] **L-070** Does not invoke any real bioinformatics tools.
- [ ] **L-071** Does not download databases or modify existing databases.
- [ ] **L-072** All planned step statuses are `dry_run`; must not be forged as real `success`.
- [ ] **L-073** Command content is complete; input, output, and database paths are expanded.
- [ ] **L-074** Generates `execution_plan.json`.
- [ ] **L-075** Generates `provenance/commands.tsv`.
- [ ] **L-076** Generates `provenance/resolved_inputs.tsv`.
- [ ] **L-077** Generates `provenance/tool_versions.tsv`; under dry-run, version status is `not_captured`.
- [ ] **L-078** Generates `resources.json` and `resource_manifest.json`.
- [ ] **L-079** Generates `config.resolved.yaml` and `environment.yml`.
- [ ] **L-080** Generates `run_summary.json`, `progress.json`, and `progress.jsonl`.
- [ ] **L-081** Generates standard tables and report directory.
- [ ] **L-082** In `run_summary.json`, `dry_run=true`; step count matches plan.
- [ ] **L-083** Step order in `commands.tsv` is consistent with the plan.
- [ ] **L-084** `inspect` can identify `NOT_CONFIGURED` and missing inputs.
- [ ] **L-085** `validate-result --allow-empty-tables` passes.
- [ ] **L-086** `validate-result --require-nonempty-tables` fails for empty dry-run tables.
- [ ] **L-087** CPU, memory, walltime, accelerator, and container parameters enter commands or exported workflows.
- [ ] **L-088** Compare database directory digest before and after dry-run; confirm no file changes.

## 9. Database Path Detection and Usage

```bash
abi check-resources \
  --type <TYPE> \
  --config <CONFIG.yaml>
```

### 9.1 General Status

- [ ] **L-100** `NOT_CONFIGURED`, `TODO`, `PLACEHOLDER` return `not_configured`.
- [ ] **L-101** Nonexistent paths return `missing`.
- [ ] **L-102** An empty directory must not be misjudged as a complete database.
- [ ] **L-103** A path with content but incomplete structure returns `incomplete` or `invalid`.
- [ ] **L-104** A complete database returns `ok`.
- [ ] **L-105** Relative paths, absolute paths, and symlinks are resolved correctly.
- [ ] **L-106** Path exists but is not readable by the current user: fail.
- [ ] **L-107** Custom paths appear in `execution_plan.json`, `commands.tsv`, and resource provenance simultaneously.
- [ ] **L-108** Planned paths are consistent with paths used in actual tool commands.
- [ ] **L-109** Database version, date, source, and checksum/fingerprint are recorded.
- [ ] **L-110** `--resource <ID>` returns only the specified resource.

### 9.2 Plugin Resource Matrix

| Plugin | Required Resources | Content-Level Checks |
|---|---|---|
| `amplicon_16s` | `taxonomy_db`, `phylogeny_tree`, `diversity_script` | taxonomy FASTA must have `;tax=` annotation |
| `easymetagenome` | `host_db`, `kraken2_db`, HUMAnN nucleotide/protein, MetaPhlAn DB | Run upstream database check commands |
| `metagenomic_plasmid` | 30 databases, models, and external tool resources | provider file structure, ready sentinel, version metadata |
| `metatranscriptomics` | STAR `genome_index`, `annotation_gtf` | STAR index structure, GTF readability |
| `rnaseq_expression` | `genome_index`, `annotation_gtf`, Rscript/DESeq2 | `library(DESeq2)` succeeds and records version |
| `viral_viwrap` | `db_dir`, `conda_env_dir`, ViWrap executable | ViWrap upstream full environment check |
| `wgs_bacteria` | `amrfinder_db` | AMRFinderPlus database structure and version |

`metagenomic_plasmid` current resource breakdown:

- `check-resources` should report all 30 resources.
- Default `setup-resources --dry-run` includes only 14 automatic resources.
- Level 2 resources should only enter the install plan when explicitly specified via `--resource`.

## 10. Database Download and Installation Safety Gates

```bash
abi setup-resources \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --resource <RESOURCE_ID> \
  --dry-run

abi setup-resources \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --resource <RESOURCE_ID> \
  --mock \
  --dry-run
```

- [ ] **L-120** dry-run returns `planned`, target path, source, and complete command.
- [ ] **L-121** dry-run does not create the download directory or ready sentinel.
- [ ] **L-122** Real install without `--confirm` exits with code 2.
- [ ] **L-123** `--resource` processes only the specified resource.
- [ ] **L-124** `--mock` output includes boolean field `mock: true`; regular dry-run includes
  `mock: false`. `--mock --dry-run` must not create resources and must be clearly distinguishable from real resource
  dry-run via this field.
- [ ] **L-125** Production configuration must not accept mock/synthetic resources.
- [ ] **L-126** Already-completed resources show skipped on re-install; do not re-download.
- [ ] **L-127** Incomplete directories must not be overwritten; should return `incomplete`.
- [ ] **L-128** Download timeout, network interruption, and insufficient disk return failed/error.
- [ ] **L-129** Failed downloads must not write a ready sentinel.
- [ ] **L-130** After download success, perform content-level ready check, not just directory existence.
- [ ] **L-131** Environment variables such as `GTDBTK_DATA_PATH`, `CHECKM2DB` point to configured paths.
- [ ] **L-132** Resource manifest records version, source, date, checksum, and file count.
- [ ] **L-133** Small resources are checkable and reusable after real download.

### Current Implementation Status and Known Risks

Resource setup return lines have been unified to include the `mock` boolean field; `metagenomic_plasmid`'s
`ResourceStatus` and resource manifest also record this field. L-124 must cover all 7 plugins and also compare target
paths before and after execution to confirm that `--mock --dry-run` did not write directories or sentinels.

When 16S RDP download fails, the current implementation may generate a synthetic fallback. Production acceptance must treat `fallback` as failure and must not use synthetic databases for real analysis.

Some generic resource checks currently mainly verify `Path.exists()`. Directory existence does not mean the database is complete, readable, or usable by tools; therefore, real minimal queries must be executed on HPC.

## 11. Local Smoke Run

First verify the execution confirmation gate:

```bash
abi run --type <TYPE> --config <CONFIG.yaml> --smoke
```

- [ ] **L-140** Without `--confirm-execution`, exit code is 2.
- [ ] **L-141** Returns `confirmation_required`.
- [ ] **L-142** Does not invoke tools or produce real analysis results.

Execute after confirmation:

```bash
abi run \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --smoke \
  --confirm-execution \
  --outdir /tmp/abi-uat/<TYPE>/smoke
```

- [ ] **L-143** Smoke run succeeds without invoking real tools.
- [ ] **L-144** `commands.tsv`, standard tables, report, and summary are complete.
- [ ] **L-145** `inspect` shows no failed steps.
- [ ] **L-146** `validate-result --allow-empty-tables` passes.
- [ ] **L-147** Deleting a required artifact causes validation to fail.
- [ ] **L-148** Modifying a standard table header causes schema validation to fail.
- [ ] **L-149** `report` can regenerate Markdown/HTML from existing results.
- [ ] **L-150** `export-nextflow --smoke` generates runnable DSL2.
- [ ] **L-151** `run --engine nextflow --smoke` passes in a local Nextflow environment.
- [ ] **L-152** Invalid engine returns `runtime_not_supported` or an equivalent clear error.

## 12. Local Results and Auxiliary Functions

- [ ] **L-160** `abi inspect --result-dir <OUT>` correctly summarizes failures, skips, and missing inputs.
- [ ] **L-161** `abi report --type <TYPE> --result-dir <OUT>` can reproduce the report.
- [ ] **L-162** `abi validate-result` does not modify the result directory.
- [ ] **L-163** `--allow-empty-tables` and `--require-nonempty-tables` behave as described.
- [ ] **L-164** `abi export-nextflow` output includes DSL2, step dependencies, and resource parameters.
- [ ] **L-165** `abi export-agent-context` content is consistent with plugin capabilities.
- [ ] **L-166** All agent/JSON interfaces uniformly return success, confirmation_required, or error envelope.
- [ ] **L-167** Re-generating a report from the same run does not modify original result tables or provenance.

---

# Part 2: HPC / Production Platform Acceptance

## 13. Platform and Shared File System

- [ ] **H-001** Use the same wheel, Git commit, and configuration version as the release.
- [ ] **H-002** `abi --help` runs successfully on both login and compute nodes.
- [ ] **H-003** `ABI_MAMBA_ROOT` is on a path accessible from compute nodes.
- [ ] **H-004** Input, database, working directory, and log directory are all on shared paths.
- [ ] **H-005** Compute nodes have database read permissions and output write permissions.
- [ ] **H-006** Check disk capacity, inodes, user quota, and temporary space.
- [ ] **H-007** Configuration does not depend on login node local `/tmp` or local disk visible only to the login node.
- [ ] **H-008** Simultaneous database reads from multiple nodes have no lock conflicts or file corruption.
- [ ] **H-009** Shared storage paths (NFS/Lustre/GPFS) and performance meet requirements.

## 14. Scheduler Acceptance

Slurm example:

```bash
abi run \
  --engine hpc \
  --scheduler slurm \
  --type <TYPE> \
  --config <PROD_CONFIG.yaml> \
  --partition <PARTITION> \
  --account <ACCOUNT> \
  --qos <QOS> \
  --confirm-execution
```

For PBS environments, replace with `--scheduler pbs`.

- [ ] **H-010** Slurm `sbatch`, `squeue`, `sacct`, `scancel` are available.
- [ ] **H-011** PBS `qsub`, `qstat`, `qdel` are available.
- [ ] **H-012** Each DAG step generates an independent scheduler script.
- [ ] **H-013** CPU, memory, walltime, and GPU are correctly written into scheduler directives.
- [ ] **H-014** DAG dependencies are converted to correct scheduler dependencies.
- [ ] **H-015** After an upstream failure, dependent downstream steps do not execute.
- [ ] **H-016** Scheduler job ID is written to `commands.tsv` and summary.
- [ ] **H-017** Scheduler timeout is mapped to timeout/failed.
- [ ] **H-018** OOM, preempt, node failure, and cancelled statuses are correctly mapped.
- [ ] **H-019** After user cancellation, unstarted subsequent jobs are stopped and completed-step provenance is preserved.
- [ ] **H-020** partition/account/qos parameters must not allow shell or scheduler directive injection.
- [ ] **H-021** Scheduler scripts include `set -euo pipefail` or equivalent strict error handling.

### Current Known Limitations

`HpcRuntime.dry_run()` has implemented HPC script generation, but the main `abi dry-run` currently does not expose `--engine hpc`. CLI users cannot directly preview complete HPC scripts; this should be recorded as an acceptance gap.

## 15. Compute Node Tool Paths

Must be checked inside actual compute nodes, not only on the login node.

- [ ] **H-030** Every tool used in the plan is resolvable on compute nodes.
- [ ] **H-031** Tools come from the expected mamba environment, not an old system binary with the same name.
- [ ] **H-032** Executables have execute permission.
- [ ] **H-033** Dynamic libraries, Perl, R, Python packages, and helper script dependencies are complete.
- [ ] **H-034** `PYTHONPATH` does not pollute the isolated environment.
- [ ] **H-035** OpenMP, BLAS, and tool thread configurations are reasonable.
- [ ] **H-036** All actual tool versions are written to `tool_versions.tsv`.
- [ ] **H-037** In container mode, images can be pulled or are already cached.
- [ ] **H-038** Singularity/Apptainer bind paths include input, database, working, and output directories.
- [ ] **H-039** Login node and compute node resolve to the same version of the ABI CLI.

## 16. Real Database Download

Large databases should be downloaded one at a time; installing all resources at once is not recommended:

```bash
abi setup-resources \
  --type metagenomic_plasmid \
  --config <PROD_CONFIG.yaml> \
  --resource genomad \
  --confirm
```

- [ ] **H-040** The download node complies with the organization's external network access and security policies.
- [ ] **H-041** The download target is the final shared path.
- [ ] **H-042** Check estimated size, remaining space, and quota before downloading.
- [ ] **H-043** An interrupted download does not mark the half-finished product as ready.
- [ ] **H-044** Re-running does not overwrite an already validated complete database.
- [ ] **H-045** Verify provider checksum or directory fingerprint.
- [ ] **H-046** Record database version, download date, source URL, and license.
- [ ] **H-047** Execute a minimal database tool query on compute nodes, not just check file existence.
- [ ] **H-048** Execute real smoke queries separately for geNomad, Bakta, Kraken2, GTDB-Tk, CheckM2, etc.
- [ ] **H-049** After a database upgrade, retain the old version and support rollback.
- [ ] **H-050** When multiple jobs start simultaneously, the same database is not concurrently re-downloaded.
- [ ] **H-051** Database paths are recorded in provenance as the final resolved canonical path.

## 17. Real End-to-End Run

Prepare at least one gold/small-real dataset for each plugin that can be manually evaluated.

- [ ] **H-060** Use real mode and `--confirm-execution`; must not use `--smoke`.
- [ ] **H-061** All external steps actually execute and return code 0.
- [ ] **H-062** All required output files exist and are non-empty.
- [ ] **H-063** Standard tables contain more than just headers.
- [ ] **H-064** Resolved sample IDs, numeric ranges, and taxonomy fields are correct.
- [ ] **H-065** Methods, tool versions, and databases in the report are consistent with the actual run.
- [ ] **H-066** `inspect` shows no failed steps and no production resource placeholders.
- [ ] **H-067** `validate-result --require-nonempty-tables` passes.
- [ ] **H-068** Compared against a known baseline, core metrics are within allowed tolerance.
- [ ] **H-069** Domain experts spot-check biological plausibility.
- [ ] **H-070** For no-hit, low-quality, and extreme inputs, return reasonable empty results rather than crashing or false positives.

## 18. Input Platform Coverage

- [ ] **H-075** Illumina paired-end real run.
- [ ] **H-076** ONT real run.
- [ ] **H-077** PacBio HiFi real run.
- [ ] **H-078** Hybrid real run.
- [ ] **H-079** assembly-only real run.
- [ ] **H-080** Both single-sample and multi-sample runs.
- [ ] **H-081** Both grouped and ungrouped scenarios.
- [ ] **H-082** Both optional-tool enabled and disabled paths verified.

Only execute for platforms actually supported by the plugin; not-applicable items must be noted in the acceptance record.

## 19. Concurrency, Recovery, and Fault Injection

- [ ] **H-090** No output directory overwriting during multi-sample parallelism.
- [ ] **H-091** Duplicate sample IDs are rejected early.
- [ ] **H-092** `--resume` only skips steps where output is complete and checksum matches.
- [ ] **H-093** After manually modifying a completed output, resume re-executes that step.
- [ ] **H-094** After deleting intermediate files, recovery starts from the correct step.
- [ ] **H-095** When a tool is manually terminated, the failure reason is written to step log.
- [ ] **H-096** When databases are temporarily unreadable, fail-fast; do not produce false success.
- [ ] **H-097** After a scheduler interruption, provenance remains parseable.
- [ ] **H-098** On re-run to the same outdir, old provenance does not contaminate the new run.
- [ ] **H-099** Nextflow `-resume` behavior is consistent with ABI resume.
- [ ] **H-100** No long-term lingering jobs after failure, cancellation, or timeout.
- [ ] **H-101** When one compute node fails, the final status and failure reason are correct.
- [ ] **H-102** Partial standard table parse failure must not cause the overall result to be falsely reported as success.
## 20. Nextflow Production Acceptance

```bash
abi run \
  --engine nextflow \
  --type <TYPE> \
  --config <PROD_CONFIG.yaml> \
  --executor slurm \
  --nextflow-profile <PROFILE> \
  --resume \
  --confirm-execution
```

- [ ] **H-110** Generated `workflow.nf` is valid DSL2.
- [ ] **H-111** Nextflow executor, profile, and working directory are correct.
- [ ] **H-112** trace, timeline, stdout, and stderr files are generated.
- [ ] **H-113** Task statuses and exit codes in trace are mapped to ABI provenance.
- [ ] **H-114** Remote scheduler job ID is recorded.
- [ ] **H-115** `-resume` does not re-execute already-cached tasks.
- [ ] **H-116** On Nextflow failure, ABI CLI exit code is non-zero and points to stderr path.
- [ ] **H-117** Nextflow work and cache cleanup strategy is clear.

## 21. Performance and Capacity

- [ ] **H-120** Record plan, submission, queue, run, and report elapsed times.
- [ ] **H-121** Record single-sample and multi-sample peak memory.
- [ ] **H-122** Record temporary file and final result disk usage.
- [ ] **H-123** Plan generation time for 100 samples meets SLA.
- [ ] **H-124** Large DAGs do not cause scheduler submission storms.
- [ ] **H-125** Shared database reads are not an unacceptable I/O bottleneck.
- [ ] **H-126** Logs and progress JSON/JSONL do not grow abnormally during long tasks.
- [ ] **H-127** Report generation time and memory meet requirements.
- [ ] **H-128** Concurrent worker count matches node CPU/memory.
- [ ] **H-129** Excessively large samples or overly long paths do not cause command line, filename, or scheduler script failures.

## 22. Traceability and Result Archiving

- [ ] **H-130** `execution_plan.json` is consistent with the actual execution configuration.
- [ ] **H-131** `commands.tsv` includes all steps and their final status.
- [ ] **H-132** In `resolved_inputs.tsv`, all production inputs exist and there are no `NOT_CONFIGURED` entries.
- [ ] **H-133** In `tool_versions.tsv`, all required tool versions are successfully captured.
- [ ] **H-134** `resources.json` records database version and path.
- [ ] **H-135** `checksums.json` or resource fingerprints are usable for integrity checks.
- [ ] **H-136** `run_summary.json` is consistent with actual scheduler status.
- [ ] **H-137** `progress.jsonl` can replay main run events.
- [ ] **H-138** Each failed step has stdout/stderr or equivalent log.
- [ ] **H-139** Report, standard tables, and provenance are archived together.
- [ ] **H-140** After archiving, read-only `inspect` and `validate-result` can be executed on another machine.

---

# Part 3: Production Release and Defect Management

## 23. Production Release Threshold

A plugin can only be deemed ready for production when all of the following conditions are met simultaneously:

- [ ] No blocking items in the local checklist.
- [ ] HPC real end-to-end run passes.
- [ ] No `NOT_CONFIGURED`, mock, synthetic, or fallback production resources present in results.
- [ ] Real tool versions and database versions are fully traceable.
- [ ] `validate-result --require-nonempty-tables` passes.
- [ ] Failure, timeout, cancellation, and resume are each verified at least once.
- [ ] Real results pass baseline or domain expert review.
- [ ] Known limitations, running costs, database licenses, and operational procedures are formally documented.

## 24. Current Fix Status and Recommended Priority Items

Completed items requiring ongoing regression:

1. All 7 plugins have implemented complete preflight; empty-check false passes are no longer allowed.
2. All 7 plugins provide sample templates required by `init`.
3. `setup-resources` output explicitly distinguishes mock from real resource preview; mock dry-run does not write resources.

Still recommended for priority treatment:

1. Some generic database checks only verify path existence and have not yet fully verified content, permissions, and structure.
2. After 16S database download failure, the synthetic fallback must be prohibited from entering production runs.
3. Explicit tool path checks should supplement execute permission and version probing.
4. The main CLI should provide an HPC dry-run / scheduler script preview entry point.

## 25. Individual Acceptance Record Template

```markdown
### Check Item: L-070 dry-run does not invoke real tools

- Plugin: metagenomic_plasmid
- Environment: Local/HPC
- ABI Version:
- Configuration File:
- Input File:
- Execution Command:
- Expected Result: Does not start any real external tool, does not modify the database directory
- Actual Result:
- Exit Code:
- Evidence Path:
- Judgment: Pass / Fail / Blocked / Not Applicable
- Defect ID:
- Tester:
- Time:
```

