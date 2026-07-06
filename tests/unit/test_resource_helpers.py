"""Unit tests for pure-function helpers in abi.resources."""

from pathlib import Path

from abi.resources import (
    _directory_file_count,
    _generic_resource_message,
    _generic_resource_status,
    _is_placeholder_resource_value,
)


# --------------------------------------------------------------------------- #
#  _is_placeholder_resource_value
# --------------------------------------------------------------------------- #

class TestIsPlaceholderResourceValue:
    """Tests for _is_placeholder_resource_value."""

    def test_placeholder_markers_upper(self) -> None:
        """True for uppercase placeholder markers."""
        assert _is_placeholder_resource_value("NOT_CONFIGURED") is True
        assert _is_placeholder_resource_value("TODO") is True
        assert _is_placeholder_resource_value("PLACEHOLDER") is True

    def test_placeholder_markers_case_insensitive(self) -> None:
        """True regardless of casing."""
        assert _is_placeholder_resource_value("Not_Configured") is True
        assert _is_placeholder_resource_value("not_configured") is True
        assert _is_placeholder_resource_value("todo") is True
        assert _is_placeholder_resource_value("Todo") is True
        assert _is_placeholder_resource_value("Placeholder") is True
        assert _is_placeholder_resource_value("placeholder") is True

    def test_placeholder_markers_embedded(self) -> None:
        """True when marker appears anywhere in the string."""
        assert _is_placeholder_resource_value("some_NOT_CONFIGURED_path") is True
        assert _is_placeholder_resource_value("TODO_later") is True

    def test_path_prefix_forward_slashes(self) -> None:
        """True for paths starting with known placeholder prefixes (forward slash)."""
        for prefix in ("/path/to/", "path/to/", "/your/path/", "your/path/"):
            assert _is_placeholder_resource_value(f"{prefix}some/resource") is True

    def test_path_prefix_backslashes(self) -> None:
        """True for paths starting with known placeholder prefixes (backslash)."""
        assert _is_placeholder_resource_value("\\path\\to\\some\\resource") is True
        assert _is_placeholder_resource_value("path\\to\\some\\resource") is True
        assert _is_placeholder_resource_value("\\your\\path\\some\\resource") is True
        assert _is_placeholder_resource_value("your\\path\\some\\resource") is True

    def test_real_paths_false(self) -> None:
        """False for real-looking paths."""
        assert _is_placeholder_resource_value("/data/genomes/human.fa") is False
        assert _is_placeholder_resource_value("resources/db") is False
        assert _is_placeholder_resource_value("/home/user/project/data") is False
        assert _is_placeholder_resource_value("./local/path") is False

    def test_empty_and_none(self) -> None:
        """Empty strings and None-like values are not placeholders."""
        assert _is_placeholder_resource_value("") is False
        # None → str(None) → "None" which does not match markers or prefixes
        assert _is_placeholder_resource_value(None) is False


# --------------------------------------------------------------------------- #
#  _generic_resource_status
# --------------------------------------------------------------------------- #

class TestGenericResourceStatus:
    """Tests for _generic_resource_status."""

    def test_none_is_not_configured(self) -> None:
        assert _generic_resource_status(None) == "not_configured"

    def test_empty_string_is_not_configured(self) -> None:
        assert _generic_resource_status("") == "not_configured"

    def test_placeholder_marker_is_not_configured(self) -> None:
        assert _generic_resource_status("NOT_CONFIGURED") == "not_configured"
        assert _generic_resource_status("TODO") == "not_configured"
        assert _generic_resource_status("PLACEHOLDER") == "not_configured"

    def test_missing_path(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        assert not nonexistent.exists()
        assert _generic_resource_status(str(nonexistent)) == "missing"

    def test_existing_file_is_ok(self, tmp_path: Path) -> None:
        f = tmp_path / "real_file.txt"
        f.write_text("hello")
        assert _generic_resource_status(str(f)) == "ok"

    def test_nonempty_directory_is_ok(self, tmp_path: Path) -> None:
        d = tmp_path / "nonempty_dir"
        d.mkdir()
        (d / "child.txt").write_text("data")
        assert _generic_resource_status(str(d)) == "ok"

    def test_empty_directory_is_incomplete(self, tmp_path: Path) -> None:
        d = tmp_path / "empty_dir"
        d.mkdir()
        assert _generic_resource_status(str(d)) == "incomplete"


# --------------------------------------------------------------------------- #
#  _generic_resource_message
# --------------------------------------------------------------------------- #

class TestGenericResourceMessage:
    """Tests for _generic_resource_message."""

    def test_ok_message(self) -> None:
        assert _generic_resource_message("ok") == "Configured resource path exists."

    def test_missing_message(self) -> None:
        assert _generic_resource_message("missing") == (
            "Configured resource path does not exist."
        )

    def test_incomplete_message(self) -> None:
        assert _generic_resource_message("incomplete") == (
            "Configured resource directory is empty; database setup may be incomplete."
        )

    def test_not_configured_message(self) -> None:
        assert _generic_resource_message("not_configured") == (
            "Resource path is not configured."
        )

    def test_unknown_status_falls_back_to_not_configured(self) -> None:
        assert _generic_resource_message("unknown") == "Resource path is not configured."
        assert _generic_resource_message("") == "Resource path is not configured."


# --------------------------------------------------------------------------- #
#  _directory_file_count
# --------------------------------------------------------------------------- #

class TestDirectoryFileCount:
    """Tests for _directory_file_count."""

    def test_file_returns_one(self, tmp_path: Path) -> None:
        f = tmp_path / "single.txt"
        f.write_text("content")
        assert _directory_file_count(f) == 1

    def test_nonexistent_path_returns_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "ghost"
        assert not p.exists()
        assert _directory_file_count(p) == 0

    def test_empty_directory_returns_zero(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        assert _directory_file_count(d) == 0

    def test_directory_with_files_returns_file_count(self, tmp_path: Path) -> None:
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")
        (d / "c.txt").write_text("c")
        # rglob("*") recurses into subdirectories
        (d / "sub").mkdir()
        (d / "sub" / "d.txt").write_text("d")
        assert _directory_file_count(d) == 4

    def test_nested_directories_count_all_files(self, tmp_path: Path) -> None:
        d = tmp_path / "nested"
        d.mkdir()
        (d / "x.txt").write_text("x")
        inner = d / "inner"
        inner.mkdir()
        (inner / "y.txt").write_text("y")
        (inner / "z.txt").write_text("z")
        # rglob("*") counts files recursively
        assert _directory_file_count(d) == 3
