# rnaseq_expression Example

4-sample paired-end RNA-seq example with treatment vs control contrast.

## Files

- `config.yaml` — Plugin configuration
- `sample_sheet.tsv` — 4 samples: 2 treatment + 2 control

## Quick Start

```bash
# Plan (structural validation)
abi plan --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example

# Dry-run (provenance + command rendering)
abi dry-run --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example

# Real execution (requires reference genome index + annotation)
abi run --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example \
  --confirm-execution
```

## Reference Resources

For real execution, you need:

1. **STAR genome index** — Build with:
   ```bash
   STAR --runMode genomeGenerate \
     --genomeDir resources/star_index \
     --genomeFastaFiles resources/genome.fa \
     --sjdbGTFfile resources/annotations.gtf \
     --runThreadN 16
   ```

2. **GTF annotation** — e.g., GENCODE, Ensembl, or RefSeq

Update `resources.genome_index` and `resources.annotation_gtf` in `config.yaml`
to point to your prepared resources.
