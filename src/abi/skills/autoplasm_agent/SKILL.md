---
name: autoplasm-agent
description: Use when an agent needs to operate the AutoPlasm repository or CLI for metagenomic plasmid analysis, including validating sample sheets, checking repository-local mamba tools, planning, dry-running, executing registered bioinformatics tools, inspecting provenance, updating project configs, or explaining AutoPlasm workflow status. This skill guides safe agent use of AutoPlasm without relying on global environments or over-claiming dry-run results.
---

# AutoPlasm Agent Operator

Use this skill when working inside the AutoPlasm repository and the task involves the `autoplasm` CLI, local `.mamba` environments, sample sheets, tool registry entries, or pipeline provenance.

## Core Rule

Always preserve the AutoPlasm control path:

1. Validate metadata.
2. Check registered tools.
3. Check or prepare required resources.
4. Build a plan.
5. Run dry-run.
6. Inspect provenance.
7. Only then run real external tools.

Do not hand-run bioinformatics tools directly unless debugging one failed step. Prefer the CLI so commands, status, stdout/stderr, and config are recorded.

## Task Routing

Use the narrowest AutoPlasm entry point that fits the user's request:

- Read or explain current capabilities: inspect `README.md`, `docs/metagenomic_plasmid.md`,
  `docs/workflow_validation.md`, `src/abi/skills/README.md`,
  `plugins/metagenomic_plasmid/tool_registry.yaml`, and
  `plugins/metagenomic_plasmid/pipeline_dag.yaml`.
- Validate input metadata: run `validate-sample-sheet`.
- Check executables: run `check-tools`; do not accept globally installed tools as substitutes for repository-local envs.
- Check databases/models/indexes: run `check-resources`.
- Preview workflow steps: run `plan`.
- Preview commands and provenance: run `dry-run`.
- Execute a batch project: run `run` only after preflight is clean.
- Execute one sample: run `run-single` only when the user gives enough single-sample input.
- Rebuild a report: run `report --result-dir ...`.
- Update tool behavior: edit registry/config/wrappers, then update the matching
  `src/abi/skills/{tool}/SKILL.md`.

## Repository Anchors

- ABI CLI entry point: `src/abi/cli.py`
- Compatibility CLI entry point: `src/abi/autoplasm/cli.py`
- Generic executor: `src/abi/executor.py`
- Step contract enforcement: `src/abi/contracts/step_contract.py`
- Plugin package: `src/abi/plugins/metagenomic_plasmid/`
- Plugin engine: `src/abi/plugins/metagenomic_plasmid/_engine/`
- Pipeline DAG: `plugins/metagenomic_plasmid/pipeline_dag.yaml`
- Tool registry: `plugins/metagenomic_plasmid/tool_registry.yaml`
- Tool contracts: `plugins/metagenomic_plasmid/tool_contracts/`
- Default config: `config/default.yaml`
- Profiles: `config/profiles/*.yaml`
- Environment files: `envs/*.yml`
- Tool docs: `src/abi/skills/{tool}/SKILL.md`
- User manual: `docs/metagenomic_plasmid.md`
- Validation plan: `docs/workflow_validation.md`

## Environment Rules

AutoPlasm tools must come from the repository-local mamba root:

```bash
.mamba/envs/{env_name}/bin/{executable}
```

If needed, set:

```bash
export AUTOPLASM_MAMBA_ROOT=/path/to/project/.mamba
```

Do not treat a globally installed executable as satisfying the registry. If `check-tools` fails, repair the local env or registry entry.

## Standard Preflight

