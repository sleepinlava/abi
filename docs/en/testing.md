# ABI Testing Guide

> **Current state (2026-06-21)**: 723 tests passed, 4 skipped, 62 test files, 0 ruff errors, 0 mypy errors.

This guide covers the ABI testing infrastructure: test taxonomy, shared fixtures, the benchmark framework, contract validation, golden traces, smoke tests, CI/CD, and conventions for plugin authors.

## Test Taxonomy

ABI tests are organized into four layers by scope and speed:

| Layer | Directory | Purpose | Speed | Requires tools? |
|-------|-----------|---------|-------|-----------------|
| **Unit** | `tests/unit/` | Isolated logic tests for core modules | < 1s each | No |
| **Integration** | `tests/integration/` | Cross-component tests (CLI, dry-run, golden traces) | 1-10s each | No |
| **Smoke** | `tests/smoke/` | Real tool execution with synthetic data | 30s-5min each | Yes |
| **Benchmark** | `tests/smoke/test_*_benchmark.py` | Value-level validation against expected outputs | 30s-5min each | Yes |

### When to use each layer

- **Unit tests**: For parser functions, schema validation, DAG logic, contract evaluation. Always add unit tests for new parsing logic or schema changes.
- **Integration tests**: For CLI argument handling, dry-run artifact generation, cross-plugin consistency.
- **Smoke tests**: When a new tool contract is added and you need to verify real execution. Mark with `@pytest.mark.smoke`.
- **Benchmark tests**: For end-to-end pipeline validation with known datasets. Use `run_benchmark()` from `abi.testing`.

## Running Tests

```bash
# All tests
pytest tests/ -v --tb=short

# Only fast tests (skip real-tool tests)
pytest tests/ -v -m "not requires_tools"

# Only smoke tests
pytest tests/ -v -m smoke

# Single test file
pytest tests/unit/test_dag_planner.py -v

# Single test function
pytest tests/unit/test_dag_planner.py::test_build_plan_per_sample -v

# With coverage
pytest tests/ --cov=src/abi --cov-report=term --cov-fail-under=60
```

## Shared Fixtures

All fixtures live in `tests/conftest.py` and are available to every test file without explicit import.

### `mock_sample`

A minimal valid `ABISample` suitable for plugin tests:

```python
def test_my_parser(mock_sample):
    assert mock_sample.sample_id == "S1"
    assert mock_sample.platform == "illumina"
    assert mock_sample.group == "treatment"
```

### `mock_sample_context`

A single-sample `ABISampleContext` built from `mock_sample`:

```python
def test_plan_builder(mock_sample_context):
    assert len(mock_sample_context.samples) == 1
    assert mock_sample_context.multi_sample is False
```

### `mock_contract_dict`

A minimal valid tool contract dict for lint/test scaffolding:

```python
def test_contract_lint(mock_contract_dict):
    assert mock_contract_dict["tool_id"] == "fastp"
    assert mock_contract_dict["execution"]["env_name"] == "abi-qc"
```

### `tmp_project`

A temporary directory with `results/`, `logs/`, `provenance/`, and `tables/` subdirectories:

```python
def test_output_writer(tmp_project):
    results_dir = tmp_project / "results"
    # write outputs, verify they land correctly
```

### Adding new fixtures

Add shared fixtures to `tests/conftest.py`. Plugin-specific fixtures should go in the plugin's test file or a `conftest.py` in the plugin test directory.

Use naming convention `mock_<thing>` for test doubles, `tmp_<thing>` for temporary scaffolding, and `real_<thing>` for fixtures that require real data.

## Plugin Contract Testing

Every plugin must pass `assert_plugin_contract(plugin)`:

```python
from abi.testing import assert_plugin_contract
from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin


def test_plugin_contract():
    plugin = RNASeqExpressionPlugin()
    assert_plugin_contract(plugin)
```

`assert_plugin_contract` verifies:

1. The plugin implements `ABIPlugin` (required) — checks for all 9 mandatory methods/attributes:
   `plugin_id`, `display_name`, `description`, `report_title`, `load_config`,
   `build_plan`, `registry`, `table_schemas`, `parse_outputs`, `write_report`

2. If the plugin implements `ABIDryRunPlugin` (optional) — checks for `execute_dry_run`

