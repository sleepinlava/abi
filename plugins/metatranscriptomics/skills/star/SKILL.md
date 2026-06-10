# STAR

## Purpose
Align cleaned RNA-seq reads to a transcriptome or genome index.

## When to Use
Use for the metatranscriptomics demo `alignment` step when `alignment.tool: star`.

## Inputs
- Cleaned `read1` and `read2`
- `genome_index`
- `output_prefix`
- `threads`

## Outputs
- Sorted BAM at `{sample_id}.Aligned.sortedByCoord.out.bam`.
- ABI provenance records in `provenance/commands.tsv` and `provenance/step_logs/`.

## Environment
Runs from the repository-local `autoplasm-stats` environment as `STAR`.

## Command Template
```bash
STAR --runThreadN {threads} --genomeDir {genome_index} --readFilesIn {read1} {read2} --outSAMtype BAM SortedByCoordinate --outFileNamePrefix {output_prefix}
```

## Failure Handling
Check that `resources.genome_index` points to a prepared STAR index and inspect stderr.

## Normalization
Future real-run parsers can append alignment metrics to `alignment_summary.tsv`.
