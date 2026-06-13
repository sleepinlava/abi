# samtools

## Purpose
Sort, index, and summarize alignments.

## When to Use
Use after bowtie2, bwa, or minimap2 mapping.

## Inputs
SAM/BAM alignment.

- Registry inputs: `alignment`.
- Template parameters: `threads, alignment, bam`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Sorted BAM, index, stats.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/abundance.yml` when present.
- Runtime environment: `autoplasm-abundance`.
- Executable: `samtools`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`samtools sort -@ {threads} -o {bam} {alignment}`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected as an abundance support tool when mapping is enabled.

## Interactive Parameters
Sort memory and thread count.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `alignment`.
Fail early if mapping indexes, BAM files, or read inputs are missing for the selected command template.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize abundance outputs toward raw counts, coverage, RPKM, and TPM tables as configured.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run abundance dry-run.
