# AMRFinderPlus

## Purpose
Annotate antimicrobial resistance genes.

## When to Use
Use during plasmid annotation.

## Inputs
`plasmid_contigs`, optional organism/database settings.

- Registry inputs: `plasmid_contigs`.
- Template parameters: `plasmid_contigs, output_dir, sample_id`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
ARG table.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `amrfinder`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`amrfinder -n {plasmid_contigs} -o {output_dir}/{sample_id}.amrfinder.tsv`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected under `annotation.arg_tools`.

## Interactive Parameters
Database update policy and organism option.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `plasmid_contigs`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize annotation rows by feature category such as ARG, VF, MOB, IS, Tn, integron, oriT, and oriV when available.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run default dry-run.
