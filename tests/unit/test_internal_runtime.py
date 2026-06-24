from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from abi.internal import (
    FunctionInternalHandler,
    InternalHandlerContext,
    InternalHandlerResult,
    internal_handler_spec,
    plugin_internal_handlers,
    run_plugin_preflight,
)


def _handler(handler_id: str = "normalize", scope: str = "worker") -> FunctionInternalHandler:
    return FunctionInternalHandler(
        handler_id,
        lambda step, config, context: InternalHandlerResult(
            message=f"{step.step_id}:{config['mode']}:{context.dry_run}"
        ),
        execution_scope=scope,
    )


def test_function_internal_handler_forwards_execution_context(tmp_path: Path) -> None:
    context = InternalHandlerContext(
        outdir=tmp_path,
        provenance_dir=tmp_path / "provenance",
        tables_dir=tmp_path / "tables",
        dry_run=True,
    )

    result = _handler().run(SimpleNamespace(step_id="S1"), {"mode": "test"}, context)

    assert result.status == "success"
    assert result.message == "S1:test:True"


def test_plugin_internal_handlers_accepts_valid_mapping() -> None:
    handler = _handler()
    plugin = SimpleNamespace(internal_handlers=lambda: {"normalize": handler})

    assert plugin_internal_handlers(plugin) == {"normalize": handler}


@pytest.mark.parametrize(
    "factory,error",
    [
        (lambda: [], "must return a mapping"),
        (lambda: {"normalize": object()}, "does not satisfy"),
        (lambda: {"wrong": _handler()}, "does not match"),
        (lambda: {"normalize": _handler(scope="remote")}, "invalid execution_scope"),
    ],
)
def test_plugin_internal_handlers_rejects_invalid_contracts(factory, error: str) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        plugin_internal_handlers(SimpleNamespace(internal_handlers=factory))


def test_plugin_without_internal_handlers_has_empty_registry() -> None:
    assert plugin_internal_handlers(object()) == {}


@pytest.mark.parametrize(
    "params,expected",
    [
        ({}, ("", "worker")),
        ({"_internal_handler": "invalid"}, ("", "worker")),
        ({"_internal_handler": {"handler_id": "x"}}, ("x", "worker")),
        (
            {"_internal_handler": {"handler_id": "x", "execution_scope": "driver"}},
            ("x", "driver"),
        ),
    ],
)
def test_internal_handler_spec_is_defensive(params, expected) -> None:
    assert internal_handler_spec(SimpleNamespace(params=params)) == expected


def test_preflight_without_custom_capability_validates_inputs() -> None:
    plugin = SimpleNamespace(
        plugin_id="plain",
        build_sample_context=lambda config, check_files: (_ for _ in ()).throw(
            ValueError("Input files do not exist: missing.fastq")
        ),
        check_resources=lambda config: [],
    )

    report = run_plugin_preflight(plugin, {}, engine="local", check_runtime=False)

    assert report["status"] == "fail"
    assert report["checks"][0]["name"] == "inputs"
    assert "missing.fastq" in report["checks"][0]["message"]


def test_preflight_forwards_runtime_flag_and_validates_mapping() -> None:
    calls = []

    def preflight(config, *, engine, check_runtime):
        calls.append((config, engine, check_runtime))
        return {"status": "pass"}

    plugin = SimpleNamespace(preflight=preflight)
    assert run_plugin_preflight(plugin, {"mode": "test"}, engine="hpc", check_runtime=False) == {
        "status": "pass"
    }
    assert calls == [({"mode": "test"}, "hpc", False)]

    plugin.preflight = lambda *args, **kwargs: []
    with pytest.raises(TypeError, match="must return a mapping"):
        run_plugin_preflight(plugin, {}, engine="local")
