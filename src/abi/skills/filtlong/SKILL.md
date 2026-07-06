# Filtlong

## Purpose
Filter long reads by length and quality.

## When to Use
Use for ONT or PacBio reads when configured.

## Inputs
`long_reads`, thresholds, `output_dir`.

- Registry inputs: `long_reads`.
- Template parameters: `long_reads, output_dir, sample_id`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Filtered FASTQ.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/qc.yml` when present.
- Runtime environment: `autoplasm-qc`.
- Executable: `filtlong`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`filtlong --min_length 1000 --keep_percent 90 {long_reads} > {output_dir}/{sample_id}.filtlong.fastq`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected for ONT route as a lightweight long-read filter.

## Interactive Parameters
Minimum length, keep percent, target bases.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `long_reads`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize cleaned read paths and QC report paths into the QC step output contract.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run a long-read dry-run.
