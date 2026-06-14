# minimap2

## Purpose
Map long reads or align assemblies.

## When to Use
Default mapper for ONT and PacBio reads.

## Inputs
Long reads, plasmid contigs, `threads`.

- Registry inputs: `plasmid_contigs, long_reads`.
- Template parameters: `threads, minimap2_preset, plasmid_contigs, long_reads, output_dir, sample_id, alignment`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
PAF/SAM alignment.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/abundance.yml` when present.
- Runtime environment: `autoplasm-abundance`.
- Executable: `minimap2`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`minimap2 -t {threads} -ax {minimap2_preset} {plasmid_contigs} {long_reads} > {alignment}`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected for long-read abundance and comparative alignment. ONT defaults to `map-ont`;
PacBio HiFi planner steps set `map-hifi`.

## Interactive Parameters
Preset (`map-ont`, `map-hifi`, `asm5/asm10`).
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `plasmid_contigs, long_reads`.
Fail early if mapping indexes, BAM files, or read inputs are missing for the selected command template.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize abundance outputs toward raw counts, coverage, RPKM, and TPM tables as configured.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run a long-read dry-run.
