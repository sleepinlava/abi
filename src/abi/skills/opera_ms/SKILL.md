# OPERA-MS

## Purpose
Hybrid metagenomic assembly using short and long reads.

## When to Use
Default route for `hybrid` samples.

## Inputs
`read1`, `read2`, `long_reads`, `threads`, `output_dir`.

- Registry inputs: `read1, read2, long_reads`.
- Template parameters: `read1, read2, long_reads, output_dir, threads, project_root`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Hybrid assembly contigs and OPERA-MS reports.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/assembly.yml` when present.
- Runtime environment: `autoplasm-assembly`.
- Executable: `OPERA-MS.pl`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`bash -lc 'mkdir -p {output_dir} && OPERA-MS.pl --short-read1 "{read1}" --short-read2 "{read2}" --long-read "{long_reads}" --out-dir {output_dir} --num-processors {threads} && sh "{project_root}/scripts/normalize_opera_ms_output.sh" {output_dir} {output_dir}/contigs.fasta'`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected when short and long reads are both present and platform is `hybrid`.

## Interactive Parameters
Assembler internals, polishing choices, and complexity warning for metagenomes.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `read1, read2, long_reads`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize the primary contig FASTA to `02_assembly/{sample_id}/contigs.fasta`
as the downstream assembly input.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Use a hybrid sample in the sample sheet and run dry-run.
