# metaSPAdes

## Purpose
High-quality short-read metagenomic assembly.

## When to Use
Use when the user selects a higher-quality but slower Illumina route.

## Inputs
`read1`, optional `read2`, `threads`, `output_dir`.

- Registry inputs: `read1, read2`.
- Template parameters: `read1, read2, output_dir, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Contig FASTA and SPAdes assembly directory.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/assembly.yml` when present.
- Runtime environment: `autoplasm-assembly`.
- Executable: `metaspades.py`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`metaspades.py -1 {read1} -2 {read2} -o {output_dir} -t {threads}`

## Auto-selection Rules
- Registry state: `optional`, `required`.
Optional alternative to MEGAHIT for Illumina samples.

## Interactive Parameters
Memory, k-mer choices, careful mode constraints, and whether duplicate QC should be skipped.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `read1, read2`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize the primary contig FASTA path as the downstream assembly input.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Set `assembly.short_read_assembler: metaspades` then run dry-run.
