# fastp

## Purpose
Quality control and adapter trimming for Illumina short reads.

## When to Use
Use for `illumina` or the short-read side of `hybrid` samples.

## Inputs
`read1`, optional `read2`, `threads`, `output_dir`.

- Registry inputs: `read1, read2`.
- Template parameters: `read1, read2, output_dir, sample_id, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Clean FASTQ files, HTML report, JSON report.

- Registry outputs: `clean_read1, clean_read2, html_report, json_report`.
- Expected fixed filenames are `{sample_id}_R1.clean.fastq.gz`,
  `{sample_id}_R2.clean.fastq.gz`, `{sample_id}.fastp.html`, and
  `{sample_id}.fastp.json`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/qc.yml` when present.
- Runtime environment: `autoplasm-qc`.
- Executable: `fastp`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`fastp -i {read1} -I {read2} -o {output_dir}/{sample_id}_R1.clean.fastq.gz -O {output_dir}/{sample_id}_R2.clean.fastq.gz --thread {threads} --html {output_dir}/{sample_id}.fastp.html --json {output_dir}/{sample_id}.fastp.json`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected automatically for Illumina samples when QC is enabled.
- Limitation: Short-read Illumina QC only.

## Interactive Parameters
Adapter trimming, quality thresholds, minimum length, and whether to skip if an assembler already performs preprocessing.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `read1, read2`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize cleaned read paths and QC report paths into the QC step output contract.
The ABI executor resolves actual files from `output_dir` before contract checks;
`clean_read1` must match the R1 file and `clean_read2` must match the R2 file.
The JSON report is used by assertions such as total read-count checks.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Dry-run through `autoplasm dry-run --config examples/config_minimal.yaml`.
