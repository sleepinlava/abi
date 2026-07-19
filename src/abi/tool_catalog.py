"""Tool Catalog — compiled RuntimeToolDescriptor and shadow comparison.

Design doc ref: §4.3 Tool Catalog, C07.

Compiles tool registry declarations, contracts, environment assignments, and
execution metadata into immutable ``RuntimeToolDescriptor`` values.  Runs in
shadow mode initially: compare catalog output against the current
``ToolRegistry`` results and report differences before making the catalog
authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Tuple

from abi.errors import ToolResolutionError
from abi.tools import ResourceSpec

__all__ = [
    "RuntimeToolDescriptor",
    "ToolCatalog",
    "ToolResolutionError",
    "CatalogComparison",
]


# ── Re-export for backward compatibility ─────────────────────────────────
# ToolResolutionError is now defined in abi.errors.  Importing from here
# still works (same class object).


@dataclass(frozen=True)
class RuntimeToolDescriptor:
    """Compiled, immutable descriptor for a single tool.

    All fields that were previously scattered across registry YAML,
    contract YAML, and ``environments.yaml`` are resolved into one
    frozen value.
    """

    tool_id: str
    name: str = ""
    category: str = ""
    plugin: str = ""

    # ── Execution ──
    executable: str = ""
    command_template: str = ""
    env_name: str = ""
    container_image: str | None = None

    # ── Resources ──
    resources: ResourceSpec = field(default_factory=ResourceSpec)

    # ── Metadata ──
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    default_enabled: bool = True
    execution_scope: str | None = None  # driver | worker | external

    @classmethod
    def from_registry_entry(
        cls,
        tool_id: str,
        registry_entry: Mapping[str, Any],
        *,
        plugin: str = "",
        env_name: str = "",
    ) -> RuntimeToolDescriptor:
        """Build from a single ``tool_registry.yaml`` entry."""
        meta = dict(registry_entry)
        return cls(
            tool_id=tool_id,
            name=str(meta.get("name", "")),
            category=str(meta.get("category", "")),
            plugin=plugin,
            executable=str(meta.get("executable", "")),
            command_template=str(meta.get("command_template", "")),
            env_name=env_name,
            container_image=_opt_str(meta.get("container_image")),
            resources=ResourceSpec.from_metadata(meta),
            inputs=_dict_field(meta, "inputs"),
            outputs=_dict_field(meta, "outputs"),
            execution=_dict_field(meta, "execution"),
            metadata=meta,
            default_enabled=bool(meta.get("default_enabled", True)),
            execution_scope=_opt_str(meta.get("execution_scope")),
        )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _dict_field(meta: Mapping[str, Any], key: str) -> Dict[str, Any]:
    val = meta.get(key)
    if isinstance(val, Mapping):
        return dict(val)
    return {}


# ── Catalog ──────────────────────────────────────────────────────────────────


@dataclass
class CatalogComparison:
    """Result of comparing the catalog against live ``ToolRegistry`` output."""

    total_tools: int = 0
    matched: int = 0
    mismatched: List[str] = field(default_factory=list)
    only_in_catalog: List[str] = field(default_factory=list)
    only_in_registry: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any((self.mismatched, self.only_in_catalog, self.only_in_registry, self.errors))


class ToolCatalog:
    """Compiled, queryable tool catalog.

    Built once from disk (registry YAML + authoritative tool contracts +
    ``environments.yaml``) and provides O(1) lookups via ``get()``.  When a
    registry entry and its contract overlap, the contract value is authoritative.

    Usage::

        catalog = ToolCatalog.from_project_root()
        desc = catalog.get("fastp")
        print(desc.env_name)  # "autoplasm-qc"
    """

    def __init__(self, descriptors: Iterator[RuntimeToolDescriptor] | None = None):
        self._by_tool_id: Dict[str, RuntimeToolDescriptor] = {}
        self._by_qualified: Dict[Tuple[str, str], RuntimeToolDescriptor] = {}
        if descriptors:
            self._add_all(descriptors)

    def _add_all(self, descriptors: Iterator[RuntimeToolDescriptor]) -> None:
        for d in descriptors:
            qualified = (d.plugin, d.tool_id)
            self._by_qualified[qualified] = d
            # Unqualified key: first-write-wins.  Later registrations
            # for the same tool_id (from other plugins) are silently skipped.
            self._by_tool_id.setdefault(d.tool_id, d)

    # ── Factory ──────────────────────────────────────────────────────────

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> ToolCatalog:
        """Compile the catalog from all plugins under *project_root*."""
        from abi.config import PROJECT_ROOT

        root = Path(project_root or PROJECT_ROOT).resolve()

        from abi.runtime_environment import load_environment_assignments

        environment_data = load_environment_assignments()
        raw_assignments = environment_data.get("tool_assignments", {})
        env_assignments = cls._normalise_env_assignments(raw_assignments)

        catalog = cls()
        for plugin_dir in sorted((root / "plugins").glob("*")):
            if not plugin_dir.is_dir():
                continue
            registry_path = plugin_dir / "tool_registry.yaml"
            contracts_dir = plugin_dir / "tool_contracts"
            if not registry_path.exists() and not contracts_dir.exists():
                continue
            plugin = plugin_dir.name
            descriptors = cls._compile_plugin(plugin_dir, plugin, env_assignments)
            catalog._add_all(descriptors)

        return catalog

    @classmethod
    def from_plugin_dir(
        cls,
        plugin_dir: str | Path,
        *,
        registry_path: str | Path | None = None,
    ) -> ToolCatalog:
        """Compile one plugin for compatibility adapters and isolated tests."""
        from abi.runtime_environment import load_environment_assignments

        path = Path(plugin_dir)
        environment_data = load_environment_assignments()
        raw_assignments = environment_data.get("tool_assignments", {})
        env_assignments = cls._normalise_env_assignments(raw_assignments)
        return cls(
            cls._compile_plugin(
                path,
                path.name,
                env_assignments,
                registry_path=Path(registry_path) if registry_path is not None else None,
            )
        )

    @classmethod
    def _normalise_env_assignments(cls, raw: Any) -> Dict[str, Dict[str, str]]:
        result: Dict[str, Dict[str, str]] = {}
        if not isinstance(raw, Mapping):
            return result
        for plugin, tools in raw.items():
            if isinstance(tools, Mapping):
                result[str(plugin)] = {str(k): str(v) for k, v in tools.items()}
        return result

    @classmethod
    def _compile_plugin(
        cls,
        plugin_dir: Path,
        plugin: str,
        env_assignments: Dict[str, Dict[str, str]],
        *,
        registry_path: Path | None = None,
    ) -> Iterator[RuntimeToolDescriptor]:
        import yaml

        manifest_path = plugin_dir / "abi-plugin.yaml"
        manifest = (
            yaml.safe_load(manifest_path.read_bytes()) or {} if manifest_path.exists() else {}
        )
        if registry_path is None:
            registry_name = str(manifest.get("tool_registry", "tool_registry.yaml"))
            registry_path = plugin_dir / registry_name
        data = yaml.safe_load(registry_path.read_bytes()) or {} if registry_path.exists() else {}
        tools = data.get("tools", [])
        plugin_envs = env_assignments.get(plugin, {})
        if not isinstance(tools, list):
            raise ToolResolutionError(f"{registry_path}: 'tools' must be a list")

        registry_entries: Dict[str, Dict[str, Any]] = {}
        for entry in tools:
            if not isinstance(entry, Mapping):
                continue
            tool_id = str(entry.get("id", "") or entry.get("tool_id", ""))
            if tool_id:
                if tool_id in registry_entries:
                    raise ToolResolutionError(
                        f"{registry_path}: duplicate registry entry for {tool_id!r}"
                    )
                registry_entries[tool_id] = dict(entry)

        contracts: Dict[str, Dict[str, Any]] = {}
        contracts_name = str(manifest.get("tool_contracts", "tool_contracts"))
        contracts_dir = plugin_dir / contracts_name
        if contracts_dir.exists():
            for path in sorted([*contracts_dir.glob("*.yaml"), *contracts_dir.glob("*.yml")]):
                contract = yaml.safe_load(path.read_bytes()) or {}
                if not isinstance(contract, Mapping):
                    raise ToolResolutionError(f"{path}: contract must be a mapping")
                tool_id = str(contract.get("tool_id", ""))
                if not tool_id:
                    raise ToolResolutionError(f"{path}: contract is missing tool_id")
                if path.stem != tool_id:
                    raise ToolResolutionError(
                        f"{path}: filename must match contract tool_id {tool_id!r}"
                    )
                if tool_id in contracts:
                    raise ToolResolutionError(f"Duplicate contract for {plugin}/{tool_id}")
                contracts[tool_id] = dict(contract)

        for tool_id in registry_entries.keys() | contracts.keys():
            entry = registry_entries.get(tool_id, {})
            contract = contracts.get(tool_id)
            merged = dict(entry)
            if contract is not None:
                # Tool contracts are the authoritative runtime declaration;
                # registry-only operational flags remain as fallbacks.
                merged.update(contract)
                execution = contract.get("execution")
                if isinstance(execution, Mapping):
                    for key in (
                        "executable",
                        "command_template",
                        "container_image",
                        "execution_scope",
                    ):
                        if key in execution:
                            merged[key] = execution[key]
                    merged["execution"] = dict(execution)
            env_name = str(merged.get("env_name", "") or plugin_envs.get(tool_id, ""))
            merged["id"] = tool_id
            if env_name:
                merged["env_name"] = env_name
            yield RuntimeToolDescriptor.from_registry_entry(
                tool_id, merged, plugin=plugin, env_name=env_name
            )

    # ── Query ────────────────────────────────────────────────────────────

    def get(self, tool_id: str) -> RuntimeToolDescriptor:
        """Return the descriptor for *tool_id* (first plugin match).

        Use :meth:`get_qualified` for a specific (plugin, tool_id) pair.
        """
        return self._by_tool_id[tool_id]

    def get_qualified(self, plugin: str, tool_id: str) -> RuntimeToolDescriptor:
        """Return the descriptor for a specific (plugin, tool_id) pair."""
        return self._by_qualified[(plugin, tool_id)]

    def has(self, tool_id: str) -> bool:
        return tool_id in self._by_tool_id

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._by_tool_id

    def __len__(self) -> int:
        return len(self._by_qualified)

    def __iter__(self) -> Iterator[RuntimeToolDescriptor]:
        return iter(self._by_qualified.values())

    def tool_ids(self) -> List[str]:
        return sorted(self._by_tool_id)

    def qualified_tool_ids(self) -> List[Tuple[str, str]]:
        return sorted(self._by_qualified)

    # ── Shadow comparison ────────────────────────────────────────────────

    def compare_with_registry(
        self,
        registry: Any,
    ) -> CatalogComparison:
        """Compare catalog output against a live ``ToolRegistry``.

        This is the shadow-mode gate: the catalog must agree with the
        current registry before it can become authoritative.
        """
        catalog_ids = set(self._by_tool_id)
        try:
            registry_ids = set(registry.ids() or ())
        except Exception:
            registry_ids = set()

        comp = CatalogComparison(
            total_tools=len(catalog_ids | registry_ids),
            matched=0,
        )
        comp.only_in_catalog = sorted(catalog_ids - registry_ids)
        comp.only_in_registry = sorted(registry_ids - catalog_ids)

        # Compare entries that exist in both.
        for tid in sorted(catalog_ids & registry_ids):
            cd = self._by_tool_id[tid]
            try:
                reg_entry = registry.get(tid)
            except Exception as exc:
                comp.errors.append(f"{tid}: registry.get() raised {exc}")
                continue

            diffs = self._diff(tid, cd, reg_entry)
            if diffs:
                comp.mismatched.append(f"{tid}: {diffs}")
            else:
                comp.matched += 1

        return comp

    def _diff(
        self,
        tool_id: str,
        cd: RuntimeToolDescriptor,
        reg_entry: Any,
    ) -> str | None:
        """Compare one catalog descriptor against a registry entry.

        Returns a human-readable diff string or ``None`` if they match.
        """
        parts: list[str] = []

        expected_env = cd.env_name or ""
        actual_env = str(
            (
                reg_entry.get("env_name", "")
                if isinstance(reg_entry, Mapping)
                else getattr(reg_entry, "env_name", "")
            )
            or ""
        )
        if expected_env != actual_env:
            parts.append(f"env_name({expected_env!r} vs {actual_env!r})")

        expected_exe = cd.executable
        if expected_exe:
            actual_exe = str(
                (
                    reg_entry.get("executable", "")
                    if isinstance(reg_entry, Mapping)
                    else getattr(reg_entry, "executable", "")
                )
                or ""
            )
            if expected_exe != actual_exe:
                parts.append(f"executable({expected_exe!r} vs {actual_exe!r})")

        return "; ".join(parts) if parts else None
