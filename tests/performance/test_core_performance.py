from __future__ import annotations

import time
import tracemalloc

import pytest

from abi.dag_planner import build_plan_from_dag
from abi.executor import GenericABIExecutor
from abi.plugins import get_plugin
from abi.provenance import RunLogger
from abi.schemas import SampleContext, SampleInput
from abi.tables import StandardTableManager


@pytest.mark.performance
def test_100_sample_planning_and_dry_run_baseline(tmp_path, pytestconfig):
    """Guard the documented 100-sample latency and memory budgets."""
    plugin = get_plugin("metagenomic_plasmid")
    config = plugin.load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "logs"),
            "execution": {"progress": False},
        },
    )
    samples = [
        SampleInput(
            sample_id=f"S{index:03d}",
            platform="illumina",
            read1=f"/data/S{index:03d}_R1.fastq.gz",
            read2=f"/data/S{index:03d}_R2.fastq.gz",
        )
        for index in range(100)
    ]
    context = SampleContext(samples=samples, multi_sample=True, has_groups=False)

    tracemalloc.start()
    plan_started = time.perf_counter()
    plan = build_plan_from_dag(plugin.root / "pipeline_dag.yaml", config, context)
    plan_seconds = time.perf_counter() - plan_started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(plan.samples) == 100
    coverage_enabled = bool(getattr(pytestconfig.option, "cov_source", None))
    if not coverage_enabled:
        assert plan_seconds < 12.0
    assert peak_bytes < 500 * 1024 * 1024

    executor = GenericABIExecutor(
        plugin.registry(),
        RunLogger(tmp_path / "logs"),
        table_manager=StandardTableManager(plugin.table_schemas()),
        parse_outputs=plugin.parse_outputs,
        report_title=plugin.report_title,
        mock_tools=True,
        enforce_contracts=False,
    )
    dry_run_started = time.perf_counter()
    outputs = executor.dry_run(plan, config)
    dry_run_seconds = time.perf_counter() - dry_run_started

    if not coverage_enabled:
        assert dry_run_seconds < 30.0
    assert outputs["summary"].exists()
