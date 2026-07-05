"""Golden file tests for DAG migration — compare legacy vs new planner output."""

import json
import os
import sys
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).parent / "data" / "dag_migration"


def _load_golden(name: str) -> dict:
    path = TEST_DATA_DIR / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_golden(name: str, data: dict) -> None:
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (TEST_DATA_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))


def _plan_steps_to_dict(plan) -> dict:
    """Convert a PlanSteps object to a comparable dict."""
    steps = []
    for step in plan.steps:
        steps.append({
            "step_id": step.step_id,
            "tool_id": step.tool_id,
            "sample_id": getattr(step, "sample_id", ""),
            "category": getattr(step, "category", ""),
            "skip": getattr(step, "skip", False),
            "outputs": {k: str(v) for k, v in (step.outputs or {}).items()},
            "params": {k: str(v) for k, v in (step.params or {}).items()},
        })
    return {
        "step_count": len(steps),
        "steps": steps,
    }


@pytest.mark.slow
def test_golden_file_legacy_illumina_isolate():
    """Record/verify golden output for illumina isolate profile."""
    if os.environ.get("ABI_DAG_GOLDEN_RECORD"):
        # Recording mode
        from abi.plugins.metagenomic_plasmid._engine.planner import _build_plan_legacy
        from abi.config import load_yaml

        plugin_root = Path(__file__).parent.parent.parent / "plugins" / "metagenomic_plasmid"
        config = load_yaml(plugin_root / "config_default.yaml")
        plan = _build_plan_legacy(config, check_files=False)
        _save_golden("illumina_isolate", _plan_steps_to_dict(plan))
        pytest.skip("Golden file recorded")
    else:
        # Verification mode: run legacy and compare
        golden = _load_golden("illumina_isolate")
        if not golden:
            pytest.skip("No golden file — run with ABI_DAG_GOLDEN_RECORD=1 first")

        from abi.plugins.metagenomic_plasmid._engine.planner import _build_plan_legacy
        from abi.config import load_yaml

        plugin_root = Path(__file__).parent.parent.parent / "plugins" / "metagenomic_plasmid"
        config = load_yaml(plugin_root / "config_default.yaml")
        plan = _build_plan_legacy(config, check_files=False)
        current = _plan_steps_to_dict(plan)

        assert current["step_count"] == golden["step_count"], (
            f"Step count mismatch: {current['step_count']} vs {golden['step_count']}"
        )
        # Compare individual steps
        for i, (g_step, c_step) in enumerate(zip(golden["steps"], current["steps"])):
            assert g_step == c_step, f"Step {i} ({g_step.get('step_id')}) differs"


@pytest.mark.slow
def test_golden_legacy_vs_new_illumina_isolate():
    """Verify legacy and new planner produce identical output."""
    if not os.environ.get("ABI_DAG_PLANNER_LEGACY_COMPARE"):
        pytest.skip("Set ABI_DAG_PLANNER_LEGACY_COMPARE=1 to run comparison")

    from abi.plugins.metagenomic_plasmid._engine.planner import (
        _build_plan_legacy,
        _build_plan_new,
    )
    from abi.config import load_yaml

    plugin_root = Path(__file__).parent.parent.parent / "plugins" / "metagenomic_plasmid"
    config = load_yaml(plugin_root / "config_default.yaml")

    legacy_plan = _build_plan_legacy(config, check_files=False)
    new_plan = _build_plan_new(config, check_files=False)

    legacy_dict = _plan_steps_to_dict(legacy_plan)
    new_dict = _plan_steps_to_dict(new_plan)

    assert legacy_dict == new_dict, (
        f"Legacy vs new planner output differs!\n"
        f"Legacy steps: {legacy_dict['step_count']}\n"
        f"New steps: {new_dict['step_count']}"
    )


@pytest.mark.slow
def test_feature_flag_default_legacy(monkeypatch):
    """Default (no env var) should use legacy path."""
    monkeypatch.delenv("ABI_DAG_PLANNER_LEGACY", raising=False)

    from abi.plugins.metagenomic_plasmid._engine import planner
    import importlib
    importlib.reload(planner)

    assert planner._LEGACY_BUILD_PLAN is True, "Default should be legacy mode"


def test_feature_flag_new_path(monkeypatch):
    """Setting ABI_DAG_PLANNER_LEGACY=0 should use new path."""
    monkeypatch.setenv("ABI_DAG_PLANNER_LEGACY", "0")

    from abi.plugins.metagenomic_plasmid._engine import planner
    import importlib
    importlib.reload(planner)

    assert planner._LEGACY_BUILD_PLAN is False, "Should switch to new path"
