# Kraken2

## Purpose
Estimate bacterial community composition for host-correlation analyses.

## When to Use
Use when plasmid-bacteria network or host-correlation analysis is enabled.

## Inputs
Reads, Kraken2 database, `threads`, `output_dir`.

- Registry inputs: `database, read1, read2`.
- Template parameters: `threads, database, output_dir, sample_id, read1, read2`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Kraken2 classification output and report.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/stats.yml` when present.
- Runtime environment: `stats`.
- Executable: `kraken2`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`kraken2 --threads {threads} --db {database} --report {output_dir}/{sample_id}.kraken2.report {read1} {read2}`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Optional; selected only when configured.

## Interactive Parameters
Database path, confidence threshold, paired/single mode.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `database, read1, read2`.
Fail early if required model/database paths are missing. Record that host predictions are evidence, not proof.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize host predictions as evidence tables; do not treat correlation or model output as definitive host assignment.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Enable under host prediction or network settings, then dry-run.
