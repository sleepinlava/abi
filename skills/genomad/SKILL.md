# geNomad

## Purpose
Default plasmid detection from assembled contigs.

## When to Use
Use after assembly or for assembly-only input.

## Inputs
`assembly`, `database`, `output_dir`.

- Registry inputs: `assembly, database`.
- Template parameters: `assembly, output_dir, database`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
geNomad classification tables and candidate plasmid contigs.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/plasmid_detect.yml` when present.
- Runtime environment: `autoplasm-plasmid-detect`.
- Executable: `genomad`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`genomad end-to-end --cleanup --restart --threads {threads} {assembly} {output_dir} {database}`

## Auto-selection Rules
- Registry state: `default-enabled`, `required`.
Selected by default for plasmid detection with `single_tool` strategy.

## Interactive Parameters
Database path, score thresholds, and whether to combine with other detectors.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `assembly, database`.
For real execution, fail early if database/model parameters are absent. In dry-run, keep placeholders visible in commands.tsv.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize detector calls into plasmid prediction rows and expose plasmid_contigs.fasta for downstream steps.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
`autoplasm dry-run --config examples/config_minimal.yaml`
