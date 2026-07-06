"""Unit tests for abi.provenance — edge cases and additional coverage."""

from __future__ import annotations

import json
from pathlib import Path

from abi.provenance import (
    PipelineProgressRecorder,
    _minimal_sample_status,
    capture_tool_version,
)


# ── capture_tool_version edge cases ────────────────────────────────────────


def test_capture_version_check_installation_raises_ext() -> None:
    """L71-72: skill.check_installation() raises → ('', 'not_captured')."""
    class BadSkill:
        def check_installation(self):
            raise RuntimeError("boom")

    version, status = capture_tool_version(BadSkill())
    assert version == ""
    assert status == "not_captured"


def test_capture_version_check_installation_returns_false_ext() -> None:
    """L75-76: check_installation() returns False → ('', 'not_found')."""
    class MissingSkill:
        def check_installation(self):
            return False

    version, status = capture_tool_version(MissingSkill())
    assert version == ""
    assert status == "not_found"


def test_capture_version_timeout_ext() -> None:
    """L83-84: version == 'version_command_timeout' → ('version_command_timeout', 'timeout')."""
    class TimeoutSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            return "version_command_timeout"

    version, status = capture_tool_version(TimeoutSkill())
    assert version == "version_command_timeout"
    assert status == "timeout"


def test_capture_version_failed_prefix_ext() -> None:
    """L85-86: version starts with 'version_command_' → ('version_command_X', 'failed')."""
    class FailedSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            return "version_command_error"

    version, status = capture_tool_version(FailedSkill())
    assert status == "failed"


def test_capture_version_regex_unmatched_ext() -> None:
    """L85: version starts with 'regex_unmatched:' → ('regex_unmatched:X', 'failed')."""
    class RegexSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            return "regex_unmatched: pattern xyz"

    version, status = capture_tool_version(RegexSkill())
    assert status == "failed"


def test_capture_version_capture_failed_prefix_ext() -> None:
    """L85: version starts with 'capture_failed' → ('capture_failedX', 'failed')."""
    class CaptureFailSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            return "capture_failed_badly"

    version, status = capture_tool_version(CaptureFailSkill())
    assert status == "failed"


def test_capture_version_empty_version_ext() -> None:
    """L81-82: capture_version() returns empty string → ('', 'not_configured')."""
    class EmptyVersionSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            return ""

    version, status = capture_tool_version(EmptyVersionSkill())
    assert version == ""
    assert status == "not_configured"


def test_capture_version_capture_raises_ext() -> None:
    """L79-80: capture_version() raises → ('', 'failed')."""
    class CrashSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            raise OSError("crash")

    version, status = capture_tool_version(CrashSkill())
    assert version == ""
    assert status == "failed"


def test_capture_version_success_ext() -> None:
    """L87: success path → (version, 'captured')."""
    class GoodSkill:
        def check_installation(self):
            return True

        def capture_version(self):
            return "1.2.3"

    version, status = capture_tool_version(GoodSkill())
    assert version == "1.2.3"
    assert status == "captured"


# ── PipelineProgressRecorder._apply_event edge cases ───────────────────────


def test_apply_event_unknown_step_id_ext(tmp_path: Path) -> None:
    """_apply_event with step_id not in snapshot → returns early (no crash)."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    recorder = PipelineProgressRecorder(prov)
    recorder._snapshot = {
        "steps": [
            {"step_id": "real_step", "status": "pending"}
        ],
        "samples": {},
        "current_steps": [],
    }
    # Call with unknown step_id — should return without error
    recorder._apply_event("step_started", {"step_id": "nonexistent"}, "2024-01-01T00:00:00")
    # The real step should still be pending
    assert recorder._snapshot["steps"][0]["status"] == "pending"


def test_apply_event_unknown_event_type_ext(tmp_path: Path) -> None:
    """_apply_event with unknown event type → no-op."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    recorder = PipelineProgressRecorder(prov)
    recorder._snapshot = {
        "steps": [
            {"step_id": "step1", "status": "pending"}
        ],
        "samples": {},
        "current_steps": [],
    }
    # Unknown event → should be a no-op
    recorder._apply_event("weird_event", {"step_id": "step1"}, "2024-01-01T00:00:00")
    assert recorder._snapshot["steps"][0]["status"] == "pending"


# ── _minimal_sample_status edge cases ──────────────────────────────────────


def test_minimal_sample_status_empty_sample_id_ext() -> None:
    """L818: empty sample_id → continue (not added to status dict)."""
    class EmptySample:
        sample_id = ""
        platform = "illumina"

    class FakePlan:
        samples = [EmptySample()]
        steps = []

    rows_by_step = {}
    result = _minimal_sample_status(FakePlan(), rows_by_step)
    # Empty sample_id should be skipped
    assert result == {}


def test_minimal_sample_status_no_samples_ext() -> None:
    """Empty samples list → empty result."""
    class FakePlan:
        samples = []
        steps = []

    rows_by_step = {}
    result = _minimal_sample_status(FakePlan(), rows_by_step)
    assert result == {}


def test_minimal_sample_status_failed_sample_ext() -> None:
    """Sample with failed step → status 'failed'."""
    class Sample:
        def __init__(self, sid, plat="illumina"):
            self.sample_id = sid
            self.platform = plat

    class FakePlan:
        def __init__(self):
            self.samples = [Sample("S1"), Sample("S2")]
            self.steps = []

    rows_by_step = {
        "step1": {"step_id": "step1", "sample_id": "S1", "status": "failed"},
        "step2": {"step_id": "step2", "sample_id": "S2", "status": "success"},
    }
    result = _minimal_sample_status(FakePlan(), rows_by_step)
    assert result["S1"]["status"] == "failed"
    assert result["S1"]["failed_step_count"] == 1
    assert result["S2"]["status"] == "completed"
    assert result["S2"]["failed_step_count"] == 0


def test_minimal_sample_status_pending_ext() -> None:
    """Sample with no command rows → status 'pending'."""
    class Sample:
        def __init__(self, sid, plat="illumina"):
            self.sample_id = sid
            self.platform = plat

    class FakePlan:
        def __init__(self):
            self.samples = [Sample("S3")]
            self.steps = []

    rows_by_step = {}
    result = _minimal_sample_status(FakePlan(), rows_by_step)
    assert result["S3"]["status"] == "pending"
    assert result["S3"]["completed_step_count"] == 0
