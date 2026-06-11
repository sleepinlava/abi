# HISAT2

## Purpose
Alternative RNA-seq aligner for the metatranscriptomics demo.

## When to Use
Use when `alignment.tool: hisat2`.

## Inputs
- Cleaned `read1` and `read2`
- `genome_index`
- `sample_id`
- `output_dir`
- `threads`

## Outputs
- SAM alignment file under `02_alignment/{sample_id}/`.
- ABI provenance records in `provenance/commands.tsv` and `provenance/step_logs/`.

## Environment
Runs from the repository-local `abi-stats` environment as `hisat2`.

## Command Template
```bash
hisat2 -p {threads} -x {genome_index} -1 {read1} -2 {read2} -S {output_dir}/{sample_id}.sam
```

## Failure Handling
Check that `resources.genome_index` points to a HISAT2 index prefix and inspect stderr.

## Normalization
Future real-run parsers can append alignment metrics to `alignment_summary.tsv`.
