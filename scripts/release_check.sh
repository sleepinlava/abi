#!/usr/bin/env bash
set -euo pipefail

ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ --cov=src/abi --cov-fail-under=75 --cov-report=term-missing:skip-covered -q --tb=short
python -m build
abi query --type metagenomic_plasmid --what stages