From the repository root:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli validate-sample-sheet --sample-sheet examples/sample_sheet.tsv
PYTHONPATH=src python -m abi.autoplasm.cli check-tools --config examples/config_minimal.yaml --profile local
PYTHONPATH=src python -m abi.autoplasm.cli check-resources --config examples/config_assembly_full_run.yaml --profile local
PYTHONPATH=src python -m abi.autoplasm.cli plan --config examples/config_minimal.yaml
PYTHONPATH=src python -m abi.autoplasm.cli dry-run --config examples/config_minimal.yaml
```

Use `autoplasm ...` instead of `PYTHONPATH=src python -m abi.autoplasm.cli ...` only when the package is installed in the current environment.

## Platform Routes

Use these platform expectations when reviewing plans or explaining selected tools:

| Platform | Expected route |
| --- | --- |
| `illumina` | fastp/FastQC/MultiQC -> MEGAHIT by default -> QUAST/geNomad -> MetaPhlAn taxonomy evidence -> annotation -> bowtie2/samtools/CoverM abundance. |
| `ont` | NanoPlot/Filtlong -> metaFlye -> QUAST/geNomad -> MetaPhlAn `--long_reads` taxonomy evidence -> annotation -> minimap2 `map-ont`/samtools/CoverM abundance. |
| `pacbio_hifi` | HiFiAdapterFilt -> hifiasm/hifiasm_meta normalized FASTA -> QUAST/geNomad -> MetaPhlAn `--long_reads` taxonomy evidence -> annotation -> minimap2 `map-hifi`/samtools/CoverM abundance. |
| `hybrid` | short-read QC plus long-read QC -> OPERA-MS -> QUAST/geNomad -> MetaPhlAn short-read taxonomy evidence -> annotation -> separate short and long abundance tracks. |
| `assembly` | skip reads QC and assembly; start from provided contigs/assembly FASTA, then QUAST/geNomad and configured downstream tools. |

If a generated plan violates these expectations, inspect `src/abi/autoplasm/planner.py`, the sample sheet platform fields, and the relevant config block before running tools.

## Common Command Recipes

Minimal dry-run:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli dry-run \
  --config examples/config_minimal.yaml \
  --outdir results/autoplasm_project \
  --log-dir log
```

Assembly-only real smoke:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli check-resources \
  --config examples/config_assembly_full_run.yaml \
  --profile local
PYTHONPATH=src python -m abi.autoplasm.cli run \
  --config examples/config_assembly_full_run.yaml \
  --profile local \
  --outdir results/assembly_full_run \
  --log-dir results/assembly_full_run/log
```

Reads-route preflights:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli dry-run \
  --config examples/config_illumina_smoke.yaml \
  --profile dry_run \
  --outdir results/illumina_smoke_dry \
  --log-dir results/illumina_smoke_dry/log
PYTHONPATH=src python -m abi.autoplasm.cli dry-run \
  --config examples/config_ont_smoke.yaml \
  --profile dry_run \
  --outdir results/ont_smoke_dry \
  --log-dir results/ont_smoke_dry/log
PYTHONPATH=src python -m abi.autoplasm.cli dry-run \
  --config examples/config_hifi_smoke.yaml \
  --profile dry_run \
  --outdir results/hifi_smoke_dry \
  --log-dir results/hifi_smoke_dry/log
PYTHONPATH=src python -m abi.autoplasm.cli dry-run \
  --config examples/config_hybrid_smoke.yaml \
  --profile dry_run \
  --outdir results/hybrid_smoke_dry \
  --log-dir results/hybrid_smoke_dry/log
```

## Real Run Procedure

Before real execution:

- Confirm sample files exist.
- Confirm `check-tools --profile local` reports required tools as `ok`.
- Confirm `check-resources` reports required databases/models as `ok`, or run `setup-resources`.
- Confirm `commands.tsv` from dry-run has no unintended placeholders.
- Confirm required database/model/reference paths are configured.
- Confirm output directory is not an unrelated previous result directory.

Assembly smoke workflow:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli fetch-examples \
  --dataset plasmid_refseq_smoke \
  --outdir data/examples/plasmid_refseq_smoke
PYTHONPATH=src python -m abi.autoplasm.cli setup-resources \
  --config examples/config_assembly_full_run.yaml \
  --profile local
PYTHONPATH=src python -m abi.autoplasm.cli run \
  --config examples/config_assembly_full_run.yaml \
  --profile local \
  --outdir results/assembly_full_run
```

Then run:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli run \
  --config config/your_project.yaml \
  --sample-sheet samples.tsv \
  --profile local \
  --outdir results/your_project \
  --log-dir results/your_project/log
```

For one sample:

```bash
PYTHONPATH=src python -m abi.autoplasm.cli run-single \
  --input reads/S1_R1.fastq.gz \
  --read2 reads/S1_R2.fastq.gz \
  --platform illumina \
  --sample-id S1 \
  --config config/your_project.yaml \
  --profile local \
  --outdir results/S1
```

## Provenance To Inspect

After dry-run or run, inspect:

- `execution_plan.json`
- `provenance/config.resolved.yaml`
- `provenance/commands.tsv`
- `provenance/resolved_inputs.tsv`
- `provenance/tool_versions.tsv`
- `provenance/checksums.json`
- `provenance/resources.json`
- `provenance/environment.yml`
- `provenance/run_summary.json`
- `provenance/step_logs/{step_id}.stdout.log`
- `provenance/step_logs/{step_id}.stderr.log`
- `tables/plasmid_predictions.tsv`
- `tables/plasmid_consensus.tsv`
- `tables/annotations.tsv`
- `tables/host_predictions.tsv`
- `tables/abundance.tsv`
- `report/report.md`
- `report/report.html`
- `report/methods.md`

