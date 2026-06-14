# AutoPlasm Markdown report

## Purpose
Generate Markdown and methods summaries from standard outputs.

## When to Use
At the end of every plan.

## Inputs
Project result directory and provenance.

- Registry inputs: `project_outdir`.
- Template parameters: `project_outdir`.
- AutoPlasm merges sample fields, step params, and step outputs before rendering the command.

## Outputs
`report.md` and `methods.md`.

- Registry outputs: `output_dir, tool-specific result files`.
- Step stdout/stderr from real execution are captured under `provenance/step_logs/`.

## Environment
- Environment file: `envs/base.yml` when present.
- Runtime environment: `autoplasm-base`.
- Executable: `autoplasm`.
- The CLI resolves the executable from `.mamba/envs/{env_name}/bin`; do not depend on a global conda/mamba environment.

## Command Template
`autoplasm report --result-dir {project_outdir}`

## Auto-selection Rules
- Registry state: `default-enabled`, `recommended`.
Always selected for report generation.

## Interactive Parameters
Report title and optional sections.
- In current CLI behavior, `interactive` is recorded as mode; agents should surface choices to users before writing config values.

## Failure Handling
- Run `autoplasm dry-run` first and inspect `provenance/commands.tsv`.
- For real execution, ensure these rendered parameters are non-empty and not placeholders: `project_outdir`.
Fail clearly if required inputs, executables, databases, or output files are missing.
- On failure, inspect `provenance/commands.tsv` and the matching `provenance/step_logs/{step_id}.stderr.log`.

## Normalization
Normalize report paths and methods text under the report directory.

## Agent Usage Notes
- Prefer editing config files or sample sheets, then run `autoplasm plan` and `autoplasm dry-run` before real execution.
- Do not hand-run this command outside AutoPlasm unless debugging a single failed step; preserve provenance through the CLI whenever possible.
- Do not claim biological completion from dry-run output; it only validates planning and command rendering.

## Example
Run `autoplasm report --result-dir results/autoplasm_project`.
