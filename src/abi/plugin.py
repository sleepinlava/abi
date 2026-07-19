"""Declarative base class for filesystem-backed ABI plugins."""

from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Iterable, Mapping

from abi.config import load_yaml
from abi.contracts import (
    ContractValidationError,
    load_plugin_manifest,
    validate_plugin_manifest,
)
from abi.tools import ToolRegistry

__all__ = ["DeclarativeABIPlugin"]


class DeclarativeABIPlugin:
    """Supply plugin identity and registries from ``abi-plugin.yaml``.

    Subclasses only implement workflow behaviour. By default the manifest is
    expected beside the subclass module; monorepos may set ``plugin_root``.
    The declaration is validated when the subclass is imported, so malformed
    plugins fail during discovery instead of later during execution.
    """

    plugin_root: ClassVar[str | Path | None] = None
    root: ClassVar[Path]
    plugin_id: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]
    report_title: ClassVar[str]
    _manifest: ClassVar[Mapping[str, Any]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        root = cls._resolve_plugin_root()
        manifest = load_plugin_manifest(root)

        cls.root = root
        for field in ("plugin_id", "display_name", "description", "report_title"):
            value = manifest.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ContractValidationError(
                    f"{root / 'abi-plugin.yaml'}: {field} must be a non-empty string"
                )
            setattr(cls, field, value)
        cls._manifest = MappingProxyType(dict(manifest))

        validate_plugin_manifest(cls, root, manifest)
        declared_entry_point = str(manifest["entry_point"])
        actual_entry_point = f"{cls.__module__}:{cls.__qualname__}"
        if declared_entry_point != actual_entry_point:
            raise TypeError(
                f"ABI plugin {cls.plugin_id!r} declares entry_point "
                f"{declared_entry_point!r}, expected {actual_entry_point!r}"
            )

    @classmethod
    def _resolve_plugin_root(cls) -> Path:
        if cls.plugin_root is not None:
            return Path(cls.plugin_root)
        module = sys.modules.get(cls.__module__)
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise TypeError(
                f"ABI plugin {cls.__name__} cannot infer its plugin root; set plugin_root"
            )
        return Path(module_file).resolve().parent

    def registry(self) -> ToolRegistry:
        """Load the registry declared by the plugin manifest."""
        return ToolRegistry.from_path(self.root / str(self._manifest["tool_registry"]))

    def table_schemas(self) -> Mapping[str, Iterable[str]]:
        """Load standard table schemas declared by the plugin manifest."""
        path = self.root / str(self._manifest["standard_tables"])
        tables = load_yaml(path).get("tables")
        if not isinstance(tables, Mapping):
            raise ValueError(f"{path} must contain a tables mapping")
        return tables