Contract enforcement happens only on real execution after external tools
succeed. The executor validates resolved on-disk outputs, so fixed filenames
such as `S1_R1.clean.fastq.gz` and `S1_R2.clean.fastq.gz` can satisfy abstract
planner outputs such as `clean_read1` and `clean_read2`.

Important `commands.tsv` statuses:

- `dry_run`: planned, not executed.
- `success`: external command returned 0.
- `failed`: command could not run, returned non-zero, or required parameters were missing.
- `skipped`: planner intentionally skipped this step.

Important parser statuses:

- `parsed`: the step wrote one or more standard result tables.
- `no_standard_rows`: the tool has a parser, but no standard rows were found.
- `not_supported`: the tool ran, but no standard parser exists yet.

## Required Resource Checks

Real runs often need external resources that are not included by tool installation:

- geNomad, PLASMe, PlasmidFinder, PlasmidHostFinder: database/model paths.
- PlasX: annotations, gene calls, model.
- COPLA: reference graph and reference list.
- BLAST, MMseqs2, Kraken2: database paths.
- MUMmer: reference plasmid FASTA.
- clinker: annotated GenBank inputs.
- bowtie2: index prefix.
- CoverM: BAM files.

If missing, update the project config rather than editing generated provenance.

## Config Knobs To Check

When users ask to change workflow behavior, prefer editing these config blocks:

- `qc`: read QC enablement, short-read tool, long-read tool, FastQC/MultiQC switches, duplicate QC policy.
- `assembly`: assembler choices for Illumina, ONT, PacBio HiFi, and hybrid routes.
- `plasmid_detection`: detection tools, consensus tools, strategy, minimum length, uncertain output.
- `typing`: MOB-typer, PlasmidFinder, COPLA and other typing tools.
- `annotation`: Bakta, AMRFinderPlus, ABRicate, ISEScan, IntegronFinder, MOB-suite selections.
- `abundance`: short/long mappers, CoverM, normalization and reporting policy.
- `sample_analysis`: diversity, differential abundance, and network settings.
- `resources`: database/model roots and tool-specific paths.

After changing config, rerun `plan` and `dry-run` before real execution.

## Failure Handling

When a command fails:

1. Find the first `failed` row in `provenance/commands.tsv`.
2. Read its `reason` and `return_code`.
3. Open the matching stderr log under `provenance/step_logs/`.
4. Check whether inputs, database/model paths, and local executable paths exist.
5. Fix config or registry entries.
6. Re-run `plan` and `dry-run` before real execution.

Do not delete user outputs as a recovery tactic. `autoplasm clean` is intentionally non-destructive.

## Documentation Update Rules

When changing CLI behavior, update:

- `README.md`
- `docs/agent_usage.md`
- `src/abi/skills/abi_agent/SKILL.md`
- `src/abi/skills/autoplasm_agent/SKILL.md`
- relevant `src/abi/skills/{tool}/SKILL.md`
- `CHANGELOG.md`

When changing a registry entry, update:

- `plugins/metagenomic_plasmid/tool_registry.yaml`
- matching `plugins/metagenomic_plasmid/tool_contracts/{tool}.yaml`
- matching `src/abi/skills/{tool}/SKILL.md`
- environment YAML if executable availability changes
- `src/abi/skills/README.md` if category, default status, required status, or runtime environment changes

## Interpretation Boundaries

Do not overstate results:

- Dry-run proves planning and command rendering only.
- Published component tools support a route stage, not the whole ABI workflow.
- A workflow is scientifically validated only after real execution on curated
  benchmark data with pinned tools, versioned databases, expected standard-table
  outputs, and documented acceptance thresholds.
- Plasmid clusters are operational groups, not species.
- Plasmid binning can be incomplete.
- Host prediction is evidence, not proof.
- Correlation networks are not causal evidence.
- Full biological interpretation requires real tool outputs and configured databases.

## Verification Commands

Use these before reporting completion:

```bash
PYTHONPATH=src python -m pytest
PYTHONPATH=src python -m ruff check src tests
git diff --check
PYTHONPATH=src python -m abi.autoplasm.cli --help
PYTHONPATH=src python -m abi.autoplasm.cli dry-run --config examples/config_minimal.yaml
```
