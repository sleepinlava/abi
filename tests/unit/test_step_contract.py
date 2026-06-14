"""Unit tests for step contract enforcement — output validation, assertions,
checksum chaining, and integration with the executor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from abi.contracts.step_contract import (
    ContractViolation,
    ContractViolationError,
    StepContractResult,
    compute_file_checksum,
    compute_output_checksums,
    evaluate_assertions,
    save_checksums,
    load_checksums,
    validate_output_contract,
    verify_input_checksums,
    _parse_size,
    _count_fasta_contigs,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestParseSize:
    def test_bytes(self):
        assert _parse_size("500B") == 500
        assert _parse_size("1KB") == 1024
        assert _parse_size("1MB") == 1024**2
        assert _parse_size("1GB") == 1024**3

    def test_no_unit_means_bytes(self):
        assert _parse_size("500") == 500

    def test_invalid_returns_zero(self):
        assert _parse_size("not a size") == 0


class TestCountFasta:
    def test_counts_headers(self, tmp_path):
        fasta = tmp_path / "test.fa"
        fasta.write_text(">contig1\nATCG\n>contig2\nGGGG\n>contig3\nCCCC\n")
        assert _count_fasta_contigs(fasta) == 3

    def test_empty_file(self, tmp_path):
        fasta = tmp_path / "empty.fa"
        fasta.write_text("")
        assert _count_fasta_contigs(fasta) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Checksums
# ═══════════════════════════════════════════════════════════════════════════


class TestChecksums:
    def test_compute_checksum(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")
        digest = compute_file_checksum(f)
        assert len(digest) == 64
        # Same content = same hash
        f2 = tmp_path / "data2.txt"
        f2.write_text("hello world")
        assert compute_file_checksum(f2) == digest

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("hello")
        f2 = tmp_path / "b.txt"
        f2.write_text("world")
        assert compute_file_checksum(f1) != compute_file_checksum(f2)

    def test_missing_file_returns_empty(self):
        assert compute_file_checksum("/nonexistent/path") == ""

    def test_compute_output_checksums(self, tmp_path):
        a = tmp_path / "a.txt"
        a.write_text("aaa")
        b = tmp_path / "b.txt"
        b.write_text("bbb")
        outputs = {"data_a": str(a), "data_b": str(b), "dir": str(tmp_path)}
        result = compute_output_checksums(outputs)
        assert str(a) in result
        assert str(b) in result
        assert str(tmp_path) not in result  # directories skipped

    def test_save_and_load_checksums(self, tmp_path):
        prov = tmp_path / "provenance"
        prov.mkdir()
        save_checksums(prov, {"/a": "abc123", "/b": "def456"})
        loaded = load_checksums(prov)
        assert loaded["/a"] == "abc123"
        assert loaded["/b"] == "def456"

    def test_merge_preserves_existing(self, tmp_path):
        prov = tmp_path / "provenance"
        prov.mkdir()
        save_checksums(prov, {"/a": "aaa"})
        save_checksums(prov, {"/b": "bbb"})
        loaded = load_checksums(prov)
        assert loaded["/a"] == "aaa"
        assert loaded["/b"] == "bbb"


# ═══════════════════════════════════════════════════════════════════════════
# Output contract validation
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateOutputContract:
    def test_empty_contract_passes(self):
        result = validate_output_contract("step1", {}, None)
        assert result.passed

    def test_file_exists_passes(self, tmp_path):
        f = tmp_path / "out.txt"
        f.write_text("data")
        spec = {"out_file": {"contract": {"min_size": "1B"}}}
        result = validate_output_contract("s1", {"out_file": str(f)}, spec)
        assert result.passed

    def test_file_missing_fails(self, tmp_path):
        spec = {"out_file": {"contract": {"min_size": "1B"}}}
        result = validate_output_contract(
            "s1", {"out_file": str(tmp_path / "nope.txt")}, spec
        )
        assert not result.passed
        assert any(v.check == "file_exists" for v in result.violations)

    def test_min_size_violation(self, tmp_path):
        f = tmp_path / "tiny.txt"
        f.write_text("x")  # 1 byte
        spec = {"out_file": {"contract": {"min_size": "1KB"}}}
        result = validate_output_contract("s1", {"out_file": str(f)}, spec)
        assert not result.passed
        assert any(v.check == "min_size" for v in result.violations)

    def test_extension_check(self, tmp_path):
        f = tmp_path / "out.xml"
        f.write_text("<xml/>")
        spec = {"out_file": {"contract": {"extensions": [".json", ".tsv"]}}}
        result = validate_output_contract("s1", {"out_file": str(f)}, spec)
        assert not result.passed
        assert any(v.check == "extension" for v in result.violations)

    def test_contains_check(self, tmp_path):
        d = tmp_path / "mydir"
        d.mkdir()
        (d / "data.txt").write_text("ok")
        spec = {"out_dir": {"contract": {"contains": ["data.txt", "missing.csv"]}}}
        result = validate_output_contract("s1", {"out_dir": str(d)}, spec)
        assert not result.passed
        violations = [v for v in result.violations if v.check == "contains"]
        assert len(violations) == 1
        assert "missing.csv" in violations[0].detail

    def test_min_contigs(self, tmp_path):
        f = tmp_path / "assembly.fa"
        f.write_text(">contig1\nATCG\n")
        spec = {"assembly": {"contract": {"min_contigs": 2}}}
        result = validate_output_contract("s1", {"assembly": str(f)}, spec)
        assert not result.passed
        assert any(v.check == "min_contigs" for v in result.violations)

    def test_json_schema_check(self, tmp_path):
        f = tmp_path / "report.json"
        f.write_text(json.dumps({"summary": {"before_filtering": {"total_reads": 0}}}))
        spec = {
            "json_report": {
                "contract": {
                    "schema": {
                        "summary.before_filtering.total_reads": {
                            "type": "integer",
                            "min": 1,
                        }
                    }
                }
            }
        }
        result = validate_output_contract("s1", {"json_report": str(f)}, spec)
        assert not result.passed
        violations = [v for v in result.violations if v.check == "json_schema"]
        assert len(violations) >= 1

    def test_computes_checksums_for_valid_outputs(self, tmp_path):
        f = tmp_path / "out.txt"
        f.write_text("some data here")
        spec = {"out_file": {"contract": {"min_size": "1B"}}}
        result = validate_output_contract("s1", {"out_file": str(f)}, spec)
        assert result.passed
        assert len(result.checksums) == 1
        assert str(f) in result.checksums


# ═══════════════════════════════════════════════════════════════════════════
# Assertions
# ═══════════════════════════════════════════════════════════════════════════


class TestEvaluateAssertions:
    def test_empty_assertions(self):
        violations = evaluate_assertions([], {})
        assert violations == []

    def test_passing_assertion(self):
        ctx = {
            "output_json": {"summary": {"after_filtering": {"total_reads": 100}}},
            "output_files": {},
            "return_code": 0,
        }
        violations = evaluate_assertions(
            ["output_json.summary.after_filtering.total_reads > 0"], ctx
        )
        assert violations == []

    def test_failing_assertion(self):
        ctx = {
            "output_json": {"summary": {"after_filtering": {"total_reads": 0}}},
            "output_files": {},
            "return_code": 0,
        }
        violations = evaluate_assertions(
            ["output_json.summary.after_filtering.total_reads > 0"], ctx
        )
        assert len(violations) == 1
        assert violations[0].check == "assertion"

    def test_file_exists_assertion(self, tmp_path):
        f = tmp_path / "real.txt"
        f.write_text("ok")
        ctx = {"output_files": {"real": True, "fake": False}, "return_code": 0}
        v1 = evaluate_assertions(["output_files.real exists"], ctx)
        assert v1 == []
        v2 = evaluate_assertions(["output_files.fake exists"], ctx)
        assert len(v2) == 1

    def test_invalid_expression(self):
        violations = evaluate_assertions(["this.is.not.valid >>>"], {})
        assert len(violations) == 1

    def test_comparison_assertion(self):
        ctx = {"output_json": {}, "output_files": {}, "return_code": 0}
        violations = evaluate_assertions(
            ["output_json.summary.after_filtering.total_reads <= output_json.summary.before_filtering.total_reads"],
            {
                "output_json": {
                    "summary": {
                        "before_filtering": {"total_reads": 1000},
                        "after_filtering": {"total_reads": 800},
                    }
                },
                "output_files": {},
                "return_code": 0,
            },
        )
        assert violations == []


# ═══════════════════════════════════════════════════════════════════════════
# Input checksum verification
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifyInputChecksums:
    def test_empty_map_noop(self):
        violations = verify_input_checksums("s1", {"read1": "/x.fq"}, {})
        assert violations == []

    def test_matching_checksum_passes(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("trusted content")
        digest = compute_file_checksum(f)
        checksums = {str(f): digest}
        violations = verify_input_checksums("s1", {"read1": str(f)}, checksums)
        assert violations == []

    def test_mismatched_checksum_fails(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("modified!")
        checksums = {str(f): "a" * 64}
        violations = verify_input_checksums("s1", {"read1": str(f)}, checksums)
        assert len(violations) >= 1
        assert any(v.check == "checksum_mismatch" for v in violations)

    def test_missing_file_reported(self, tmp_path):
        checksums = {str(tmp_path / "gone.txt"): "b" * 64}
        violations = verify_input_checksums(
            "s1", {"read1": str(tmp_path / "gone.txt")}, checksums
        )
        assert any(v.check == "checksum_verify" for v in violations)


# ═══════════════════════════════════════════════════════════════════════════
# ContractViolationError
# ═══════════════════════════════════════════════════════════════════════════


class TestContractViolationError:
    def test_message_includes_violations(self):
        v = [ContractViolation(check="min_size", detail="too small", path="/x")]
        err = ContractViolationError("step1", v)
        assert "step1" in str(err)
        assert "min_size" in str(err)
        assert "too small" in str(err)
