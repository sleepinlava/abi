# Release Guide

`abi-agent` is the only PyPI distribution produced from this repository.

## Pre-Release Checks

Run the consolidated release check before tagging or publishing:

```bash
scripts/release_check.sh
```

Before pushing a release candidate, confirm `CHANGELOG.md` has a section for
the exact `project.version` in `pyproject.toml`; CI enforces this with
`scripts/check_release_identity.py`.

The script creates a POSIX temporary directory under `/tmp` by default and
exports `TMPDIR`, `TMP`, and `TEMP` before running tests. This keeps
permission-sensitive checks off WSL/Windows-mounted temporary directories. Use
`ABI_RELEASE_TMPDIR` or `ABI_RELEASE_TMP_ROOT` to override the location.

The script runs the same quality gate expected by CI:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
python -m pytest tests/ src/abi/sciplot/tests/ -v --tb=short \
  --strict-markers -m "not requires_tools" --capture=no \
  --cov=src/abi --cov-branch --cov-report=term-missing:skip-covered \
  --cov-report=xml --cov-report=json:coverage.json --cov-fail-under=75
python scripts/check_module_coverage.py --coverage coverage.json

python -m build
abi query --type metagenomic_plasmid --what stages
```

After building a wheel, smoke-test the installed commands in a clean
environment when possible:

```bash
abi list-types
abi query --type metagenomic_plasmid --what stages
abi query --type rnaseq_expression --what tools
autoplasm --help
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
abi doctor-agent --type metatranscriptomics
abi export-openai-tools --type metatranscriptomics --format json
abi install-skills --target /tmp/abi-smoke-skills
abi-mcp --help 2>/dev/null || python -m abi.mcp.server --help 2>/dev/null || true
```

## GitHub Actions

- `ci.yml` runs lint, format check, mypy, tests, and a build check.
- `release.yml` builds distributions and creates a GitHub Release for `v*` tags.
- `publish-pypi.yml` publishes the release artifact through PyPI Trusted Publishing.
- `opencode.yml` expects `DEEPSEEK_API_KEY` to be configured as a GitHub Actions
  secret; never place provider API keys directly in workflow YAML.

The release workflow should not upload to PyPI directly; publishing is handled
by the dedicated PyPI workflow after a GitHub Release is published.
