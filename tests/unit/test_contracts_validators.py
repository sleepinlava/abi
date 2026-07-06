"""Unit tests for private validator functions in abi.contracts."""

from __future__ import annotations

import pytest

from abi.contracts import (
    ContractValidationError,
    _normalize_template,
    _require_mapping,
    _require_non_empty_string,
    _require_string_list,
    _template_fields,
    _validate_resources_block,
)

# ---------------------------------------------------------------------------
# _require_non_empty_string
# ---------------------------------------------------------------------------


def test_require_non_empty_string_valid():
    """Should not raise for a non-empty string."""
    _require_non_empty_string("hello", "test_label")


def test_require_non_empty_string_none():
    """None should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_non_empty_string(None, "test_label")


def test_require_non_empty_string_empty():
    """Empty string should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_non_empty_string("", "test_label")


def test_require_non_empty_string_whitespace():
    """Whitespace-only string should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_non_empty_string("   ", "test_label")


# ---------------------------------------------------------------------------
# _require_mapping
# ---------------------------------------------------------------------------


def test_require_mapping_valid_dict():
    """Non-empty dict should pass."""
    _require_mapping({"key": "val"}, "test_label")


def test_require_mapping_none():
    """None should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_mapping(None, "test_label")


def test_require_mapping_empty_dict():
    """Empty dict should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_mapping({}, "test_label")


def test_require_mapping_list():
    """A list should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_mapping([1, 2, 3], "test_label")


def test_require_mapping_string():
    """A string should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_mapping("not a dict", "test_label")


# ---------------------------------------------------------------------------
# _require_string_list
# ---------------------------------------------------------------------------


def test_require_string_list_valid():
    """Non-empty list of non-empty strings should pass."""
    _require_string_list(["a", "b"], "test_label")


def test_require_string_list_empty():
    """Empty list raises ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_string_list([], "test_label")


def test_require_string_list_not_a_list():
    """A non-list should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_string_list("not a list", "test_label")


def test_require_string_list_contains_non_string():
    """List containing a non-string element should raise."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_string_list(["valid", 42], "test_label")


def test_require_string_list_contains_whitespace_only():
    """List containing a whitespace-only string should raise."""
    with pytest.raises(ContractValidationError, match="test_label"):
        _require_string_list(["valid", "   "], "test_label")


# ---------------------------------------------------------------------------
# _template_fields
# ---------------------------------------------------------------------------


def test_template_fields_simple():
    """Plain {name} placeholders are extracted."""
    fields = _template_fields("hello {name}, welcome to {place}")
    assert fields == ["name", "place"]


def test_template_fields_no_fields():
    """String with no placeholders returns empty list."""
    assert _template_fields("no placeholders") == []


def test_template_fields_ignores_dotted_as_literal():
    """Dotted access like {obj.attr} is not in the field list as-is."""
    fields = _template_fields("{obj.attr}")
    assert "obj.attr" not in fields


def test_template_fields_ignores_bracketed_as_literal():
    """Bracketed access like {arr[0]} is not in the field list as-is."""
    fields = _template_fields("{arr[0]}")
    assert "arr[0]" not in fields


# ---------------------------------------------------------------------------
# _normalize_template
# ---------------------------------------------------------------------------


def test_normalize_template_multi_whitespace():
    """Multiple spaces are collapsed."""
    result = _normalize_template("cmd    --flag  --other")
    assert "    " not in result
    assert result == "cmd --flag --other"


def test_normalize_template_newlines():
    """Newlines are replaced with spaces."""
    result = _normalize_template("cmd\n--flag\n--other")
    assert "\n" not in result
    assert result == "cmd --flag --other"


def test_normalize_template_no_change():
    """Already normalised template is unchanged."""
    result = _normalize_template("cmd --flag --other")
    assert result == "cmd --flag --other"


# ---------------------------------------------------------------------------
# _validate_resources_block
# ---------------------------------------------------------------------------


def test_validate_resources_block_valid():
    """Valid resource block should not raise."""
    _validate_resources_block({"cpu": 4, "memory": "16G", "walltime": "1h"}, "test")


def test_validate_resources_block_cpu_float():
    """cpu as a float should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="cpu"):
        _validate_resources_block({"cpu": 4.0}, "test")


def test_validate_resources_block_cpu_string():
    """cpu as a string should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="cpu"):
        _validate_resources_block({"cpu": "four"}, "test")


def test_validate_resources_block_cpu_zero():
    """cpu = 0 should raise (must be >= 1)."""
    with pytest.raises(ContractValidationError, match="cpu"):
        _validate_resources_block({"cpu": 0}, "test")


def test_validate_resources_block_memory_int():
    """memory as an int should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="memory"):
        _validate_resources_block({"memory": 16}, "test")


def test_validate_resources_block_walltime_int():
    """walltime as an int should raise ContractValidationError."""
    with pytest.raises(ContractValidationError, match="walltime"):
        _validate_resources_block({"walltime": 60}, "test")


def test_validate_resources_block_empty_block():
    """Empty resources block raises (mapping must be non-empty)."""
    with pytest.raises(ContractValidationError, match="resources"):
        _validate_resources_block({}, "test")
