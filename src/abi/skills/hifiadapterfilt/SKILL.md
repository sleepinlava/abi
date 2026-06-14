# HiFiAdapterFilt

## Purpose
Remove adapters from PacBio HiFi reads.

## When to Use
Use for `pacbio_hifi` samples.

## Inputs
HiFi reads and output prefix.

- Registry inputs: `long_reads`.
- Template parameters: `sample_id, long_reads, output_dir, project_root`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Filtered HiFi reads.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/qc.yml` when present.
- Runtime environment: `autoplasm-qc`.
- Executable: `hifiadapterfilt.sh`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`bash -lc 'mkdir -p {output_dir} && input=$(realpath "{long_reads}") && cd {output_dir} && hifiadapterfilt.sh -p {sample_id} "$input" && sh "{project_root}/scripts/normalize_hifiadapterfilt_output.sh" {sample_id} {sample_id}.hifiadapterfilt.fastq.gz'`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected for PacBio HiFi QC.

## Interactive Parameters
Adapter database and prefix.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `long_reads`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize cleaned read paths to `01_qc/{sample_id}/{sample_id}.hifiadapterfilt.fastq.gz`
and parse log/stat files into `qc_summary.tsv`.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Use platform `pacbio_hifi`.
