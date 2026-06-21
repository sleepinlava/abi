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
`network_edges` for community analysis), and 8 sciplot figures (barplot × 3, scatterplot,
stacked_barplot, heatmap × 5) with `abi_nature` theme + `colorblind_safe` palette.
10 databases available; 24/24 default_enabled tools confirmed working.
Supports sample-level parallel execution via `config.execution.parallel`.

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
| genomad_db | 2.9 GB | geNomad | ✅ Available |
| bakta_db | 4.2 GB | Bakta | ✅ Available (light DB, --skip-sorf workaround) |
| amrfinder_db | 251 MB | AMRFinderPlus | ✅ Available (+ BLAST indexes auto-built) |
| plasmidfinder_db | ~1 MB | PlasmidFinder | ✅ Available |
| mob_suite_db | 3.0 GB | MOB-suite | ✅ Available |
| platon_db | 55 MB | PLaton | ✅ Available |
| macsyfinder_db | 180 MB | MacSyFinder | ✅ Available (pip install) |
| metaphlan_db | 34 GB | MetaPhlAn | ✅ Available |
| mmseqs2_db | 1.6 GB | MMseqs2 | ✅ Available (built from mob_suite) |
| kraken2_db | ~50 GB | Kraken2 | 🔄 Pending download (S3) |
| blast_db | ~10 GB | BLAST+ | ❌ Not built |
| checkm2_db | ~100 GB | CheckM2 | ❌ Not downloaded (env conflict) |
| gtdbtk_db | ~100 GB | GTDB-Tk | ❌ Not downloaded (env conflict) |

**Tool availability**: 24/24 `default_enabled: true` tools confirmed working in
their conda environments. 11 `default_enabled: false` tools (PlasmidHostFinder,
pMLST, gplas2, Recycler, scapp, COPLA, conjscan, PLASMe, PlasX, plasmaag,
plasmidhostfinder) are missing git-clone installations — these are Tier 3
(experimental/non-mainstream) tools for niche analysis scenarios.

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
