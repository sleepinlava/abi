from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

from abi.internal import FunctionInternalHandler, InternalHandlerResult
from abi.schemas import PlanStep
from abi.step_runner import (
    StepExecutionResult,
    execute_step,
    execute_step_payload,
    plan_step_from_dict,
    write_step_payload,
)


def _step(**overrides) -> PlanStep:
    values = {
        "step_id": "step_001",
        "step_name": "Test step",
        "tool_id": "tool",
        "category": "test",
        "sample_id": "S1",
    }
    values.update(overrides)
    return PlanStep(**values)


class _Registry:
    def __init__(self, skill, *, output_dir_policy: str = "create") -> None:
        self.skill = skill
        self.output_dir_policy = output_dir_policy

    def create(self, tool_id: str):
        assert tool_id == "tool"
        return self.skill

    def get(self, tool_id: str):
        assert tool_id == "tool"
        return {"output_dir_policy": self.output_dir_policy}


class _Skill:
    def __init__(self, return_code: int = 0) -> None:
        self.return_code = return_code
        self.params = None

    def build_command(self, params):
        return ["tool", "--output", str(params["result"])]

    def run(self, params, *, dry_run: bool):
        assert dry_run is False
        self.params = params
        return SimpleNamespace(return_code=self.return_code)


class _ExternalPlugin:
    def __init__(self, skill: _Skill, *, output_dir_policy: str = "create") -> None:
        self._registry = _Registry(skill, output_dir_policy=output_dir_policy)

    def registry(self):
        return self._registry

    def parse_outputs(self, tool_id: str, output_dir: str, sample_id: str):
        assert (tool_id, sample_id) == ("tool", "S1")
        return {"summary": ({"output_dir": str(output_dir)},)}


def test_plan_step_from_dict_filters_transport_only_fields() -> None:
    step = plan_step_from_dict(
        {
            **_step().to_dict(),
            "transport_retry_count": 3,
        }
    )

    assert step == _step()
    assert not hasattr(step, "transport_retry_count")


def test_execute_external_step_creates_paths_parses_tables_and_checksums(tmp_path: Path) -> None:
    output_dir = tmp_path / "nested" / "output"
    result_file = output_dir / "result.tsv"
    output_dir.mkdir(parents=True)
    result_file.write_text("value\n1\n", encoding="utf-8")
    skill = _Skill()
    step = _step(
        inputs={"input": "reads.fastq"},
        outputs={"output_dir": str(output_dir), "result": str(result_file)},
        params={"threads": 2},
    )

    result = execute_step(
        _ExternalPlugin(skill),
        step,
        {"outdir": str(tmp_path)},
        provenance_dir=tmp_path / "provenance",
    )

    assert result.status == "success"
    assert result.command.startswith("tool --output")
    assert result.standard_tables["summary"][0]["output_dir"] == str(output_dir)
    assert result.checksums[str(result_file)]
    assert skill.params["input"] == "reads.fastq"
    assert skill.params["threads"] == 2
    assert Path(skill.params["stdout_path"]).parent.name == "step_logs"


