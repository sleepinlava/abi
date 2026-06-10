# featureCounts

## Purpose
Quantify gene-level counts from aligned RNA-seq reads.

## When to Use
Use after the metatranscriptomics alignment step.

## Inputs
- `bam`
- `annotation_gtf`
- `counts`
- `threads`

## Outputs
- featureCounts text output.
- ABI `gene_expression.tsv` rows when real output is parsed.
- ABI provenance records in `provenance/commands.tsv` and `provenance/step_logs/`.

## Environment
Runs from the repository-local `autoplasm-stats` environment as `featureCounts`.

## Command Template
```bash
featureCounts -T {threads} -a {annotation_gtf} -o {counts} {bam}
```

## Failure Handling
Check BAM path, annotation GTF path, the `autoplasm-stats` environment, and stderr.

## Normalization
Real featureCounts output is normalized to `tables/gene_expression.tsv`.
