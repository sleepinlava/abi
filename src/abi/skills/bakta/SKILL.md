# Bakta

## Purpose
General plasmid sequence annotation.

## When to Use
Default general annotation tool for predicted plasmid contigs.

## Inputs
`plasmid_contigs`, Bakta database, `threads`, `output_dir`.

- Registry inputs: `plasmid_contigs`.
- Template parameters: `database, output_dir, threads, plasmid_contigs`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
GFF, GBK, TSV, FAA, and FFN annotation outputs.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `bakta`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`bakta --db {database} --output {output_dir} --threads {threads} {plasmid_contigs}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected when `annotation.enable` is true.

## Interactive Parameters
Database path, locus tag prefix, completeness mode.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `database, plasmid_contigs`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize annotation rows by feature category such as ARG, VF, MOB, IS, Tn, integron, oriT, and oriV when available.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
`autoplasm dry-run --config examples/config_minimal.yaml`
