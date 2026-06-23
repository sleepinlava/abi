from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from abi.contracts.step_contract import ContractViolationError
from abi.executor import (
    GenericABIExecutor,
    _bridge_consensus_for_single_detector,
    _build_assertion_context,
    _execution_options,
    _filename_has_read_pair,
    _output_candidate_score,
    _propagate_resolved_paths,
    _read_pair_for_key,
    _resolve_actual_outputs,
    _symlink_resolved_outputs,
    _tool_failure_reason,
)
from abi.internal import FunctionInternalHandler, InternalHandlerResult
from abi.provenance import RunLogger
from abi.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput, ToolError
from abi.tables import StandardTableManager
from abi.tools import ToolRegistry


class _Logger:
    def __init__(self, path: Path) -> None:
        self.log_file = path
        self.rows = []

    def log_step(self, step, **kwargs) -> None:
        self.rows.append((step.step_id, kwargs))


class _Tables:
    def __init__(self) -> None:
        self.rows = []

    def append_rows(self, path, rows):
        self.rows.append(rows)
        return list(rows)


class _Registry:
    def __init__(self, skill=None, *, registered: bool = True) -> None:
        self.skill = skill
        self.registered = registered

    def has(self, tool_id: str) -> bool:
        return self.registered and tool_id == "tool"

    def create(self, tool_id: str, *, mock_tools: bool = False):
        return self.skill


class _Skill:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or SimpleNamespace(return_code=0, status="success", outputs={})
        self.error = error
        self.params = None

    def build_command(self, params):
        return ["tool", "--output", str(params.get("output_dir", ""))]

    def run(self, params, *, dry_run: bool):
        self.params = params
        if self.error:
            raise self.error
        return self.result


def _step(**overrides) -> PlanStep:
    values = {
        "step_id": "step",
        "step_name": "Step",
        "tool_id": "tool",
        "category": "test",
        "sample_id": "S1",
    }
    values.update(overrides)
    return PlanStep(**values)


def _executor(
    tmp_path: Path,
    *,
    skill=None,
    registered: bool = True,
    handlers=None,
    enforce_contracts: bool = True,
) -> GenericABIExecutor:
    executor = GenericABIExecutor(
        _Registry(skill, registered=registered),
        _Logger(tmp_path / "run.log"),
        table_manager=_Tables(),
        parse_outputs=lambda tool_id, output_dir, sample_id: {
            "summary": [{"sample_id": sample_id}]
        },
        internal_handlers=handlers,
        enforce_contracts=enforce_contracts,
    )
    executor._config = {"outdir": str(tmp_path)}
    return executor


def test_generic_executor_parallel_dry_run_preserves_plan_order(tmp_path: Path) -> None:
    samples = [
        SampleInput(sample_id="S1", platform="assembly", assembly="S1.fa"),
        SampleInput(sample_id="S2", platform="assembly", assembly="S2.fa"),
    ]
    context = SampleContext(samples, True, False, True, False)
    steps = [
        _step(step_id="S1_step", sample_id="S1"),
        _step(step_id="S2_step", sample_id="S2"),
        _step(step_id="project_step", sample_id=None),
    ]
    plan = ExecutionPlan(
        project_name="parallel",
        mode="auto",
        threads=1,
        outdir=str(tmp_path / "out"),
        log_dir=str(tmp_path / "logs"),
        samples=samples,
        sample_context=context,
        selected_tools=[],
        steps=steps,
    )
    executor = GenericABIExecutor(
        ToolRegistry([]),
        RunLogger(tmp_path / "logs"),
        table_manager=StandardTableManager({"summary": ["sample_id"]}),
        parse_outputs=lambda *args: {},
    )

    outputs = executor.run(
        plan,
        {
            "outdir": str(tmp_path / "out"),
            "execution": {
                "parallel": True,
                "workers": 2,
                "progress": False,
                "error_policy": "continue",
            },
        },
        dry_run=True,
    )

    command_lines = outputs["commands"].read_text(encoding="utf-8").splitlines()
    assert [line.split("\t", 1)[0] for line in command_lines[1:]] == [
        "S1_step",
        "S2_step",
        "project_step",
    ]


