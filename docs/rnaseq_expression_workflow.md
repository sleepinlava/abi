# RNA-seq Expression Workflow (`rnaseq_expression`)

> **Plugin**: `rnaseq_expression`
> **Status**: Active (2026-06-18)
> **Canonical reference**: `docs/next_development_plan.md` §6.2

## Workflow

```text
FASTQ
  → fastp (QC)
  → STAR / HISAT2 (alignment)
  → featureCounts (quantification)
  → DESeq2 (differential expression)
  → enrichment (clusterProfiler, optional)
  → report + figures
```

## Tool Chain

| Stage | Default Tool | Alternative | Category |
| --- | --- | --- | --- |
| QC | fastp | FastQC, MultiQC | qc |
| Alignment | STAR | HISAT2 | alignment |
| Quantification | featureCounts | Salmon, Kallisto | expression |
| Differential expression | DESeq2 | edgeR | differential_expression |
| Enrichment | clusterProfiler | gseapy | enrichment |

## Standard Tables

| Table | Content | Required |
| --- | --- | --- |
| `qc_summary` | Read QC metrics (total reads, Q30, GC) | Yes |
| `alignment_summary` | Mapping rate, unique/multi-mapped reads | Yes |
| `gene_expression` | Per-gene raw counts | Yes |
| `normalized_expression` | DESeq2 median-of-ratios normalized counts | Yes |
| `differential_expression` | log2FC, p-value, padj per gene | Yes |
| `enrichment_results` | GO/KEGG pathway enrichment | No |

## Figures

| Figure | File | Required |
| --- | --- | --- |
| QC read counts | `figures/qc_read_counts.png` | Yes |
| Mapping rate | `figures/mapping_rate.png` | Yes |
| PCA expression | `figures/pca_expression.png` | Yes |
| Volcano plot | `figures/volcano_deg.png` | Yes |
| MA plot | `figures/ma_plot.png` | No |
| Top DEG heatmap | `figures/top_deg_heatmap.png` | No |
| Enrichment dotplot | `figures/enrichment_dotplot.png` | No |

## Quick Start

```bash
# Plan
abi plan --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example

# Dry-run
abi dry-run --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example

# Real execution (requires STAR index + GTF annotation)
abi run --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example \
  --confirm-execution

# Report
abi report --type rnaseq_expression \
  --result-dir results/rnaseq_example
```

## Configuration

### Minimum config

```yaml
project_name: "rnaseq_expression_run"
mode: dry_run
threads: 4
outdir: results/rnaseq_expression
input:
  sample_sheet: sample_sheet.tsv
alignment:
  tool: star
resources:
  genome_index: /path/to/star_index
  annotation_gtf: /path/to/annotations.gtf
differential_expression:
  comparison: "treatment_vs_control"
  alpha: 0.05
```

### Sample sheet format

```tsv
sample_id	group	condition	platform	read1	read2
sample1	treatment	treated	rna_seq	raw/s1_R1.fastq.gz	raw/s1_R2.fastq.gz
sample2	treatment	treated	rna_seq	raw/s2_R1.fastq.gz	raw/s2_R2.fastq.gz
sample3	control	untreated	rna_seq	raw/s3_R1.fastq.gz	raw/s3_R2.fastq.gz
sample4	control	untreated	rna_seq	raw/s4_R1.fastq.gz	raw/s4_R2.fastq.gz
```

Required columns: `sample_id`, `read1`, `read2`. Optional: `group`, `condition`, `platform`.

## Resource Requirements

Real execution requires:

1. **STAR genome index** — Build with `STAR --runMode genomeGenerate`.
2. **GTF annotation** — GENCODE, Ensembl, or RefSeq format.
3. **R + DESeq2** — `BiocManager::install("DESeq2")`.
4. **Optional: R + clusterProfiler** — `BiocManager::install("clusterProfiler")`.

All resources appear in `provenance/resource_manifest.json` after a real run.

## Known Limitations

See `plugins/rnaseq_expression/limitations.yaml` for the complete list. Key points:

1. RNA-seq measures transcript abundance, not protein levels.
2. Alignment rates depend on reference genome completeness.
3. DESeq2 assumes most genes are not differentially expressed.
4. Lowly expressed genes have inflated FDR.
5. Reference genome/annotation version affects results.

## Architecture Notes

This plugin is an **inline implementation** (no `_engine/` sub-package), following the
same pattern as `metatranscriptomics`. The parser functions live in the plugin module
itself rather than in a separate `parsers.py`.

### Plugin lifecycle

```
load_config()  →  build_plan()  →  run (ExternalExecutor)
  →  parse_outputs() (per step)  →  write_report()
```

### Parser dispatch

`parse_outputs(tool_id, output_dir, sample_id)` dispatches:
- `fastp` → `_parse_fastp()` → `qc_summary`
- `star` / `hisat2` → `_parse_star()` → `alignment_summary`
- `featurecounts` → `_parse_featurecounts()` → `gene_expression`
- `deseq2` → `_parse_deseq2()` + `_parse_deseq2_normalized()` → `differential_expression` + `normalized_expression`
