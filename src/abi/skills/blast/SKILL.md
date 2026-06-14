# BLAST+

## Purpose
Homology search for plasmid detection evidence and comparative genomics.

## When to Use
Use when database similarity evidence is configured.

## Inputs
Query FASTA, BLAST database, `threads`.

- Registry inputs: `plasmid_contigs, database`.
- Template parameters: `plasmid_contigs, database, output_dir, sample_id, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Tabular BLAST hits.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `blastn`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`blastn -query {plasmid_contigs} -db {database} -out {output_dir}/{sample_id}.blast.tsv -outfmt 6 -num_threads {threads}`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Selected when listed in comparative genomics tools.

## Interactive Parameters
Database, identity, coverage, e-value.
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
