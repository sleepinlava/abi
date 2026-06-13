# Release Guide

`autoplasm-abi` is the only PyPI distribution produced from this repository.

## Pre-Release Checks

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short

rm -rf dist/
python -m build
python -m twine check dist/*
```

After building a wheel, smoke-test the installed commands in a clean
environment when possible:

```bash
abi list-types
autoplasm --help
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
```

## GitHub Actions

- `ci.yml` runs lint, format check, mypy, tests, and a build check.
- `release.yml` builds distributions and creates a GitHub Release for `v*` tags.
- `publish-pypi.yml` publishes the release artifact through PyPI Trusted Publishing.

The release workflow should not upload to PyPI directly; publishing is handled
by the dedicated PyPI workflow after a GitHub Release is published.
