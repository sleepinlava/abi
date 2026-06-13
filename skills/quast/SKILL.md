# metaQUAST

## Purpose
Assess metagenomic assembly quality.

## When to Use
Use after assembly or for assembly-only input.

## Inputs
Assembly FASTA and `threads`.

- Registry inputs: `assembly`.
- Template parameters: `assembly, output_dir, threads`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
Assembly QC report.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/assembly.yml` when present.
- Runtime environment: `autoplasm-assembly`.
- Executable: `metaquast.py`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`metaquast.py {assembly} -o {output_dir} -t {threads}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Selected when `assembly.assembly_qc` is true.

## Interactive Parameters
Reference genomes and minimum contig length.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `assembly`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize assembly metrics and report paths for the assembly QC section.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run `autoplasm plan --config examples/config_minimal.yaml`.
