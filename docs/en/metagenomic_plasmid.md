# Metagenomic Plasmid Integration

The `metagenomic_plasmid` ABI plugin uses the bundled `abi.autoplasm` pipeline
(40 Python files in `plugins/metagenomic_plasmid/_engine/`). This is ABI's flagship
plasmid analysis workflow, supporting the full analysis chain from raw sequencing data
to community analysis visualization. This replaces the earlier split development model
where an external `autoplasm` package supplied the plasmid workflow.

## Public Shape

- PyPI package: `abi-agent`
- ABI plugin id: `metagenomic_plasmid`
- Internal Python namespace: `abi.autoplasm`
- Compatibility command: `autoplasm`
- Tool contracts: 67 (all bioinformatics tools across 11 analysis categories)
- Engine: 40 files under `_engine/` (pipeline, planner, DAG, parsers, normalize, report, statistics, skills, etc.)
- Pipeline DAG: `pipeline_dag.yaml` (84+ nodes, 5 platforms, 16 standard tables) — single source of truth
- Step contract enforcement: `contracts/step_contract.py` — output validation, actual-output resolution, assertions, and checksum chaining
- 10 conda environments: qc, assembly, plasmid_detection, plasmid_binning, annotation, typing, abundance, comparative_genomics, visualization, statistics

## Full Analysis Chain

```
QC (fastp / FastQC / MultiQC)
  → Assembly (MEGAHIT / SPAdes / Canu)
    → Assembly QC (QUAST / Bandage)
      → Plasmid Detection (geNomad / Plasme / PlasX / Platon)
        → Plasmid Binning (MetaBAT2 / MaxBin2 / CONCOCT / SemiBin / DAS Tool)
          → Plasmid Consensus (consensus algorithm)
            → Annotation (Bakta / Prodigal / AMRFinderPlus / ISEScan / IntegronFinder)
              → Typing (PlasmidFinder / MOB-typer)
                → Abundance (bowtie2 / coverm)
                  → Community Analysis (alpha/beta diversity + differential abundance)
                    → Comparative Genomics (BLAST / MUMmer / MMseqs2 / clinker)
                      → Visualization (pyCirclize / DNA Features Viewer / pyvis / Bandage)
                        → Co-occurrence Network (FastSpar)
                          → Report (Markdown + sciplot figures)
```

## High-Performance Server Execution

On a server with 16 cores and 1TB RAM, metagenomic_plasmid runs stably at 16 threads.
The core pipeline (QC → Assembly → Detection → Annotation → Abundance → Community Analysis → Visualization)
has been verified with real biological data.

Currently produces all 16 standard tables (including `sample_diversity`, `differential_abundance`,
`network_edges` for community analysis), and 3 sciplot figures. The remaining 48 of 62 steps
are mostly gated behind database downloads — the tool code itself is ready.

## Common Commands

```bash
abi plan --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --profile dry_run

abi dry-run --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --profile dry_run

autoplasm dry-run \
  --config examples/config_minimal.yaml \
  --profile dry_run
```

For real execution, prepare the repository-local mamba environments and required
databases first. Dry-run output is planning evidence, not proof that external
bioinformatics tools or databases are production-ready.

## Database Dependencies

| Database | Size | Required By | Status |
|----------|------|------------|:---:|
| genomad_db | ~2GB | genomad | ✅ Available |
| bakta_db | ~40GB | bakta | ✅ Available |
| amrfinder_db | ~2GB | amrfinderplus | ✅ Fixed — `-d {database}` flag + DAG wiring (2026-06-20) |
| plasmidfinder_db | ~100MB | plasmidfinder | ✅ Available |
| mob_suite_db | ~200MB | mob_typer | ❌ Not downloaded |
| kraken2_db | ~50GB | kraken2 | ❌ Not downloaded |
| metaphlan_db | ~3GB | metaphlan | ❌ Not downloaded |
| checkm2_db | ~3GB | checkm2 | ❌ Not downloaded |
| gtdbtk_db | ~30GB | gtdbtk | ❌ Not downloaded |

## Resource Boundaries

The package includes small configs, tool contracts, test fixtures, and examples.
It does not include real databases, mamba environments, or user results.

Use `resources/` for local databases and keep those files outside git.

## Validation Position

The metagenomic plasmid route is now structured as a constrained workflow:
`pipeline_dag.yaml` defines node order, outputs, contracts, and assertions;
the generic executor writes provenance and enforces contracts after each
successful external command.

This is not yet the same as a fully validated biological workflow. The current
codebase provides the control layer needed for validation, while the remaining
work is to pin environments, version databases, curate positive/negative
benchmark datasets, and connect route-level reports to method citations. See
[Workflow Validation and Scientific Evidence Plan](workflow_validation.md).
