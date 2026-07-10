"""Tests for path_policy — validate_sample_id and resolve_within."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from abi.errors import InputPolicyError as PublicInputPolicyError
from abi.path_policy import (
    _MAX_SAMPLE_ID_LENGTH,
    InputPolicyError,
    resolve_within,
    validate_sample_id,
)


def test_input_policy_error_uses_public_error_contract() -> None:
    assert InputPolicyError is PublicInputPolicyError


# ── validate_sample_id ──────────────────────────────────────────────────────


class TestValidateSampleId:
    """Normal / valid sample_id values."""

    @pytest.mark.parametrize(
        "value",
        [
            "S1",
            "sample_01",
            "sample-01",
            "Sample_123_test",
            "a" * 64,
            "test.sample",  # dot in middle is fine
            "test sample",  # spaces in middle are fine
            "test-sample_v2",
            "SRR12345678",
            "0123456789",
        ],
    )
    def test_valid_sample_ids(self, value: str) -> None:
        assert validate_sample_id(value) == value

    def test_strips_nothing_when_clean(self) -> None:
        assert validate_sample_id("clean_id") == "clean_id"


class TestValidateSampleIdRejections:
    """Rejected sample_id values."""

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "\t",
            "\n",
        ],
    )
    def test_empty_or_whitespace(self, value: str) -> None:
        with pytest.raises(InputPolicyError):
            validate_sample_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "  leading",
            "trailing  ",
            "\tindented",
        ],
    )
    def test_leading_trailing_whitespace(self, value: str) -> None:
        with pytest.raises(InputPolicyError):
            validate_sample_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "/etc/passwd",
            "/root/.ssh/id_rsa",
            "C:\\Windows\\System32",
            "D:\\data",
        ],
    )
    def test_absolute_paths(self, value: str) -> None:
        with pytest.raises(InputPolicyError):
            validate_sample_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "a/b",
            "a\\b",
            "../escape",
            "..\\escape",
            "a/../b",
            "a\\..\\b",
            ".",
            "..",
            "sub/dir/name",
        ],
    )
    def test_traversal_and_separators(self, value: str) -> None:
        with pytest.raises(InputPolicyError):
            validate_sample_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "test\x00null",
            "test\x01ctrl",
            "test\x1fctrl",
            "test\x7fdel",
        ],
    )
    def test_control_characters(self, value: str) -> None:
        with pytest.raises(InputPolicyError):
            validate_sample_id(value)

    def test_unix_traversal_variants(self) -> None:
        for v in ("a/../b", "a/./b", "./a", "../a", "../../../etc/passwd"):
            with pytest.raises(InputPolicyError, match="sample_id"):
                validate_sample_id(v)

    def test_windows_traversal_variants(self) -> None:
        for v in ("a\\..\\b", ".\\.\\a", "..\\a", "..\\..\\..\\Windows"):
            with pytest.raises(InputPolicyError, match="sample_id"):
                validate_sample_id(v)

    def test_excessive_length(self) -> None:
        long_id = "x" * (_MAX_SAMPLE_ID_LENGTH + 10)
        with pytest.raises(InputPolicyError, match="must not exceed"):
            validate_sample_id(long_id)

    def test_edge_max_length_passes(self) -> None:
        max_ok = "x" * _MAX_SAMPLE_ID_LENGTH
        assert validate_sample_id(max_ok) == max_ok


# ── resolve_within ──────────────────────────────────────────────────────────


class TestResolveWithin:
    """Containment enforcement."""

    def test_normal_path_within_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = resolve_within(root, "sub/output_dir")
            expected = (root / "sub/output_dir").resolve()
            assert result == expected

    def test_path_equals_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = resolve_within(root, ".", label="output_dir")
            assert result == root.resolve()

    def test_absolute_candidate_within_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "sub"
            sub.mkdir()
            result = resolve_within(root, str(sub), label="output_dir")
            assert result == sub.resolve()

    def test_absolute_candidate_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = Path(tempfile.gettempdir()) / "outside"
            with pytest.raises(InputPolicyError, match="escapes output root"):
                resolve_within(root, str(outside), label="output_dir")

    def test_traversal_escape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with pytest.raises(InputPolicyError, match="escapes output root"):
                resolve_within(root, "../etc/passwd", label="output_dir")

    def test_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Create a directory outside root
            outside = Path(tempfile.gettempdir())
            # Create a symlink inside root pointing outside
            link = root / "escape_link"
            link.symlink_to(outside)
            with pytest.raises(InputPolicyError, match="escapes output root"):
                resolve_within(root, "escape_link/target", label="output_dir")

    def test_symlink_escape_direct(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = Path(tempfile.gettempdir())
            link = root / "escape_link"
            link.symlink_to(outside)
            with pytest.raises(InputPolicyError, match="escapes output root"):
                resolve_within(root, "escape_link", label="output_dir")

    def test_root_does_not_exist_yet(self) -> None:
        """resolve_within should work even when root doesn't exist yet
        (e.g. when creating new output dirs)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "new_root"
            result = resolve_within(root, "sub/dir")
            expected = (root / "sub/dir").resolve()
            assert result == expected

    def test_label_in_error_message(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with pytest.raises(InputPolicyError, match="test_label escapes output root"):
                resolve_within(root, "../escape", label="test_label")

    def test_null_byte_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with pytest.raises(InputPolicyError):
                resolve_within(root, "sub\x00dir", label="output_dir")

    def test_dot_dot_components(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with pytest.raises(InputPolicyError, match="escapes output root"):
                resolve_within(root, "sub/../../../etc", label="output_dir")


# ── Real-world integration scenarios ────────────────────────────────────────


class TestIntegrationScenarios:
    """Scenarios matching the attack vectors documented in the audit."""

    def test_sample_id_as_subdirectory(self) -> None:
        """sample_id used as a path component: ../../etc"""
        with pytest.raises(InputPolicyError):
            validate_sample_id("../../etc")

    def test_sample_id_as_absolute(self) -> None:
        """sample_id as absolute path: /tmp/malware"""
        with pytest.raises(InputPolicyError):
            validate_sample_id("/tmp/malware")

    def test_sample_id_null_byte(self) -> None:
        """sample_id with NUL byte injection"""
        with pytest.raises(InputPolicyError):
            validate_sample_id("safe\x00/etc/passwd")

    def test_resolved_path_not_escaping_with_root_boundary(self) -> None:
        """Resolving a deeply nested path within root should pass."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deep = root / "a" / "b" / "c" / "d"
            result = resolve_within(root, "a/b/c/d")
            assert result == deep.resolve()

    def test_relative_path_with_dot_slash_prefix(self) -> None:
        """./ prefix should not escape (it stays within root)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = resolve_within(root, "./subdir")
            assert result == (root / "subdir").resolve()
