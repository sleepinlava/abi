# MultiQC

## Purpose
Aggregate QC reports.

## When to Use
Use after QC tools have generated reports.

## Inputs
QC output directory.

- Registry inputs: ``.
- Template parameters: `output_dir`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
MultiQC HTML report.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/qc.yml` when present.
- Runtime environment: `autoplasm-qc`.
- Executable: `multiqc`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`multiqc {output_dir} --outdir {output_dir}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected when `qc.run_multiqc` is true.

## Interactive Parameters
Report title and input directories.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize cleaned read paths and QC report paths into the QC step output contract.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run a dry-run for an Illumina sample.
