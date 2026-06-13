# bowtie2

## Purpose
Map short reads to plasmid contigs for abundance estimation.

## When to Use
Default mapper for Illumina samples.

## Inputs
Short reads, plasmid candidate FASTA, `threads`.

- Registry inputs: `plasmid_contigs, read1, read2`.
- Template parameters: `plasmid_contigs, read1, read2, threads, output_dir, sample_id, alignment, abundance_label`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
SAM/BAM alignment.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/abundance.yml` when present.
- Runtime environment: `autoplasm-abundance`.
- Executable: `bowtie2`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`bash -lc 'bowtie2-build {plasmid_contigs} {output_dir}/{sample_id}{abundance_label}.plasmid_index >/dev/null && bowtie2 -x {output_dir}/{sample_id}{abundance_label}.plasmid_index -1 {read1} -2 {read2} -p {threads} -S {alignment}'`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected for short-read abundance.

## Interactive Parameters
Sensitivity preset and mapping quality threshold.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `plasmid_contigs, read1, read2`.
Fail early if candidate plasmid FASTA files, BAM files, or read inputs are missing for the selected command template.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize abundance outputs toward raw counts, coverage, RPKM, and TPM tables as configured.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run an Illumina dry-run.
