"""Unit tests for filesystem helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from abi.errors import ABIError
from abi.filesystem import ensure_directory, ensure_parent


class TestEnsureDirectory:
    def test_creates_missing_directory(self, tmp_path):
        result = ensure_directory(tmp_path / "new_dir")
        assert result.exists()
        assert result.is_dir()
        assert isinstance(result, Path)

    def test_returns_existing_directory(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        result = ensure_directory(existing)
        assert result == existing
        assert result.is_dir()

    def test_raises_on_file_not_directory(self, tmp_path):
        file_path = tmp_path / "a_file"
        file_path.write_text("content")
        with pytest.raises(ABIError):
            ensure_directory(file_path)

    def test_creates_nested_directories(self, tmp_path):
        result = ensure_directory(tmp_path / "a" / "b" / "c")
        assert result.exists()
        assert result.is_dir()
        assert result.parent == tmp_path / "a" / "b"
        assert result.parent.parent == tmp_path / "a"

    def test_label_in_error_message(self, tmp_path):
        file_path = tmp_path / "my_data"
        file_path.write_text("content")
        with pytest.raises(ABIError, match="Output folder exists but is not a directory"):
            ensure_directory(file_path, label="Output folder")


class TestEnsureParent:
    def test_creates_parent_directory(self, tmp_path):
        result = ensure_parent(tmp_path / "subdir" / "file.txt")
        assert (tmp_path / "subdir").exists()
        assert (tmp_path / "subdir").is_dir()

    def test_returns_path_unchanged(self, tmp_path):
        original = tmp_path / "subdir" / "file.txt"
        result = ensure_parent(original)
        assert result == original

    def test_existing_parent_no_error(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        result = ensure_parent(subdir / "file.txt")
        assert result == subdir / "file.txt"
