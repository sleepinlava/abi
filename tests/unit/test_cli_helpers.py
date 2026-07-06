"""Unit tests for pure helper functions in ``src/abi/cli.py``.

These functions have no Typer decorators and no side effects -- they are
100 % unit-testable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import typer

from abi.cli import _agent_result, _build_job_payload, _fail, _path_string, _set_if_not_none
from abi.errors import ABIError

# ---------------------------------------------------------------------------
# _agent_result  (cli.py lines 168-182)
# ---------------------------------------------------------------------------


def test_agent_result_success_with_result():
    """status="success" with a result dict → returns the result."""
    result = _agent_result('{"status":"success","result":{"key":"value"}}')
    assert result == {"key": "value"}


def test_agent_result_confirmation_required():
    """status="confirmation_required" → typer.Exit(code=2)."""
    with pytest.raises(typer.Exit) as exc:
        _agent_result('{"status":"confirmation_required","confirmation_prompt":"Are you sure?"}')
    assert exc.value.exit_code == 2


def test_agent_result_error_status():
    """status="error" → ABIError containing the error_code."""
    with pytest.raises(ABIError, match="ERR-001"):
        _agent_result('{"status":"error","error_code":"ERR-001","error":"Something went wrong"}')


def test_agent_result_success_missing_result():
    """status="success" but no result key → ABIError."""
    with pytest.raises(ABIError, match="missing"):
        _agent_result('{"status":"success"}')


def test_agent_result_not_a_dict():
    """Parsed JSON is not a dict (e.g. a JSON string literal) → ABIError."""
    with pytest.raises(ABIError, match="JSON object"):
        _agent_result('"just a string"')


def test_agent_result_invalid_json():
    """Invalid JSON text → ABIError (propagated from loads_json)."""
    with pytest.raises(ABIError):
        _agent_result("not json at all")


# ---------------------------------------------------------------------------
# _fail  (cli.py lines 120-132)
# ---------------------------------------------------------------------------


def test_fail_prints_and_exits():
    """Normal exceptions → printed in red + typer.Exit(code=1)."""
    with pytest.raises(typer.Exit) as exc:
        _fail(ValueError("bad value"))
    assert exc.value.exit_code == 1


def test_fail_reraises_memory_error():
    """MemoryError is re-raised (bare ``raise`` in an except block)."""
    with pytest.raises(MemoryError):
        try:
            raise MemoryError("out of memory")
        except Exception as exc:
            _fail(exc)


# ---------------------------------------------------------------------------
# _build_job_payload  (cli.py lines 1844-1931)
# ---------------------------------------------------------------------------

# Every keyword-only parameter is required (no defaults), so each test
# call must supply all 24 arguments.  The helper below fills in sensible
# defaults so individual tests only override what they care about.
_ALL_KWARGS: Dict[str, Any] = dict(
    command="test",
    payload_path=None,
    arguments_json=None,
    backend=None,
    analysis_type=None,
    config_path=None,
    sample_sheet=None,
    profile=None,
    mode=None,
    threads=None,
    outdir=None,
    log_dir=None,
    engine=None,
    workflow=None,
    nextflow_bin=None,
    nextflow_profile=None,
    executor=None,
    work_dir=None,
    nxf_home=None,
    mamba_root=None,
    resume=False,
    smoke=False,
    confirm_execution=False,
    check_files=None,
)


def _payload(**overrides: Any) -> Dict[str, Any]:
    """Call ``_build_job_payload`` with defaults + overrides."""
    kwargs = dict(_ALL_KWARGS)
    kwargs.update(overrides)
    return _build_job_payload(**kwargs)


def test_build_job_payload_arguments_not_dict():
    """``--arguments-json`` must be a JSON object, not an array."""
    with pytest.raises(ABIError, match="must be a JSON object"):
        _payload(arguments_json='["list"]')


def test_build_job_payload_no_flags_returns_minimal():
    """Minimal call populates command + arguments.analysis_type, no backend."""
    result = _payload(analysis_type="metatranscriptomics")
    assert result["command"] == "test"
    assert result["arguments"]["analysis_type"] == "metatranscriptomics"
    assert "backend" not in result


def test_build_job_payload_boolean_flags_only_when_true():
    """Boolean values are only placed into arguments when truthy."""
    result_true = _payload(analysis_type="test", confirm_execution=True)
    assert result_true["arguments"].get("confirm_execution") is True

    result_false = _payload(analysis_type="test", confirm_execution=False)
    assert "confirm_execution" not in result_false["arguments"]


def test_build_job_payload_check_files_explicit_false():
    """``check_files=False`` is set explicitly (treated as ``is not None``)."""
    result = _payload(analysis_type="test", check_files=False)
    assert result["arguments"].get("check_files") is False


# ---------------------------------------------------------------------------
# _set_if_not_none  (cli.py lines 1942-1952)
# ---------------------------------------------------------------------------


def test_set_if_not_none_adds_value():
    d: Dict[str, Any] = {}
    _set_if_not_none(d, "key", "value")
    assert d == {"key": "value"}


def test_set_if_not_none_skips_none():
    d: Dict[str, Any] = {}
    _set_if_not_none(d, "key", None)
    assert d == {}


# ---------------------------------------------------------------------------
# _path_string  (cli.py lines 1955-1960)
# ---------------------------------------------------------------------------


def test_path_string_returns_str():
    assert _path_string(Path("/tmp/foo")) == "/tmp/foo"


def test_path_string_none_returns_none():
    assert _path_string(None) is None
