from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from abi.runtimes import local
from abi.runtimes.local import LocalRuntime, _coerce_bool
from abi.schemas import ABIError


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        (" YES ", True),
        ("false", False),
        ("0", False),
        ("none", False),
        (1, True),
        (None, False),
    ],
)
def test_coerce_bool_handles_config_and_environment_shapes(value, expected: bool) -> None:
    assert _coerce_bool(value) is expected


class _Plugin:
    plugin_id = "test"
    report_title = "Test Report"

    def registry(self):
        return {"tool": "metadata"}

    def table_schemas(self):
        return {"summary": ["value"]}

    def parse_outputs(self, tool_id, output_dir, sample_id):
        return {}


def test_local_runtime_dry_run_forces_mock_execution(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeExecutor:
        def __init__(self, registry, logger, **kwargs):
            captured.update(registry=registry, logger=logger, kwargs=kwargs)

        def run(self, plan, config, *, dry_run):
            captured.update(plan=plan, config=config, dry_run=dry_run)
            return {"summary": tmp_path / "summary.json"}

    monkeypatch.setattr(local, "GenericABIExecutor", FakeExecutor)
    monkeypatch.setattr(local, "RunLogger", lambda path: f"logger:{path}")
    monkeypatch.setattr(local, "StandardTableManager", lambda schemas: ("tables", schemas))

    runtime = LocalRuntime(_Plugin())
    result = runtime.dry_run("plan", {"log_dir": str(tmp_path / "logs")})

    assert result.status == "success"
    assert result.outputs == {"summary": tmp_path / "summary.json"}
    assert captured["kwargs"]["mock_tools"] is True
    assert captured["dry_run"] is True


def test_local_runtime_blocks_real_execution_when_preflight_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        local,
        "run_plugin_preflight",
        lambda *args, **kwargs: {"status": "fail", "recommendations": ["configure db"]},
    )
    monkeypatch.setattr(
        local,
        "GenericABIExecutor",
        lambda *args, **kwargs: pytest.fail("executor must not be created"),
    )

    with pytest.raises(ABIError, match="configure db"):
        LocalRuntime(_Plugin()).run("plan", {"mock_tools": False})


def test_local_runtime_skips_preflight_for_explicit_mock_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        local,
        "run_plugin_preflight",
        lambda *args, **kwargs: pytest.fail("preflight must not run in mock mode"),
    )
    monkeypatch.setattr(local, "RunLogger", lambda path: path)
    monkeypatch.setattr(local, "StandardTableManager", lambda schemas: schemas)
    monkeypatch.setattr(
        local,
        "plugin_internal_handlers",
        lambda plugin: {"handler": SimpleNamespace(handler_id="handler")},
    )

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            assert kwargs["mock_tools"] is True
            assert "handler" in kwargs["internal_handlers"]

        def run(self, plan, config, *, dry_run):
            assert dry_run is False
            return {"summary": tmp_path / "summary.json"}

    monkeypatch.setattr(local, "GenericABIExecutor", FakeExecutor)

    result = LocalRuntime(_Plugin()).run("plan", {"mock_tools": "true"})
    assert result.return_code == 0


def test_local_runtime_check_is_noop() -> None:
    LocalRuntime(_Plugin()).check()
