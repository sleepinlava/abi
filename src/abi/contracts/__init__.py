"""Machine-checkable ABI plugin and tool contract helpers."""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from abi.config import load_yaml

__all__ = [
    "PLUGIN_MANIFEST_NAME",
    "TOOL_CONTRACT_SCHEMA",
    "ContractValidationError",
    "load_plugin_manifest",
    "load_tool_contracts",
    "validate_plugin_contract_files",
    "validate_tool_contract",
]

PLUGIN_MANIFEST_NAME = "abi-plugin.yaml"

TOOL_CONTRACT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ABI Tool Contract",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "abi_version",
        "tool_id",
        "name",
        "category",
        "purpose",
        "inputs",
        "outputs",
        "execution",
        "failure_handling",
    ],
    "properties": {
        "abi_version": {"type": "string"},
        "tool_id": {"type": "string"},
        "name": {"type": "string"},
        "category": {"type": "string"},
        "purpose": {"type": "string"},
        "when_to_use": {"type": "array", "items": {"type": "string"}},
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "execution": {"type": "object"},
        "normalization": {"type": "object"},
        "failure_handling": {"type": "object"},
    },
}

_GENERIC_TEMPLATE_FIELDS = {
    "mode",
    "project_root",
    "abundance_label",
    "metaphlan_long_reads_flag",
}


class ContractValidationError(ValueError):
    """Raised when plugin or tool contracts are inconsistent."""


def load_plugin_manifest(plugin_root: str | Path) -> Dict[str, Any]:
    """Load ``abi-plugin.yaml`` from a plugin directory."""
    root = Path(plugin_root)
    path = root / PLUGIN_MANIFEST_NAME
    if not path.exists():
        raise ContractValidationError(f"Missing plugin manifest: {path}")
    return load_yaml(path)


def load_tool_contracts(plugin_root: str | Path) -> Dict[str, Dict[str, Any]]:
    """Load all ``tool_contracts/*.yaml`` files for a plugin."""
    root = Path(plugin_root)
    contracts_dir = root / "tool_contracts"
    if not contracts_dir.exists():
        raise ContractValidationError(f"Missing tool_contracts directory: {contracts_dir}")
    contracts: Dict[str, Dict[str, Any]] = {}
    for path in sorted(contracts_dir.glob("*.yaml")):
        contract = load_yaml(path)
        validate_tool_contract(contract, path=path)
        tool_id = str(contract["tool_id"])
        if tool_id in contracts:
            raise ContractValidationError(f"Duplicate tool contract for {tool_id!r}")
        if path.stem != tool_id:
            raise ContractValidationError(
                f"Tool contract filename {path.name!r} must match tool_id {tool_id!r}"
            )
        contracts[tool_id] = contract
    if not contracts:
        raise ContractValidationError(f"No tool contracts found in: {contracts_dir}")
    return contracts


def validate_tool_contract(contract: Mapping[str, Any], *, path: str | Path | None = None) -> None:
    """Validate one ABI tool contract against the SDK's required structure."""
    label = str(path) if path else str(contract.get("tool_id", "<unknown>"))
    allowed = set(TOOL_CONTRACT_SCHEMA["properties"])
    unknown = set(contract) - allowed
    if unknown:
        raise ContractValidationError(f"{label}: unknown contract fields: {sorted(unknown)}")
    for key in TOOL_CONTRACT_SCHEMA["required"]:
        if key not in contract:
            raise ContractValidationError(f"{label}: missing required field {key!r}")
    for key in ("abi_version", "tool_id", "name", "category", "purpose"):
        _require_non_empty_string(contract.get(key), f"{label}: {key}")
    _require_mapping(contract.get("inputs"), f"{label}: inputs")
    _require_mapping(contract.get("outputs"), f"{label}: outputs")
    execution = _require_mapping(contract.get("execution"), f"{label}: execution")
    for key in ("env_name", "executable", "command_template"):
        _require_non_empty_string(execution.get(key), f"{label}: execution.{key}")
    if "network" in execution and not isinstance(execution["network"], bool):
        raise ContractValidationError(f"{label}: execution.network must be boolean")
    if "writes_output" in execution and not isinstance(execution["writes_output"], bool):
        raise ContractValidationError(f"{label}: execution.writes_output must be boolean")
    if "when_to_use" in contract:
        _require_string_list(contract["when_to_use"], f"{label}: when_to_use")
    if "normalization" in contract:
        normalization = _require_mapping(contract["normalization"], f"{label}: normalization")
        if "tables" in normalization:
            _require_string_list(normalization["tables"], f"{label}: normalization.tables")
    failure_handling = _require_mapping(
        contract.get("failure_handling"),
        f"{label}: failure_handling",
    )
    for code, handling in failure_handling.items():
        handling_mapping = _require_mapping(handling, f"{label}: failure_handling.{code}")
        _require_non_empty_string(handling_mapping.get("hint"), f"{label}: {code}.hint")