def test_execute_step_handles_skipped_dry_run_missing_and_external_failures(
    tmp_path: Path,
) -> None:
    executor = _executor(tmp_path, registered=False)
    skipped, error = executor._execute_step(
        _step(skipped=True, reason="not applicable"),
        dry_run=False,
        provenance=tmp_path,
        tables_dir=tmp_path / "tables",
        progress_recorder=None,
    )
    dry, dry_error = executor._execute_step(
        _step(),
        dry_run=True,
        provenance=tmp_path,
        tables_dir=tmp_path / "tables",
        progress_recorder=None,
    )
    missing, missing_error = executor._execute_step(
        _step(),
        dry_run=False,
        provenance=tmp_path,
        tables_dir=tmp_path / "tables",
        progress_recorder=None,
    )

    assert (skipped["status"], error) == ("skipped", None)
    assert (dry["status"], dry_error) == ("dry_run", None)
    assert missing["status"] == "failed"
    assert isinstance(missing_error, ToolError)

    nonzero = SimpleNamespace(
        return_code=7,
        status="failed",
        outputs={"stderr_path": "tool.err", "stdout_path": "tool.out"},
    )
    failed_executor = _executor(tmp_path, skill=_Skill(nonzero))
    row, failed_error = failed_executor._execute_step(
        _step(outputs={"output_dir": str(tmp_path / "output")}),
        dry_run=False,
        provenance=tmp_path,
        tables_dir=tmp_path / "tables",
        progress_recorder=None,
    )
    assert row["return_code"] == 7
    assert "stderr_path=tool.err" in row["reason"]
    assert isinstance(failed_error, ToolError)


def test_external_step_records_tool_exception_and_successful_parsing(tmp_path: Path) -> None:
    raised = _executor(tmp_path, skill=_Skill(error=ToolError("binary missing")))
    failed = raised._run_external_step(
        _step(outputs={"output_dir": str(tmp_path / "failed")}),
        tmp_path,
        tmp_path / "tables",
    )
    assert failed["status"] == "failed"
    assert "binary missing" in failed["reason"]
    assert (tmp_path / "step_logs" / "step.stderr.log").is_file()

    successful = _executor(tmp_path, skill=_Skill(), enforce_contracts=False)
    result = successful._run_external_step(
        _step(outputs={"output_dir": str(tmp_path / "success")}),
        tmp_path,
        tmp_path / "tables",
    )
    assert result["status"] == "success"
    assert result["parsed_status"] == "parsed"
    assert result["standard_tables"] == "summary"


def test_internal_handler_success_failure_missing_and_contract_violation(tmp_path: Path) -> None:
    success_handler = FunctionInternalHandler(
        "normalize",
        lambda *args: InternalHandlerResult(
            message="normalized", tables={"summary": [{"value": 1}]}
        ),
    )
    failed_handler = FunctionInternalHandler(
        "failed",
        lambda *args: InternalHandlerResult(status="failed", message="bad rows"),
    )
    executor = _executor(
        tmp_path,
        handlers={"normalize": success_handler, "failed": failed_handler},
    )
    assert (
        executor._run_internal_step(_step(tool_id="internal"), tmp_path, tmp_path / "tables")[
            "parsed_status"
        ]
        == "not_applicable"
    )

    with pytest.raises(ToolError, match="not registered"):
        executor._run_internal_step(
            _step(
                tool_id="internal",
                params={"_internal_handler": {"handler_id": "missing"}},
            ),
            tmp_path,
            tmp_path / "tables",
        )

    failed = executor._run_internal_step(
        _step(
            tool_id="internal",
            params={"_internal_handler": {"handler_id": "failed"}},
        ),
        tmp_path,
        tmp_path / "tables",
    )
    assert (failed["status"], failed["return_code"]) == ("failed", 1)

    success = executor._run_internal_step(
        _step(
            tool_id="internal",
            params={"_internal_handler": {"handler_id": "normalize"}},
        ),
        tmp_path,
        tmp_path / "tables",
    )
    assert success["standard_tables"] == "summary"

    contract_step = _step(
        tool_id="internal",
        outputs={"result": str(tmp_path / "missing.tsv")},
        params={
            "_internal_handler": {"handler_id": "normalize"},
            "_contract": {"outputs": {"result": {"contract": {"min_size": "1 B"}}}},
        },
    )
    with pytest.raises(ContractViolationError):
        executor._run_internal_step(contract_step, tmp_path, tmp_path / "tables")


