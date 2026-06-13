# MMseqs2

## Purpose
Large-scale sequence search and clustering.

## When to Use
Use for plasmid clustering and comparative genomics.

## Inputs
FASTA query and target database.

- Registry inputs: `plasmid_contigs, database`.
- Template parameters: `plasmid_contigs, database, output_dir, sample_id, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Search or cluster tables.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `mmseqs`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`mmseqs easy-search {plasmid_contigs} {database} {output_dir}/{sample_id}.mmseqs.tsv {output_dir}/tmp --threads {threads}`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Selected when configured for comparative genomics.

## Interactive Parameters
Sensitivity, coverage mode, identity threshold.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `plasmid_contigs, database`.
Fail early if reference databases or GenBank/reference files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize hit, alignment, cluster, or synteny outputs with explicit database/reference provenance.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run default dry-run.
