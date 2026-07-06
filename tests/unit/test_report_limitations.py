"""Unit tests for abi.report.limitations — load_limitations, formatters."""

from __future__ import annotations

from pathlib import Path

from abi.report.limitations import (
    format_limitations_html,
    format_limitations_markdown,
    load_limitations,
)


# ── load_limitations ──────────────────────────────────────────────────────


def test_load_limitations_from_list() -> None:
    """L46: source is already a list/tuple → return as-is (coerced to str)."""
    result = load_limitations(["Limitation A", "Limitation B"])
    assert result == ["Limitation A", "Limitation B"]


def test_load_limitations_from_tuple() -> None:
    """source is a tuple → coerced to list of strings."""
    result = load_limitations(("Lim A", "Lim B"))
    assert result == ["Lim A", "Lim B"]


def test_load_limitations_bare_string_path(tmp_path: Path) -> None:
    """L50: source is a bare string (not Path) → convert to Path."""
    path = tmp_path / "test_limitations.yaml"
    path.write_text("limitations:\n  - Item 1\n  - Item 2\n", encoding="utf-8")
    result = load_limitations(str(path))
    assert len(result) == 2


def test_load_limitations_file_does_not_exist() -> None:
    """L52: file doesn't exist → return empty list."""
    result = load_limitations(Path("/nonexistent/limitations.yaml"))
    assert result == []


def test_load_limitations_yaml_top_level_list(tmp_path: Path) -> None:
    """L57: YAML top-level is a list not a dict → return empty."""
    path = tmp_path / "list_top.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    result = load_limitations(path)
    assert result == []


def test_load_limitations_limitations_key_not_a_list(tmp_path: Path) -> None:
    """L60: 'limitations' key is not a list → return empty."""
    path = tmp_path / "non_list_lim.yaml"
    path.write_text("limitations: not_a_list\n", encoding="utf-8")
    result = load_limitations(path)
    assert result == []


# ── format_limitations_markdown ───────────────────────────────────────────


def test_format_limitations_markdown_empty() -> None:
    """L74: empty limitations → '' for markdown."""
    result = format_limitations_markdown([])
    assert result == ""


def test_format_limitations_markdown_with_items() -> None:
    """Non-empty limitations."""
    result = format_limitations_markdown(["Lim A", "Lim B"])
    assert "1. Lim A" in result
    assert "2. Lim B" in result


# ── format_limitations_html ───────────────────────────────────────────────


def test_format_limitations_html_empty() -> None:
    """L92: empty limitations → '' for HTML."""
    result = format_limitations_html([])
    assert result == ""


def test_format_limitations_html_with_items() -> None:
    """Non-empty limitations."""
    result = format_limitations_html(["Lim A"])
    assert "<li>Lim A</li>" in result
    assert "<ol>" in result
    assert "</ol>" in result


# ── load_limitations with Path source ──────────────────────────────────────


def test_load_limitations_from_path_object(tmp_path: Path) -> None:
    """L48: source is already a Path object."""
    path = tmp_path / "test_limitations.yaml"
    path.write_text("limitations:\n  - Item 1\n  - Item 2\n", encoding="utf-8")
    result = load_limitations(path)
    assert len(result) == 2
    assert "Item 1" in result


# ── Formatters with custom titles ──────────────────────────────────────────


def test_format_limitations_markdown_custom_title() -> None:
    """Custom title for markdown format."""
    result = format_limitations_markdown(["Lim A"], title="Caveats")
    assert "## Caveats" in result


def test_format_limitations_html_custom_title() -> None:
    """Custom title for HTML format."""
    result = format_limitations_html(["Lim A"], title="Caveats")
    assert "<h2>Caveats</h2>" in result


def test_format_limitations_markdown_non_string() -> None:
    """Coerces non-string items to str."""
    result = format_limitations_markdown([42])
    assert "1. 42" in result
