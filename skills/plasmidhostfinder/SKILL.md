# PlasmidHostFinder

## Purpose
Predict candidate bacterial hosts for plasmids.

## When to Use
Use after plasmid contig detection.

## Inputs
`plasmid_contigs`, database, `output_dir`.

- Registry inputs: `plasmid_contigs, level, threshold, database`.
- Template parameters: `plasmid_contigs, output_dir, level, threshold, database`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Host prediction table.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/annotation.yml` when present.
- Runtime environment: `autoplasm-annotation`.
- Executable: `plasmidhostfinder.py`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`plasmidhostfinder.py -i {plasmid_contigs} -o {output_dir} -l {level} -t {threshold} -p {database}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Default host prediction tool.

## Interactive Parameters
Database and confidence threshold.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `plasmid_contigs, level, threshold, database`.
Fail early if required model/database paths are missing. Record that host predictions are evidence, not proof.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize host predictions as evidence tables; do not treat correlation or model output as definitive host assignment.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run `autoplasm dry-run --config examples/config_minimal.yaml`.