def test_execute_external_step_honours_must_not_exist_and_reports_tool_failure(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "parent" / "must-be-created-by-tool"
    result_file = output_dir / "result.tsv"
    skill = _Skill(return_code=23)
    step = _step(outputs={"output_dir": str(output_dir), "result": str(result_file)})

    result = execute_step(
        _ExternalPlugin(skill, output_dir_policy="must_not_exist"),
        step,
        {"outdir": str(tmp_path)},
        provenance_dir=tmp_path / "provenance",
    )

    assert result.status == "failed"
    assert result.return_code == 23
    assert "Tool exited with 23" in result.reason
    assert output_dir.parent.is_dir()
    assert not output_dir.exists()


def test_execute_external_step_rejects_output_outside_configured_outdir(tmp_path: Path) -> None:
    outdir = tmp_path / "pipeline"
    escaped = tmp_path / "escaped" / "result.tsv"
    skill = _Skill()
    step = _step(outputs={"result": str(escaped)})

    result = execute_step(
        _ExternalPlugin(skill),
        step,
        {"outdir": str(outdir)},
        provenance_dir=outdir / "provenance",
    )

    assert result.status == "failed"
    assert "InputPolicyError" in result.reason
    assert "escapes output root" in result.reason
    assert skill.params is None
    assert not escaped.parent.exists()


def test_execute_external_step_rejects_symlink_escape(tmp_path: Path) -> None:
    outdir = tmp_path / "pipeline"
    outside = tmp_path / "outside"
    outdir.mkdir()
    outside.mkdir()
    (outdir / "escape").symlink_to(outside, target_is_directory=True)
    escaped = outdir / "escape" / "created" / "result.tsv"
    skill = _Skill()

    result = execute_step(
        _ExternalPlugin(skill),
        _step(outputs={"result": str(escaped)}),
        {"outdir": str(outdir)},
        provenance_dir=outdir / "provenance",
    )

    assert result.status == "failed"
    assert "InputPolicyError" in result.reason
    assert skill.params is None
    assert not (outside / "created").exists()


def test_execute_external_step_normalizes_relative_outputs_under_outdir(tmp_path: Path) -> None:
    outdir = tmp_path / "pipeline"
    skill = _Skill(return_code=23)

    result = execute_step(
        _ExternalPlugin(skill),
        _step(outputs={"result": "relative/result.tsv"}),
        {"outdir": str(outdir)},
        provenance_dir=outdir / "provenance",
    )

    assert result.status == "failed"
    assert skill.params["result"] == str(outdir / "relative" / "result.tsv")


def test_execute_internal_step_normalizes_tables_and_artifacts(tmp_path: Path) -> None:
    captured = {}

    def run(step, config, context):
        captured.update(step=step, config=config, context=context)
        return InternalHandlerResult(
            message="normalized",
            tables={"summary": ({"sample_id": "S1"},)},
            artifacts={"report": tmp_path / "report.html"},
        )

    handler = FunctionInternalHandler("normalize", run)
    plugin = SimpleNamespace(internal_handlers=lambda: {"normalize": handler})
    step = _step(
        tool_id="internal",
        params={"_internal_handler": {"handler_id": "normalize"}},
    )

    result = execute_step(
        plugin,
        step,
        {"outdir": str(tmp_path)},
        provenance_dir=tmp_path / "provenance",
    )

    assert result.status == "success"
    assert result.reason == "normalized"
    assert result.standard_tables == {"summary": [{"sample_id": "S1"}]}
    assert result.artifacts == {"report": str(tmp_path / "report.html")}
    assert captured["context"].tables_dir == tmp_path / "tables"


def test_execute_internal_step_rejects_output_outside_configured_outdir(tmp_path: Path) -> None:
    handler_called = False

    def run(*args):
        nonlocal handler_called
        handler_called = True
        return InternalHandlerResult()

    handler = FunctionInternalHandler("normalize", run)
    plugin = SimpleNamespace(internal_handlers=lambda: {"normalize": handler})
    step = _step(
        tool_id="internal",
        outputs={"report": str(tmp_path / "escaped" / "report.html")},
        params={"_internal_handler": {"handler_id": "normalize"}},
    )

    result = execute_step(
        plugin,
        step,
        {"outdir": str(tmp_path / "pipeline")},
        provenance_dir=tmp_path / "pipeline" / "provenance",
    )

    assert result.status == "failed"
    assert "InputPolicyError" in result.reason
    assert handler_called is False


def test_execute_internal_step_handles_declared_and_missing_handler_failures(
    tmp_path: Path,
) -> None:
    failed_handler = FunctionInternalHandler(
        "normalize",
        lambda *args: InternalHandlerResult(status="failed", message="invalid output"),
    )
    step = _step(
        tool_id="internal",
        params={"_internal_handler": {"handler_id": "normalize"}},
    )

    declared = execute_step(
        SimpleNamespace(internal_handlers=lambda: {"normalize": failed_handler}),
        step,
        {"outdir": str(tmp_path)},
        provenance_dir=tmp_path / "p1",
    )
    missing = execute_step(
        SimpleNamespace(internal_handlers=lambda: {}),
        step,
        {"outdir": str(tmp_path)},
        provenance_dir=tmp_path / "p2",
    )

    assert (declared.status, declared.reason) == ("failed", "invalid output")
    assert "not registered" in missing.reason


def test_execute_step_converts_contract_violation_to_failed_result(tmp_path: Path) -> None:
    missing = tmp_path / "missing.tsv"
    step = _step(
        outputs={"result": str(missing)},
        params={
            "_contract": {
                "outputs": {"result": {"contract": {"min_size": "1 B"}}},
            }
        },
    )

    result = execute_step(
        _ExternalPlugin(_Skill()),
        step,
        {"outdir": str(tmp_path)},
        provenance_dir=tmp_path / "provenance",
    )

    assert result.status == "failed"
    assert "ContractViolationError" in result.reason
    assert "file_exists" in result.reason


def test_payload_round_trip_uses_private_permissions_and_atomic_result(
    tmp_path: Path, monkeypatch
) -> None:
    payload_path = tmp_path / "jobs" / "step.json"
    result_path = tmp_path / "results" / "step.json"
    step = _step()
    written = write_step_payload(
        payload_path,
        plugin_id="test-plugin",
        step=step,
        config={"outdir": tmp_path},
        provenance_dir=tmp_path / "provenance",
        result_path=result_path,
    )
    payload = json.loads(written.read_text(encoding="utf-8"))

    assert stat.S_IMODE(written.stat().st_mode) == 0o600
    assert payload["plugin_id"] == "test-plugin"
    assert payload["config"]["outdir"] == str(tmp_path)

    plugin = object()
    expected = StepExecutionResult("step_001", "tool", "success", checksums={"x": "abc"})
    monkeypatch.setattr("abi.step_runner.get_plugin", lambda plugin_id: plugin)
    monkeypatch.setattr(
        "abi.step_runner.execute_step",
        lambda actual_plugin, actual_step, config, provenance_dir: expected,
    )

    actual = execute_step_payload(payload_path)

    assert actual is expected
    assert json.loads(result_path.read_text(encoding="utf-8")) == expected.to_dict()
    assert not result_path.with_suffix(".json.tmp").exists()
