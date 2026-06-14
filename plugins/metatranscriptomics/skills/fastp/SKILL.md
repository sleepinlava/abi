# fastp

## Purpose
Trim and quality-control paired-end RNA-seq reads before alignment.

## When to Use
Use for the metatranscriptomics demo `qc` step when paired FASTQ inputs are present.

## Inputs
- `read1`
- `read2`
- `sample_id`
- `output_dir`
- `threads`

## Outputs
- Cleaned paired FASTQ files under `01_qc/{sample_id}/`.
- Expected fixed filenames are `{sample_id}_R1.clean.fastq.gz` and
  `{sample_id}_R2.clean.fastq.gz`; R1/R2 must not be swapped when inspecting
  downstream paths.
- HTML and JSON QC summaries.
- ABI provenance records in `provenance/commands.tsv` and `provenance/step_logs/`.

## Environment
Runs from the repository-local `abi-qc` environment as `fastp`.

## Command Template
```bash
fastp -i {read1} -I {read2} -o {output_dir}/{sample_id}_R1.clean.fastq.gz -O {output_dir}/{sample_id}_R2.clean.fastq.gz --thread {threads} --html {output_dir}/{sample_id}.fastp.html --json {output_dir}/{sample_id}.fastp.json
```

## Failure Handling
Check input FASTQ paths, the `abi-qc` environment, and the per-step stderr log.

## Normalization
Future real-run parsers can append read metrics to `qc_summary.tsv`.