def validate_plugin_contract_files(plugin: Any) -> None:
    """Validate a plugin's manifest, standard tables, and machine tool contracts."""
    if not hasattr(plugin, "root"):
        return
    root = Path(plugin.root)
    manifest = load_plugin_manifest(root)
    _validate_manifest(plugin, root, manifest)
    contracts = load_tool_contracts(root)
    registry = plugin.registry()
    registry_by_id = {tool["id"]: tool for tool in registry.list_tools()}
    required_contracts = set(registry_by_id)
    missing_contracts = required_contracts - set(contracts)
    if missing_contracts:
        raise ContractValidationError(
            f"{plugin.plugin_id}: missing required tool contracts: {sorted(missing_contracts)}"
        )
    unknown_contracts = set(contracts) - set(registry_by_id)
    if unknown_contracts:
        raise ContractValidationError(
            f"{plugin.plugin_id}: contracts without registry tools: {sorted(unknown_contracts)}"
        )
    for tool_id in sorted(required_contracts):
        if tool_id not in registry_by_id:
            raise ContractValidationError(
                f"{plugin.plugin_id}: contract tool {tool_id!r} is not in registry"
            )
        _validate_contract_matches_registry(contracts[tool_id], registry_by_id[tool_id])
    table_schemas = plugin.table_schemas()
    _validate_declared_tables(root, manifest, table_schemas)
    for tool_id, contract in contracts.items():
        normalization = contract.get("normalization", {})
        if not isinstance(normalization, Mapping):
            continue
        for table_name in normalization.get("tables", []):
            if table_name not in table_schemas:
                raise ContractValidationError(
                    f"{plugin.plugin_id}: {tool_id} normalizes unknown table {table_name!r}"
                )


def _validate_manifest(plugin: Any, root: Path, manifest: Mapping[str, Any]) -> None:
    for key in (
        "abi_version",
        "plugin_id",
        "display_name",
        "description",
        "plugin_type",
        "entry_point",
        "tool_registry",
        "standard_tables",
        "tool_contracts",
    ):
        _require_non_empty_string(manifest.get(key), f"{root / PLUGIN_MANIFEST_NAME}: {key}")
    if manifest["plugin_id"] != plugin.plugin_id:
        raise ContractValidationError(
            f"{plugin.plugin_id}: manifest plugin_id is {manifest['plugin_id']!r}"
        )
    for key in ("tool_registry", "standard_tables", "tool_contracts"):
        declared = root / str(manifest[key])
        if not declared.exists():
            raise ContractValidationError(f"{plugin.plugin_id}: missing manifest path {declared}")
    if "core_contracts" in manifest:
        _require_string_list(manifest["core_contracts"], f"{plugin.plugin_id}: core_contracts")


def _validate_contract_matches_registry(
    contract: Mapping[str, Any],
    registry_tool: Mapping[str, Any],
) -> None:
    tool_id = str(contract["tool_id"])
    execution = contract["execution"]
    assert isinstance(execution, Mapping)
    for key in ("env_name", "executable"):
        if str(execution[key]) != str(registry_tool.get(key, "")):
            raise ContractValidationError(
                f"{tool_id}: contract execution.{key} does not match registry"
            )
    if _normalize_template(str(execution["command_template"])) != _normalize_template(
        str(registry_tool.get("command_template", ""))
    ):
        raise ContractValidationError(
            f"{tool_id}: contract execution.command_template does not match registry"
        )
    if str(contract["category"]) != str(registry_tool.get("category", "")):
        raise ContractValidationError(f"{tool_id}: contract category does not match registry")
    declared_fields = set(contract["inputs"]) | set(contract["outputs"])
    missing_registry_inputs = set(registry_tool.get("inputs", [])) - declared_fields
    if missing_registry_inputs:
        raise ContractValidationError(
            f"{tool_id}: registry inputs missing from contract: {sorted(missing_registry_inputs)}"
        )
    template_fields = set(_template_fields(str(registry_tool.get("command_template", ""))))
    missing_template_fields = template_fields - declared_fields - _GENERIC_TEMPLATE_FIELDS
    if missing_template_fields:
        raise ContractValidationError(
            f"{tool_id}: command template fields missing from contract: "
            f"{sorted(missing_template_fields)}"
        )


def _validate_declared_tables(
    root: Path,
    manifest: Mapping[str, Any],
    table_schemas: Mapping[str, Iterable[str]],
) -> None:
    data = load_yaml(root / str(manifest["standard_tables"]))
    table_label = f"{root / str(manifest['standard_tables'])}: tables"
    tables = _require_mapping(data.get("tables"), table_label)
    declared_tables = set(tables)
    runtime_tables = set(table_schemas)
    if declared_tables != runtime_tables:
        raise ContractValidationError(
            "standard_tables.yaml must match plugin.table_schemas(): "
            f"declared={sorted(declared_tables)} runtime={sorted(runtime_tables)}"
        )
    for table_name, fields in table_schemas.items():
        declared_fields = tables.get(table_name)
        if list(declared_fields or []) != list(fields):
            raise ContractValidationError(f"{table_name}: declared columns do not match runtime")


def _template_fields(command_template: str) -> list[str]:
    fields: list[str] = []
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(command_template):
        if not field_name:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root not in fields:
            fields.append(root)
    return fields


def _normalize_template(command_template: str) -> str:
    return " ".join(command_template.split())


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ContractValidationError(f"{label} must be a non-empty mapping")
    return value


def _require_non_empty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string")


def _require_string_list(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise ContractValidationError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractValidationError(f"{label} entries must be non-empty strings")
