from __future__ import annotations

import json

import pytest

from abi.plugins import get_plugin
from abi.runtimes import RuntimeOptions
from abi.schemas import ABIError
from abi.workflow import WorkflowCoordinator


def test_coordinator_prepares_resolved_config_and_canonical_plan(tmp_path):
    prepared = WorkflowCoordinator().prepare(
        "easymetagenome",
        overrides={
            "workflow": {"preset": "p1_humann4"},
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "logs"),
        },
        check_files=False,
    )

    assert (
        prepared.analysis_type,
        prepared.config["workflow"]["preset"],
        prepared.plan.analysis_type,
    ) == ("easymetagenome", "p1_humann4", "easymetagenome")


def test_coordinator_dry_run_uses_selected_runtime_and_writes_abi_result(tmp_path):
    coordinator = WorkflowCoordinator()
    prepared = coordinator.prepare(
        "viral_viwrap",
        overrides={
            "outdir": str(tmp_path / "result"),
            "log_dir": str(tmp_path / "logs"),
        },
        check_files=False,
        options=RuntimeOptions(engine="local"),
    )

    result = coordinator.dry_run(prepared)
    summary = json.loads(result.outputs["summary"].read_text(encoding="utf-8"))

    assert (result.status, summary["analysis_type"], summary["dry_run"]) == (
        "success",
        "viral_viwrap",
        True,
    )


def test_coordinator_local_dry_run_preserves_plugin_hook(monkeypatch, tmp_path):
    plugin = get_plugin("viral_viwrap")
    sentinel = tmp_path / "plugin-hook.txt"

    def execute_dry_run(plan, config):
        sentinel.write_text(plan.analysis_type, encoding="utf-8")
        return {"hook": sentinel}

    monkeypatch.setattr(plugin, "execute_dry_run", execute_dry_run)
    monkeypatch.setattr("abi.plugins.get_plugin", lambda analysis_type: plugin)
    coordinator = WorkflowCoordinator()
    prepared = coordinator.prepare(
        "viral_viwrap",
        overrides={"outdir": str(tmp_path / "result")},
        check_files=False,
    )

    result = coordinator.dry_run(prepared)

    assert result.outputs == {"hook": sentinel}
    assert sentinel.read_text(encoding="utf-8") == "viral_viwrap"


def test_coordinator_rejects_unknown_runtime_engine(tmp_path):
    prepared = WorkflowCoordinator().prepare(
        "viral_viwrap",
        overrides={"outdir": str(tmp_path / "result")},
        check_files=False,
        options=RuntimeOptions(engine="remote-magic"),
    )

    with pytest.raises(ABIError, match="Unsupported runtime engine: remote-magic"):
        WorkflowCoordinator().dry_run(prepared)
