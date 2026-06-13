# MUMmer/nucmer

## Purpose
Whole-plasmid alignment and synteny evidence.

## When to Use
Optional comparative genomics step with reference plasmids.

## Inputs
Reference plasmids and query plasmid contigs.

- Registry inputs: `reference_plasmids, plasmid_contigs`.
- Template parameters: `output_dir, sample_id, reference_plasmids, plasmid_contigs`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Alignment coords and delta files.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `nucmer`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`nucmer --prefix {output_dir}/{sample_id} {reference_plasmids} {plasmid_contigs}`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Selected only when configured.
- Limitation: Requires a reference plasmid set; optional comparative step.

## Interactive Parameters
Reference set and minimum cluster length.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `reference_plasmids, plasmid_contigs`.
Fail early if reference databases or GenBank/reference files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize hit, alignment, cluster, or synteny outputs with explicit database/reference provenance.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Configure reference plasmids and dry-run.
