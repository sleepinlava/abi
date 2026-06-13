# PlasmidFinder

## Purpose
Replicon and incompatibility typing, and optional homology evidence for plasmid detection.

## When to Use
Use after plasmid contig detection or as one detector in multi-tool mode.

## Inputs
`assembly` or `plasmid_contigs`, database path, `output_dir`.

- Registry inputs: `assembly, database`.
- Template parameters: `assembly, output_dir, database`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Replicon hit table and Inc typing calls.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `plasmidfinder.py`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`plasmidfinder.py -i {assembly} -o {output_dir} -p {database}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Enabled by default for typing.

## Interactive Parameters
Identity threshold, coverage threshold, and database path.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `assembly, database`.
Fail early if plasmid_contigs or required reference data are missing. Keep isolate-oriented limitations visible in the report or notes.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize typing/classification tables by sample_id and contig/plasmid ID.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Use as part of `plasmid_detection.tools` in `examples/config_full.yaml`.
