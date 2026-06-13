"""Testing helpers for ABI plugin authors."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from abi.contracts import ContractValidationError, validate_plugin_contract_files
from abi.tools import ToolRegistry


def assert_plugin_contract(plugin: Any) -> None:
    """Assert that a plugin exposes ABI's minimum SDK contract."""
    for name in ("plugin_id", "display_name", "description", "report_title"):
        value = getattr(plugin, name, None)
        assert isinstance(value, str) and value.strip(), f"{name} must be a non-empty string"

    required_methods = (
        "load_config",
        "build_plan",
        "registry",
        "table_schemas",
        "parse_outputs",
        "write_report",
    )
    for name in required_methods:
        assert callable(getattr(plugin, name, None)), f"{name} must be callable"

    registry = plugin.registry()
    assert isinstance(registry, ToolRegistry), "registry() must return abi.tools.ToolRegistry"
    assert registry.ids(), "registry() must define at least one tool"

    table_schemas = plugin.table_schemas()
    assert isinstance(table_schemas, Mapping), "table_schemas() must return a mapping"
    assert table_schemas, "table_schemas() must define at least one table"
    for table_name, fields in table_schemas.items():
        assert isinstance(table_name, str) and table_name.strip(), "table names must be strings"
        assert isinstance(fields, Iterable), f"{table_name} fields must be iterable"
        field_list = list(fields)
        assert field_list, f"{table_name} must define at least one field"
        valid_fields = all(isinstance(field, str) and field.strip() for field in field_list)
        assert valid_fields, f"{table_name} fields must be non-empty strings"

    try:
        validate_plugin_contract_files(plugin)
    except ContractValidationError as exc:
        raise AssertionError(str(exc)) from exc
