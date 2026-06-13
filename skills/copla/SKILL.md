# COPLA

## Purpose
Plasmid taxonomic unit style classification.

## When to Use
Optional plasmid typing after plasmid detection.

## Inputs
`plasmid_contigs`, database, `output_dir`.

- Registry inputs: `plasmid_contigs, refgraph, reflist`.
- Template parameters: `plasmid_contigs, refgraph, reflist, output_dir`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
PTU classification table.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `copla`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`copla --input {plasmid_contigs} --refgraph {refgraph} --reflist {reflist} --output-dir {output_dir}`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Enabled when listed under `typing.tools`.

## Interactive Parameters
Database and score threshold.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `plasmid_contigs, refgraph, reflist`.
Fail early if plasmid_contigs or required reference data are missing. Keep isolate-oriented limitations visible in the report or notes.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize typing/classification tables by sample_id and contig/plasmid ID.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run default plan; COPLA is configured as optional typing.
