# hifiasm

## Purpose
PacBio HiFi assembly fallback for the unavailable `hifiasm-meta` package.

## When to Use
Default PacBio HiFi assembler.

## Inputs
`long_reads`, `threads`, `output_dir`.

- Registry inputs: `long_reads`.
- Template parameters: `threads, output_dir, sample_id, long_reads, project_root`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Assembly graph and contig FASTA after conversion.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/assembly.yml` when present.
- Runtime environment: `autoplasm-assembly`.
- Executable: `hifiasm`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`bash -lc 'mkdir -p {output_dir} && hifiasm -t {threads} -o {output_dir}/{sample_id} "{long_reads}" && sh "{project_root}/scripts/hifiasm_gfa_to_fasta.sh" {output_dir}/{sample_id} {output_dir}/{sample_id}.hifiasm.fasta'`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected for `pacbio_hifi` samples.
- Limitation: hifiasm-meta is not resolvable from the configured channels under the required python=3.9 environments; this registry entry uses hifiasm as the installable fallback.

## Interactive Parameters
Purge settings and graph conversion mode.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `long_reads`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize the primary GFA segment records to
`02_assembly/{sample_id}/{sample_id}.hifiasm.fasta` as the downstream assembly input.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run a PacBio HiFi dry-run.
