# clinker

## Purpose
Gene cluster comparison visualization.

## When to Use
Use after annotation when GenBank files are available.

## Inputs
GenBank files.

- Registry inputs: `genbank_files`.
- Template parameters: `genbank_files, output_dir, sample_id`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Interactive cluster plot HTML.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/visualization.yml` when present.
- Runtime environment: `autoplasm-visualization`.
- Executable: `clinker`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`clinker {genbank_files} -p {output_dir}/{sample_id}.clinker.html`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Selected only when configured and annotated GBK files exist.
- Limitation: Requires annotated GenBank files.

## Interactive Parameters
Minimum identity and plot format.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `genbank_files`.
Fail early if reference databases or GenBank/reference files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize hit, alignment, cluster, or synteny outputs with explicit database/reference provenance.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Enable clinker in comparative genomics and dry-run.
