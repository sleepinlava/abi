# Repository Guidelines

## Project Structure & Module Organization

Core Python code lives in `src/abi/`. Keep transport-neutral behavior in the core; CLI, MCP, HTTP, and provider integrations should remain thin adapters. Built-in workflow implementations are split between Python entry points in `src/abi/plugins/` and declarative definitions in `plugins/<analysis_type>/` (`pipeline_dag.yaml`, tool registries, schemas, and report metadata). Tests are organized under `tests/unit/`, `tests/integration/`, and `tests/smoke/`; SciPlot also has focused tests in `src/abi/sciplot/tests/`. Use `examples/` for runnable configuration samples, `docs/en/` and `docs/zh/` for documentation, `envs/` for Conda environments, `environments.yaml` for tool→env assignments (18 envs, 98 tools), and `scripts/` for maintenance utilities.

Current codebase (2026-07-09): 209 Python source files (~51.5k lines), plasmid engine (11,823 lines), 44-file sciplot module (3,912 lines), 134 test files (2,121 passed), 79% coverage.

## Build, Test, and Development Commands

- `pip install -e ".[dev]"` installs ABI and development tools in editable mode.
- `pytest tests/ -v --tb=short` runs the main test suite.
- `pytest tests/unit/test_dag.py -q` runs a focused test module.
- `pytest tests/ --cov=src/abi --cov-fail-under=75` checks the CI coverage floor.
- `ruff check src/ tests/` checks lint and import rules.
- `ruff format --check src/ tests/` verifies formatting; omit `--check` to format locally.
- `mypy src/abi/ --ignore-missing-imports` performs static type checking.
- `python -m build` creates wheel and source distributions.
- `abi query --type metagenomic_plasmid --what stages` lightweight metadata query (~50ms).
- `abi-sciplot validate --spec figure.yaml` validates a FigureSpec before rendering.

## Coding Style & Naming Conventions

Target Python 3.10 and use four-space indentation with a 100-character line limit. Ruff enforces `E`, `F`, `I`, and `W` rules and supplies formatting. Use `snake_case` for modules, functions, fixtures, and YAML analysis types; use `PascalCase` for classes and `UPPER_SNAKE_CASE` for constants. Add type annotations to public APIs and preserve the "thick core, thin transport, clean plugin" architecture. Run `pre-commit install` to apply Ruff, mypy, YAML/TOML, whitespace, and large-file checks before commits.

## Testing Guidelines

Name test files `test_<feature>.py` and test functions `test_<behavior>`. Add fast isolated checks to `tests/unit/`, cross-component checks to `tests/integration/`, and tool-dependent workflows to `tests/smoke/`. Mark real-tool tests with `@pytest.mark.smoke` and/or `@pytest.mark.requires_tools`. Include regression tests with every behavior change; keep total coverage at or above 60%.

## Commit & Pull Request Guidelines

History uses concise imperative subjects prefixed by scope, such as `feat:`, `fix:`, and `docs:`. Keep each commit focused. Pull requests should explain the problem and solution, list validation commands, link relevant issues, and note configuration or compatibility effects. Include screenshots or generated artifacts for report, documentation, or figure changes. Ensure lint, formatting, typing, tests, and bilingual documentation updates (when applicable) pass before review.

## End-to-End Development Workflow

Treat every change as a traceable sequence: define the behavior and acceptance criteria; inspect the
owning core, adapter, plugin, and documentation boundaries; implement the smallest coherent change;
add a regression test; run focused checks; then run the repository quality gates. Do not mix unrelated
refactors with behavior changes. Keep generated Conda YAMLs synchronized with `environments.yaml`, and
keep Docker build inputs (`docker/`, `envs/*.yml`, package metadata, plugin definitions, and runtime
scripts) available in the build context.

Before requesting review, run the checks proportional to the change. Python changes require Ruff,
mypy, focused pytest, and the affected integration tests. Plugin changes also require strict
`abi contract-lint`, dry-run validation, and relevant smoke tests. Docker changes require Compose
configuration validation, Docker configuration regression tests, a representative image build, and
`abi list-types` inside the image. Documentation changes require `bash docs/build_docs.sh`. Release
changes additionally require package build, `twine check`, wheel smoke tests, and release-identity
validation. Record every command and result in the pull request; explicitly identify checks that could
not be run and their residual risk. See `docs/zh/development_workflow.md` for the full developer guide.

## Local Codex Cloud Access

This workspace may include a local, git-ignored `.key` file for the cloud
development machine. Treat it as a secret and never print, paste, commit, or
summarize its contents. The expected format is:

```text
ssh -p <port> <user>@<host>
<password>
```

Use the local ignored helper `.codex/abi-cloud-ssh` to connect. It reads `.key`
without exposing the password and supports either an interactive SSH session or
a remote command:

```bash
.codex/abi-cloud-ssh
.codex/abi-cloud-ssh 'hostname && whoami && pwd'
.codex/abi-cloud-ssh 'cd /root && ls -la'
```

Network/SSH commands require sandbox escalation. Before running long remote
jobs, verify the current target with a read-only probe such as `hostname`,
`whoami`, `pwd`, and optionally `nvidia-smi`. SeetaCloud web port mappings such
as `6006` or `6008` are service URLs, not the SSH control endpoint.