3. If the plugin implements `ABIInitializablePlugin` (optional) — checks for `root`

All 5 built-in plugins have contract tests. Run with:

```bash
pytest tests/ -k "contract" -v
```

## Benchmark Framework

`abi.testing.benchmark` provides a unified framework for value-level pipeline validation.
All five plugins have benchmark tests using this framework.

### `BenchmarkAssertion`

A single assertion against a pipeline output:

| Field | Type | Description |
|-------|------|-------------|
| `step_id` | `str` | DAG step name (e.g. `"fastp"`, `"star_align"`) |
| `table` | `str` | Output table path relative to result_dir |
| `column` | `str` | Column to check, or `""` for file-level checks |
| `condition` | `str` | Comparison: `"exists"`, `">"`, `">="`, `"<="`, `"contains"`, `"between"` |
| `expected` | `Any` | Expected value. For `"between"`: `[min, max]` |
| `description` | `str` | Human-readable description |

### `BenchmarkResult`

Returned by `run_benchmark()`:

```python
@dataclass
class BenchmarkResult:
    plugin_id: str
    passed: int
    failed: int
    total: int
    assertions: list[BenchmarkAssertion]
    failures: list[BenchmarkAssertion]
    errors: list[str]
```

### Writing a benchmark test

Benchmark tests follow this pattern:

```python
from pathlib import Path
import pytest
from abi.testing.benchmark import BenchmarkResult, run_benchmark


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_rnaseq_expression_benchmark(tmp_path):
    result = run_benchmark(
        plugin_id="rnaseq_expression",
        dataset_path=Path("data/benchmarks/rnaseq_expression"),
        outdir=tmp_path / "results",
    )

    assert result.total > 0, "No assertions defined"
    assert result.passed >= result.total * 0.8, (
        f"Benchmark failed: {result.passed}/{result.total} passed\n"
        + "\n".join(f"  - {f.description}" for f in result.failures)
    )
```

### Benchmark configuration

Each benchmark dataset in `data/benchmarks/<plugin_id>/` contains:

```
data/benchmarks/rnaseq_expression/
  expected_assertions.yaml    # list of BenchmarkAssertion dicts
  config.yaml                 # plugin-specific config for the run
  samples.tsv                 # sample sheet with benchmark data paths
```

## Golden Traces

Golden traces are pre-recorded execution plans that capture expected DAG output for known inputs.
They enable deterministic regression testing of the DAG planner.

Golden traces live in `tests/fixtures/golden_traces/` and are replayed via integration tests:

```bash
pytest tests/integration/test_golden_traces.py -v
```

### Creating a new golden trace

1. Run a dry-run against the target configuration:
   ```bash
   abi dry-run --type my_plugin --config my_config.yaml --outdir /tmp/golden
   ```

2. Copy the execution plan to `tests/fixtures/golden_traces/`:
   ```bash
   cp /tmp/golden/execution_plan.json tests/fixtures/golden_traces/my_plugin_golden.json
   ```

3. Add a test in `tests/integration/test_golden_traces.py`:
   ```python
   def test_my_plugin_golden_trace():
       expected = load_golden_trace("my_plugin_golden.json")
       actual = build_plan(...)
       assert_plans_match(expected, actual)
   ```

## Smoke Tests

Smoke tests execute real bioinformatics tools with synthetic data to verify tool contracts,
parsers, and output contracts work end-to-end.

### Smoke test conventions

- Mark with `@pytest.mark.smoke` and `@pytest.mark.requires_tools`
- Generate synthetic input data in the test (no checked-in FASTQ files)
- Use small data sizes (500-1000 reads) for speed
- Verify key output artifacts exist (files, directories)
- Verify parser output has expected columns and non-trivial values
- Clean up with `tmp_path` (pytest auto-cleans)

### Example smoke test

```python
import pytest
from pathlib import Path
from abi.plugins.amplicon_16s import Amplicon16SPlugin


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_amplicon_smoke(tmp_path):
    plugin = Amplicon16SPlugin()
    # Generate synthetic reads...
    # Run pipeline...
    # Verify outputs...
    assert (tmp_path / "tables" / "asv_table.tsv").exists()
```

