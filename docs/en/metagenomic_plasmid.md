# Metagenomic Plasmid Analysis

The `metagenomic_plasmid` plugin is ABI's platform-aware plasmid workflow for
Illumina, ONT, PacBio HiFi, hybrid, and assembly-only projects. Its canonical
topology is declared in `plugins/metagenomic_plasmid/pipeline_dag.yaml`; the
Python engine resolves sample-specific inputs, conditions, paths, provenance,
and normalized result tables.

## Default routes

### Illumina

```text
FASTQ → fastp → MultiQC → optional Bowtie2 host removal → MEGAHIT → QUAST
      → geNomad → circularity/structure check → PlasmidFinder + MOB-typer
      → Bakta + AMRFinderPlus + ISEScan + IntegronFinder
      → MMseqs2 catalog → Bowtie2 + samtools + CoverM → report
```

### ONT

```text
FASTQ/POD5/BAM → optional Dorado or BAM-to-FASTQ → NanoPlot → Filtlong
               → optional minimap2 host removal → metaFlye
               → optional Medaka → QUAST → shared downstream path
```

### PacBio HiFi

```text
FASTQ/BAM → optional BAM-to-FASTQ → NanoPlot + HiFiAdapterFilt
          → optional minimap2 host removal → hifiasm-meta → QUAST
          → shared downstream path
```

### Hybrid

```text
Illumina + ONT/HiFi → fastp + NanoPlot/Filtlong
                    → platform-specific optional host removal
                    → OPERA-MS → QUAST → shared downstream path
```

`hybridSPAdes` and `metaSPAdes` are explicit alternatives. Selecting an
alternative replaces the platform default; ABI does not run multiple assemblers
implicitly.

## Tool policy

The default path is intentionally narrow:

- geNomad is the primary plasmid detector. Platon, PLASMe, and PlasX are
  optional consensus evidence. The default weighted vote gives geNomad 0.60
  weight and the three supporting detectors 0.40 in total, so supporting tools
  cannot create a positive plasmid call without geNomad.
- PlasmidFinder and MOB-typer are the default typing tools.
- AMRFinderPlus is the default AMR path. ABRicate and RGI are optional.
- ISEScan and IntegronFinder are enabled by default; eggNOG-mapper is optional.
- MMseqs2 performs cross-sample catalog clustering. BLAST, MUMmer, and clinker
  are representative-sequence validation/visualization tools only.
- MetaBAT2, MaxBin2, CONCOCT, and SemiBin belong to the optional MAG host-genome
  branch, not plasmid binning.
- BWA, KneadData, the Hi-C placeholder, pMLST, and batch Bandage nodes are not
  part of the workflow DAG.

FastQC is disabled by default because fastp already emits HTML and JSON QC
reports. Enable it only for a publication or QC-audit appendix. MultiQC remains
enabled for project-level aggregation.

## Conditional cross-sample analyses

ABI derives eligibility from the actual sample sheet:

| Module | Default gate |
|---|---|
| Alpha/beta diversity | at least 3 samples with read-based abundance |
| Differential abundance | at least 2 groups and 3 eligible replicates per group |
| FastSpar network | at least 20 samples with read-based abundance |

When a gate is not met, the node is omitted and the reason is written to
`tables/analysis_status.tsv` and the serialized plan. Assembly-only rows do not
count as abundance replicates.

Eligible differential analysis uses DESeq2 on raw mapped counts. If raw counts
are unavailable, the runner labels rounded coverage explicitly as a count proxy.
`internal_effect_size` is available as a descriptive fallback and does not emit
inferential p-values.

## Stable result contract

Every declared table is created with its header before execution. A valid
zero-hit run therefore produces empty TSVs rather than missing files. Core
public tables include:

- `sample_qc.tsv`, `assembly_qc.tsv`
- `plasmid_predictions.tsv`, `plasmid_consensus.tsv`,
  `plasmid_structure.tsv`, `plasmid_catalog.tsv`
- `plasmid_abundance.tsv`, `plasmid_annotation.tsv`, `amr_genes.tsv`,
  `mge_elements.tsv`, `plasmid_typing.tsv`
- `host_profile.tsv`, `host_plasmid_links.tsv`
- `differential_plasmids.tsv`, `network_edges.tsv`, `network_nodes.tsv`
- `analysis_status.tsv`

Legacy normalized tables remain available for compatibility.

## Reproducibility

Each run writes `provenance/resource_manifest.json` and the compatibility file
`provenance/resources.json`. Database entries record resource ID, path, version,
date, source, status, and checksum. File resources use a content SHA-256;
database directories use a bounded directory-manifest fingerprint unless a
provider checksum is configured.

Tool versions, resolved inputs, commands, logs, and the resolved configuration
are recorded separately. Placeholder paths ending in `NOT_CONFIGURED` are
reported as such; dry-run success is not evidence that external tools or
databases are installed.

## Commands

```bash
abi plan --type metagenomic_plasmid \
  --config examples/config_minimal.yaml --profile dry_run

abi dry-run --type metagenomic_plasmid \
  --config examples/config_minimal.yaml --profile dry_run

abi check-resources --type metagenomic_plasmid
```

For production execution, configure database paths and versions, validate the
sample sheet, then run the resource and workflow checks before starting tools.
