"""Unit tests for timeout parsing (C5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest

from abi.timeouts import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    mapping_block,
    parse_timeout_seconds,
    timeout_from_env_or_value,
)


class TestParseTimeoutSeconds:
    def test_none_returns_default(self):
        assert parse_timeout_seconds(None, default=60.0) == 60.0

    def test_empty_string_returns_default(self):
        assert parse_timeout_seconds("", default=60.0) == 60.0

    def test_positive_float(self):
        assert parse_timeout_seconds(300.0, default=None) == 300.0

    def test_positive_int(self):
        assert parse_timeout_seconds(600, default=None) == 600.0

    def test_disabled_strings_return_none(self):
        for val in ("0", "false", "no", "none", "off", "disabled", "  OFF  "):
            assert parse_timeout_seconds(val, default=60.0) is None, f"failed for {val!r}"

    def test_negative_returns_none(self):
        assert parse_timeout_seconds(-1, default=60.0) is None

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="timeout_seconds"):
            parse_timeout_seconds("not_a_number", default=60.0)

    def test_zero_returns_none(self):
        assert parse_timeout_seconds(0, default=60.0) is None

    def test_default_none_passed_through(self):
        assert parse_timeout_seconds(None, default=None) is None


class TestTimeoutFromEnvOrValue:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("ABI_TEST_TIMEOUT", "30")
        result = timeout_from_env_or_value("ABI_TEST_TIMEOUT", 999.0, default=60.0)
        assert result == 30.0

    def test_falls_back_to_value_when_env_not_set(self):
        result = timeout_from_env_or_value("ABI_NONEXISTENT_XXXX", 45.0, default=60.0)
        assert result == 45.0

    def test_falls_back_to_default_when_value_none(self):
        result = timeout_from_env_or_value("ABI_NONEXISTENT_XXXX2", None, default=60.0)
        assert result == 60.0

    def test_env_disabled_overrides_value(self, monkeypatch):
        monkeypatch.setenv("ABI_TEST_TIMEOUT2", "disabled")
        result = timeout_from_env_or_value("ABI_TEST_TIMEOUT2", 300.0, default=60.0)
        assert result is None


class TestMappingBlock:
    def test_returns_mapping_as_is(self):
        config = {"section": {"key": "value"}}
        assert mapping_block(config, "section") == {"key": "value"}

    def test_returns_empty_for_non_mapping(self):
        assert mapping_block({"section": "string"}, "section") == {}
        assert mapping_block({"section": 42}, "section") == {}

    def test_returns_empty_for_missing_key(self):
        assert mapping_block({}, "missing") == {}


def test_default_constants_are_reasonable():
    assert DEFAULT_TOOL_TIMEOUT_SECONDS == 7 * 24 * 60 * 60  # 7 days
