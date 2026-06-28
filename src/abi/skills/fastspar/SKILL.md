# FastSpar

## Purpose
Compositional-aware correlation network inference.

## When to Use
Default plasmid-bacteria network method for multi-sample analysis.

## Inputs
Standardized abundance table, `threads`, `output_dir`.

- Registry inputs: `abundance_table`.
- Template parameters: `abundance_table, output_dir, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Correlation and covariance tables.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/stats.yml` when present.
- Runtime environment: `stats`.
- Executable: `fastspar`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`fastspar --otu_table {abundance_table} --correlation {output_dir}/correlation.tsv --covariance {output_dir}/covariance.tsv --threads {threads}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected for multi-sample network analysis when enabled.

## Interactive Parameters
Iterations, exclusion threshold, bootstrap count.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `abundance_table`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize correlation/covariance outputs and network edges for downstream visualization.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Use the example sample sheet with two samples and run dry-run.