def test_command_building_params_progress_and_internal_exception(tmp_path: Path) -> None:
    progress = SimpleNamespace(
        started=[],
        completed=[],
        step_started=lambda step: progress.started.append(step.step_id),
        step_completed=lambda step, **kwargs: progress.completed.append(kwargs),
    )
    executor = _executor(tmp_path, registered=False)
    internal = _step(
        tool_id="internal",
        params={"_internal_handler": {"handler_id": "normalize", "execution_scope": "driver"}},
    )
    assert executor._command_for_step(internal, dry_run=False)[:3] == [
        "abi",
        "internal",
        "normalize",
    ]
    assert executor._command_for_step(_step(), dry_run=False)[:2] == ["abi", "missing-wrapper"]

    executor._run_internal_step = lambda *args: (_ for _ in ()).throw(RuntimeError("broken"))
    row, error = executor._execute_step(
        internal,
        dry_run=False,
        provenance=tmp_path,
        tables_dir=tmp_path / "tables",
        progress_recorder=progress,
    )
    assert row["status"] == "failed"
    assert isinstance(error.__cause__, RuntimeError)
    assert progress.started == ["step"]
    assert progress.completed[0]["status"] == "failed"

    executor._tool_timeout_seconds = None
    params = executor._params_for_step(
        _step(inputs={"outdir": "input"}, params={"outdir": "params"}, outputs={}),
        dry_run=True,
    )
    assert params["output_dir"] == "params"
    assert params["dry_run"] is True


def test_execution_and_output_helpers_cover_corrupt_and_unresolved_paths(tmp_path: Path) -> None:
    assert _execution_options({"execution": []})["workers"] == 1
    options = _execution_options(
        {"execution": {"progress": False, "dashboard": {"enable": True}, "workers": 0}}
    )
    assert options["record_progress"] is True
    assert options["workers"] == 1

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("not json", encoding="utf-8")
    context = _build_assertion_context(
        SimpleNamespace(outputs={}),
        {"_contract": {}, "number": 3, "corrupt": str(corrupt)},
    )
    assert context["output_json"] == {}
    assert _resolve_actual_outputs({"result": "abstract"}, {}, "S1") == {"result": "abstract"}
    missing_dir = tmp_path / "missing"
    assert (
        _resolve_actual_outputs({"output_dir": str(missing_dir), "result": "abstract"}, {}, "S1")[
            "result"
        ]
        == "abstract"
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    custom = output_dir / "S1-result.custom"
    custom.write_text("value", encoding="utf-8")
    resolved = _resolve_actual_outputs(
        {"output_dir": str(output_dir), "result": "abstract"},
        {"output_dir": {}, "ignored": "invalid", "result": {"format": "custom"}},
        "S1",
    )
    assert resolved["result"] == str(custom)


def test_symlink_bridge_propagation_and_scoring_helpers(tmp_path: Path) -> None:
    actual = tmp_path / "stage" / "actual" / "S1_result.tsv"
    actual.parent.mkdir(parents=True)
    actual.write_text("value", encoding="utf-8")
    planned = tmp_path / "stage" / "planned" / "result.tsv"
    _symlink_resolved_outputs(
        {"result": str(planned)},
        {"result": str(actual)},
        {"result": {"format": "tsv"}},
    )
    assert planned.is_symlink()

    output_dir = tmp_path / "pipeline" / "plasmid_detection" / "S1"
    output_dir.mkdir(parents=True)
    plasmid = output_dir / "plasmids.fna"
    plasmid.write_text(">p\nACGT\n", encoding="utf-8")
    step = _step(
        tool_id="genomad",
        outputs={"output_dir": str(output_dir)},
    )
    _bridge_consensus_for_single_detector(step, {"plasmid_contigs": str(plasmid)})
    consensus = tmp_path / "pipeline" / "plasmid_consensus" / "S1"
    assert (consensus / "S1.internal.plasmid_contigs").exists()

    downstream = _step(
        inputs={"table": str(tmp_path / "stage" / "old" / "expected.tsv")},
        params={"table": str(tmp_path / "stage" / "old" / "expected.tsv")},
    )
    _propagate_resolved_paths(SimpleNamespace(outputs={"result": str(actual)}), [downstream])
    assert downstream.inputs["table"] == str(actual)
    assert downstream.params["table"] == str(actual)

    assert _read_pair_for_key("clean_read1") == "1"
    assert _read_pair_for_key("clean_r2") == "2"
    assert _read_pair_for_key("summary") == ""
    assert _filename_has_read_pair("sample_R1.fastq.gz", "1")
    assert _output_candidate_score("clean_read1", "S1", Path("S1_R1.clean.fastq.gz")) > 0


def test_structured_tool_failure_reason_includes_diagnostic_paths() -> None:
    reason = _tool_failure_reason(
        _step(),
        return_code="",
        stderr_path="step.err",
        stdout_path="step.out",
        message="binary missing",
    )
    assert "exit_code=not_started" in reason
    assert "stderr_path=step.err" in reason
    assert "stdout_path=step.out" in reason
    assert "message=binary missing" in reason
