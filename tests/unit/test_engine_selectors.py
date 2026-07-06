"""Unit tests for the metagenomic_plasmid parameter selectors (_engine/selectors.py)."""

from __future__ import annotations

import pytest

from abi.plugins.metagenomic_plasmid._engine.schemas import ConfigError
from abi.plugins.metagenomic_plasmid._engine.selectors import record_auto_selection, select_value


# ---------------------------------------------------------------------------
# select_value
# ---------------------------------------------------------------------------
class TestSelectValue:
    def test_auto_mode_returns_configured(self):
        result = select_value(name="threads", configured=8, default=4, mode="auto")
        assert result == 8

    def test_interactive_mode_returns_configured(self):
        result = select_value(name="threads", configured=8, default=4, mode="interactive")
        assert result == 8

    def test_none_configured_returns_default(self):
        result = select_value(name="mode", configured=None, default="auto", mode="auto")
        assert result == "auto"

        result = select_value(
            name="mode", configured=None, default="interactive", mode="interactive"
        )
        assert result == "interactive"

    def test_invalid_mode_raises_config_error(self):
        with pytest.raises(ConfigError, match="Invalid mode"):
            select_value(name="x", configured=1, default=2, mode="batch")

    def test_value_not_in_choices_raises(self):
        with pytest.raises(ConfigError, match="must be one of"):
            select_value(
                name="platform",
                configured="nanopore",
                default="illumina",
                mode="auto",
                choices=["illumina", "pacbio"],
            )

    def test_value_in_choices_passes(self):
        result = select_value(
            name="platform",
            configured="nanopore",
            default="illumina",
            mode="auto",
            choices=["illumina", "nanopore"],
        )
        assert result == "nanopore"

    def test_empty_choices_list(self):
        with pytest.raises(ConfigError, match="must be one of"):
            select_value(
                name="x",
                configured="a",
                default="b",
                mode="auto",
                choices=[],
            )

    def test_none_choices_no_validation(self):
        result = select_value(
            name="x", configured="anything", default="b", mode="auto", choices=None
        )
        assert result == "anything"

    def test_configured_none_with_choices_uses_default(self):
        result = select_value(
            name="platform",
            configured=None,
            default="illumina",
            mode="auto",
            choices=["illumina", "nanopore"],
        )
        assert result == "illumina"


# ---------------------------------------------------------------------------
# record_auto_selection
# ---------------------------------------------------------------------------
class TestRecordAutoSelection:
    def test_adds_reason_to_empty_params(self):
        result = record_auto_selection({}, "default value")
        assert result == {"auto_selection_reason": "default value"}

    def test_preserves_existing_keys(self):
        result = record_auto_selection({"threads": 8, "mode": "auto"}, "chosen by system")
        assert result["threads"] == 8
        assert result["mode"] == "auto"
        assert result["auto_selection_reason"] == "chosen by system"

    def test_does_not_overwrite_existing_reason(self):
        result = record_auto_selection(
            {"auto_selection_reason": "original", "x": 1},
            "should not appear",
        )
        assert result["auto_selection_reason"] == "original"
        assert result["x"] == 1

    def test_returns_new_dict_not_mutate_input(self):
        params = {"key": "value"}
        result = record_auto_selection(params, "reason")
        assert "auto_selection_reason" not in params
        assert result["auto_selection_reason"] == "reason"
        assert result["key"] == "value"
