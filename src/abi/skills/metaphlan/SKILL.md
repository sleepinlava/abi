# MetaPhlAn

## Purpose
Estimate species-level microbial abundance for host-correlation analyses.

## When to Use
Default taxonomy evidence for reads-based AutoPlasm workflows; optional for assembly-only workflows.

## Inputs
Reads, MetaPhlAn database, `threads`, `output_dir`.

- Registry inputs: reads are supplied through planner-derived `metaphlan_input`.
- Template parameters: `metaphlan_input, metaphlan_long_reads_flag, database, threads, output_dir, sample_id`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Taxonomic abundance table.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/stats.yml` when present.
- Runtime environment: `stats`.
- Executable: `metaphlan`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`metaphlan {metaphlan_input} --input_type fastq {metaphlan_long_reads_flag} --nproc {threads} --db_dir {database} -o {output_dir}/{sample_id}.metaphlan.tsv`

## Auto-selection Rules
- Registry state: `optional`, `recommended`.
Selected by default for Illumina, ONT, PacBio HiFi, and hybrid reads samples when `host_prediction.enable` is `auto`; assembly-only runs still require explicit configuration.

## Interactive Parameters
Database directory, taxonomic rank, and long-read mode.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `metaphlan_input, database`.
Fail early if required model/database paths are missing. Record that host predictions are evidence, not proof.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize species-level taxa into `host_predictions.tsv` as sample-level taxonomy evidence with an empty `contig_id`; do not treat MetaPhlAn abundance as definitive plasmid-host assignment.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run any reads smoke dry-run with `host_prediction.enable: auto`; configure `resources.metaphlan.database` before a real run.
