#!/usr/bin/env bash
set -euo pipefail

release_tmpdir_created=
if [[ -z "${ABI_RELEASE_TMPDIR:-}" ]]; then
  release_tmp_root="${ABI_RELEASE_TMP_ROOT:-/tmp}"
  mkdir -p "$release_tmp_root"
  ABI_RELEASE_TMPDIR="$(mktemp -d "$release_tmp_root/abi-release-check.XXXXXX")"
  release_tmpdir_created=1
else
  mkdir -p "$ABI_RELEASE_TMPDIR"
fi
trap 'if [[ -n "${release_tmpdir_created:-}" ]]; then rm -rf "$ABI_RELEASE_TMPDIR"; fi' EXIT
export TMPDIR="$ABI_RELEASE_TMPDIR"
export TMP="$ABI_RELEASE_TMPDIR"
export TEMP="$ABI_RELEASE_TMPDIR"

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
