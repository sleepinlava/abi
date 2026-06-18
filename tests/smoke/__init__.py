"""Smoke tests for ABI plugins.

Smoke tests validate end-to-end pipeline behavior:
- ``test_dry_run_smoke.py`` — fast: plan generation + DAG validation (no tools needed)
- ``test_tool_smoke.py`` — slow: real tool execution with synthetic data (requires conda envs)

Usage:
    pytest tests/smoke/ -v                          # run all smoke tests
    pytest tests/smoke/ -v -m "not requires_tools"  # skip tool-dependent tests
    pytest tests/smoke/ -v -m smoke                 # only full smoke tests
"""
