#!/usr/bin/env bash
set -euo pipefail

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