To skip smoke tests in environments without bioinformatics tools:

```bash
pytest tests/ -v -m "not requires_tools"
```

## CI/CD Pipeline

ABI uses GitHub Actions with two workflows:

### `ci.yml` — Runs on every push and PR

| Step | Python Versions |
|------|----------------|
| `ruff check` | 3.10, 3.11, 3.12, 3.13 |
| `ruff format --check` | 3.10, 3.11, 3.12, 3.13 |
| `mypy src/abi/` | 3.10, 3.11, 3.12, 3.13 |
| `pytest tests/` | 3.10, 3.11, 3.12, 3.13 |
| `pytest --cov --cov-fail-under=60` | 3.12 only |
| Sphinx docs build | 3.12 only |
| Wheel build + smoke test | 3.12 only |

### `release.yml` — Builds and creates GitHub Release for `v*` tags

### `publish-pypi.yml` — Publishes to PyPI via Trusted Publishing

## Test Writing Conventions

### File naming

- Test files: `test_<feature>.py`
- Test functions: `test_<behavior>`
- Example: `tests/unit/test_dag_planner.py::test_build_plan_per_sample`

### Code quality gates

All tests must pass these gates before commit:

```bash
ruff check src/ tests/        # 0 errors
ruff format --check src/ tests/  # 236 files formatted
mypy src/abi/ --ignore-missing-imports  # 0 errors
pytest tests/ -v --tb=short   # 723+ passed
```

### Isolation

- Use `tmp_path` (pytest built-in) for file system isolation — never write to project directories
- Use `mock_sample` and `mock_sample_context` fixtures for shared test data — avoid duplicating sample construction
- Do not depend on test execution order — every test should be independently runnable

### Contract testing for plugins

Every new plugin should include at minimum:

```python
def test_plugin_contract():
    """Plugin satisfies the ABIPlugin protocol."""
    from abi.testing import assert_plugin_contract
    plugin = MyPlugin()
    assert_plugin_contract(plugin)


def test_registry_loads():
    """Tool registry YAML parses without error."""
    plugin = MyPlugin()
    registry = plugin.registry()
    assert len(registry.tools) > 0


def test_build_plan():
    """build_plan() returns valid ExecutionPlan for default config."""
    plugin = MyPlugin()
    plan = plugin.build_plan(...)
    assert len(plan.steps) > 0
    # Verify step ordering
    tool_ids = [s.step_id for s in plan.steps]
    assert tool_ids[0] == "qc_fastp"  # QC always first
```

### Benchmark test thresholds

Benchmark tests should target:

| Stage | Threshold | When |
|-------|-----------|------|
| **Development** | ≥ 70% assertions pass | Plugin under active development |
| **Stable** | ≥ 80% assertions pass | Plugin with verified parsers |
| **Release** | ≥ 85% assertions pass | Plugin candidate for release |

## Coverage

CI enforces a minimum 60% line coverage floor. The current coverage baseline is maintained through:

- Unit tests for all parser functions
- Integration tests for CLI and dry-run paths
- Contract tests for all 5 plugins

To check coverage locally:

```bash
pip install pytest-cov
pytest tests/ --cov=src/abi --cov-report=html
# Open htmlcov/index.html
```

## Troubleshooting Tests

### Test fails with "tool not found"

Ensure conda environments are set up and the tool is on PATH:

```bash
abi check-resources --type <plugin_id>
```

### Benchmark assertion fails

1. Check `expected_assertions.yaml` — are expected values still correct?
2. Has the tool output format changed? Re-run and update expected values.
3. Check if the tool version changed — some tools change output formats between versions.

### Contract-lint shows `output_dir.exists()` errors

This is a known limitation of static contract analysis — `output_dir` is not in scope during lint.
Runtime contract enforcement works correctly. This does not affect execution.

### Test isolation issues

If tests interfere with each other, ensure:
- Each test uses a unique `tmp_path`
- No test modifies global state (`os.environ`, module-level variables, `sys.path`)
- Tests that require real tools are marked `@pytest.mark.requires_tools`

## See Also

- `docs/en/plugin_development_guide.md` — How to structure plugin code
- `docs/en/development.md` — Source tree and SDK reference
- `CLAUDE.md` — Project commands and architecture
