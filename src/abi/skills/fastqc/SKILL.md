# FastQC

## Purpose
Generate per-file read quality reports.

## When to Use
Use before or after short-read QC.

## Inputs
FASTQ reads and `output_dir`.

- Registry inputs: `read1, read2`.
- Template parameters: `threads, output_dir, read1, read2`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
HTML and ZIP reports.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/qc.yml` when present.
- Runtime environment: `autoplasm-qc`.
- Executable: `fastqc`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`fastqc --threads {threads} --outdir {output_dir} {read1} {read2}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected for Illumina when `qc.run_fastqc` is true.

## Interactive Parameters
Input stage and output directory.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `read1, read2`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize cleaned read paths and QC report paths into the QC step output contract.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run `autoplasm dry-run --config examples/config_minimal.yaml`.
