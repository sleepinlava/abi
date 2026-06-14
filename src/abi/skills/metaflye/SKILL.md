# metaFlye

## Purpose
Long-read metagenomic assembly through Flye `--meta`.

## When to Use
Default assembler for ONT long-read metagenomes.

## Inputs
`long_reads`, `threads`, `output_dir`.

- Registry inputs: `long_reads`.
- Template parameters: `long_reads, output_dir, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Contig FASTA and assembly graph.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/assembly.yml` when present.
- Runtime environment: `autoplasm-assembly`.
- Executable: `flye`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`flye --meta --nano-raw {long_reads} --out-dir {output_dir} --threads {threads}`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected for `ont` samples.

## Interactive Parameters
Read type, genome size estimate, polishing settings.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `long_reads`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize the primary contig FASTA path as the downstream assembly input.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
`autoplasm run-single --input ont.fastq --platform ont --dry-run`
