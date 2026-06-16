"""Unit tests for SafeFormatDict strict mode and template parameter validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest

from abi.errors import MissingTemplateParamError
from abi.tools import SafeFormatDict


class TestSafeFormatDictLenient:
    """Lenient mode (default): missing keys → "" + WARNING."""

    def test_known_key_returns_value(self):
        d = SafeFormatDict({"input": "file.fasta", "threads": 4})
        assert d["input"] == "file.fasta"
        assert d["threads"] == 4

    def test_missing_key_returns_empty_string(self):
        d = SafeFormatDict({"input": "file.fasta"})
        result = d["nonexistent"]
        assert result == ""

    def test_missing_key_is_recorded(self):
        d = SafeFormatDict({"input": "file.fasta"})
        _ = d["optional_flag"]
        _ = d["another_missing"]
        assert "optional_flag" in d.missing_keys
        assert "another_missing" in d.missing_keys

    def test_format_map_substitutes_missing_with_empty(self):
        template = "tool --input {input} --flag {optional_flag}"
        d = SafeFormatDict({"input": "file.fasta"})
        result = template.format_map(d)
        assert result == "tool --input file.fasta --flag "
        assert "optional_flag" in d.missing_keys

    def test_format_map_with_all_keys_present(self):
        template = "tool --input {input} --threads {threads}"
        d = SafeFormatDict({"input": "file.fasta", "threads": 8})
        result = template.format_map(d)
        assert result == "tool --input file.fasta --threads 8"
        assert d.missing_keys == []

    def test_missing_keys_deduplication(self):
        """Same key requested multiple times → recorded once per lookup."""
        d = SafeFormatDict({"input": "file.fasta"})
        _ = d["missing"]
        _ = d["missing"]
        assert d.missing_keys == ["missing", "missing"]


class TestSafeFormatDictStrict:
    """Strict mode: missing keys → MissingTemplateParamError."""

    def test_strict_raises_on_missing(self):
        d = SafeFormatDict({"input": "file.fasta"}, strict=True, tool_name="fastp")
        with pytest.raises(MissingTemplateParamError) as excinfo:
            _ = d["undefined_param"]
        assert "undefined_param" in str(excinfo.value)
        assert "fastp" in str(excinfo.value)

    def test_strict_does_not_raise_for_known_keys(self):
        d = SafeFormatDict({"input": "file.fasta", "threads": 4}, strict=True)
        assert d["input"] == "file.fasta"
        assert d["threads"] == 4

    def test_strict_via_env_var(self, monkeypatch):
        """ABI_STRICT_TEMPLATES=1 enables strict mode when not explicitly set."""
        monkeypatch.setenv("ABI_STRICT_TEMPLATES", "1")
        d = SafeFormatDict({"input": "file.fasta"})
        assert d.strict is True
        with pytest.raises(MissingTemplateParamError):
            _ = d["undefined"]

    def test_strict_records_missing_before_raising(self):
        d = SafeFormatDict({"input": "file.fasta"}, strict=True)
        try:
            _ = d["param1"]
        except MissingTemplateParamError:
            pass
        assert "param1" in d.missing_keys

    def test_explicit_strict_overrides_env(self, monkeypatch):
        """Explicit strict=False overrides ABI_STRICT_TEMPLATES=1."""
        monkeypatch.setenv("ABI_STRICT_TEMPLATES", "1")
        d = SafeFormatDict({"input": "file.fasta"}, strict=False)
        assert d.strict is False
        result = d["undefined"]
        assert result == ""

    def test_format_map_raises_in_strict_mode(self):
        template = "tool --input {input} --flag {undefined_flag}"
        d = SafeFormatDict({"input": "file.fasta"}, strict=True)
        with pytest.raises(MissingTemplateParamError):
            template.format_map(d)


class TestSafeFormatDictToolName:
    """Tool name is included in error messages."""

    def test_tool_name_in_error(self):
        d = SafeFormatDict({}, strict=True, tool_name="kraken2")
        with pytest.raises(MissingTemplateParamError) as excinfo:
            _ = d["database"]
        assert "kraken2" in str(excinfo.value)

    def test_tool_name_defaults_to_empty(self):
        d = SafeFormatDict({}, strict=True)
        with pytest.raises(MissingTemplateParamError) as excinfo:
            _ = d["missing"]
        assert "unknown" in str(excinfo.value)
