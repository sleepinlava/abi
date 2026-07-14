"""Unit tests for error classification and DiagnosticHint (C5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))


from abi.contracts.step_contract import ContractViolation, ContractViolationError
from abi.diagnostics import (
    ERROR_CODES,
    DiagnosticHint,
    classify_exception,
)
from abi.workflow import WorkflowCatalogError, WorkflowPresetError


class TestDiagnosticHint:
    def test_creation(self):
        hint = DiagnosticHint(
            severity="error",
            code="missing_input",
            message="Input file not found: /data/R1.fq",
            suggested_next_action="Check file paths in sample sheet.",
            artifact="/data/R1.fq",
        )
        assert hint.severity == "error"
        assert hint.code == "missing_input"
        assert hint.artifact == "/data/R1.fq"
        assert hint.field is None

    def test_to_dict_omits_none(self):
        hint = DiagnosticHint(
            severity="error",
            code="missing_input",
            message="Missing input",
            suggested_next_action="Check paths",
        )
        d = hint.to_dict()
        assert "severity" in d
        assert "artifact" not in d  # None fields omitted
        assert "field" not in d

    def test_to_dict_includes_artifact_when_set(self):
        hint = DiagnosticHint(
            severity="error",
            code="missing_input",
            message="msg",
            suggested_next_action="fix",
            artifact="/tmp/file",
        )
        d = hint.to_dict()
        assert d["artifact"] == "/tmp/file"


class TestErrorCodes:
    def test_all_defined_codes(self):
        assert len(ERROR_CODES) >= 14
        assert "missing_input" in ERROR_CODES
        assert "tool_not_found" in ERROR_CODES
        assert "internal_error" in ERROR_CODES
        assert "invalid_config" in ERROR_CODES
        assert "permission_required" in ERROR_CODES
        assert "contract_violation" in ERROR_CODES


class TestClassifyException:
    def _classify(self, exc: Exception, command: str = "run"):
        code, hints = classify_exception(exc, command=command)
        return code, hints

    def test_missing_input_classified(self):
        exc = ValueError("Input file does not exist: /data/R1.fq")
        code, hints = self._classify(exc)
        assert code == "missing_input"
        assert len(hints) >= 1
        assert hints[0]["code"] == "missing_input"

    def test_missing_resource_classified(self):
        exc = ValueError("Resource NOT_CONFIGURED: genome_index")
        code, hints = self._classify(exc)
        # NOT_CONFIGURED resources map to invalid_config
        assert code in ("missing_resource", "missing_input", "invalid_config")

    def test_invalid_config_classified(self):
        exc = ValueError("Missing wgs_bacteria config keys: outdir")
        code, hints = self._classify(exc)
        assert code in ("invalid_config", "missing_input")

    def test_workflow_catalog_errors_are_invalid_config(self):
        for exc in (
            WorkflowCatalogError("catalog requires a workflows list"),
            WorkflowPresetError("Unknown workflow preset 'missing'"),
        ):
            code, hints = self._classify(exc, command="plan")
            assert code == "invalid_config"
            assert hints[0]["code"] == "invalid_config"

    def test_tool_not_found_classified(self):
        exc = RuntimeError("executable 'fastp' was not found in /path/bin or PATH")
        code, hints = self._classify(exc)
        assert code == "tool_not_found"

    def test_generic_error_falls_back_to_internal(self):
        exc = RuntimeError("Something completely unexpected happened!")
        code, hints = self._classify(exc)
        assert code == "internal_error"
        assert len(hints) >= 1

    def test_exception_with_traceback(self):
        try:
            raise ValueError("Input file does not exist: /data/R1.fq")
        except ValueError as e:
            code, hints = classify_exception(e, command="dry_run")
        assert code == "missing_input"

    def test_permission_required_classified(self):
        exc = RuntimeError("Execution requires explicit confirmation")
        code, hints = self._classify(exc)
        assert code in ("permission_required", "internal_error")

    def test_contract_violation_classified(self):
        exc = ContractViolationError(
            "step_1",
            [ContractViolation(check="file_exists", detail="missing output", path="out.bam")],
        )
        code, hints = self._classify(exc)
        assert code == "contract_violation"
        assert hints[0]["code"] == "contract_violation"

    def test_extracts_common_bioinformatics_path_extensions(self):
        exc = FileNotFoundError("Input does not exist: reads.fastq")
        _, hints = self._classify(exc)
        assert hints[0]["artifact"] == "reads.fastq"

    def test_sample_sheet_validation_errors_have_precise_codes(self):
        cases = {
            "Row 2: missing sample_id": "missing_sample_id",
            "Row 3: duplicate sample_id 'S1'": "duplicate_sample_id",
            "Row 2: incomplete FASTQ pair": "incomplete_pairs",
            "Row 2: invalid platform 'bad'": "invalid_platform",
        }
        for message, expected in cases.items():
            code, _ = self._classify(ValueError(message), command="plan")
            assert code == expected
