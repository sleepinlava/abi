# PlasMAAG

## Purpose
Candidate plasmid binning or reconstruction.

## When to Use
Use after plasmid contig detection when configured.

## Inputs
`plasmid_contigs`, optional coverage profile, `threads`, `output_dir`.

- Registry inputs: `reads_contigs_table`.
- Template parameters: `reads_contigs_table, output_dir, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Candidate plasmid bins, bin membership, and summary tables.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/plasmid_binning.yml` when present.
- Runtime environment: `autoplasm-plasmid-binning`.
- Executable: `plasmaag`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`plasmaag --reads_and_contigs {reads_contigs_table} --output {output_dir} --threads {threads}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected as a default candidate binning tool through the dedicated repository-local `autoplasm-plasmaag` environment.
- Limitation: Runs through the dedicated repository-local autoplasm-plasmaag Python 3.11 environment; first real run may initialize the geNomad database.

## Interactive Parameters
Coverage input, graph input, and bin confidence thresholds.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `reads_contigs_table`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize bin/reconstruction assignments as candidate plasmid groups without over-interpreting completeness.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Dry-run through `autoplasm dry-run --config examples/config_minimal.yaml`.
