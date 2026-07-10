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
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

from abi.tools import ResourceSpec

__all__ = [
    "RuntimeToolDescriptor",
    "ToolCatalog",
    "ToolResolutionError",
    "CatalogComparison",
]


class ToolResolutionError(ValueError):
    """A tool could not be resolved during catalog compilation."""


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
        return not any(
            (self.mismatched, self.only_in_catalog, self.only_in_registry, self.errors)
        )


class ToolCatalog:
    """Compiled, queryable tool catalog.

    Built once from disk (registry YAML + ``environments.yaml``) and
    provides O(1) lookups via ``get()``.

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

        env_assignments = cls._load_env_assignments(root)

        catalog = cls()
        for plugin_dir in sorted((root / "plugins").glob("*")):
            if not plugin_dir.is_dir():
                continue
            registry_path = plugin_dir / "tool_registry.yaml"
            if not registry_path.exists():
                continue
            plugin = plugin_dir.name
            descriptors = cls._compile_plugin(registry_path, plugin, env_assignments)
            catalog._add_all(descriptors)

        return catalog

    @classmethod
    def _load_env_assignments(cls, project_root: Path) -> Dict[str, Dict[str, str]]:
        import yaml

        env_path = project_root / "environments.yaml"
        if not env_path.exists():
            return {}
        data = yaml.safe_load(env_path.read_bytes()) or {}
        raw = data.get("tool_assignments", {})
        result: Dict[str, Dict[str, str]] = {}
        for plugin, tools in raw.items():
            if isinstance(tools, Mapping):
                result[str(plugin)] = {str(k): str(v) for k, v in tools.items()}
        return result

    @classmethod
    def _compile_plugin(
        cls,
        registry_path: Path,
        plugin: str,
        env_assignments: Dict[str, Dict[str, str]],
    ) -> Iterator[RuntimeToolDescriptor]:
        import yaml

        data = yaml.safe_load(registry_path.read_bytes()) or {}
        tools = data.get("tools", [])
        plugin_envs = env_assignments.get(plugin, {})
        if not isinstance(tools, list):
            return

        for entry in tools:
            if not isinstance(entry, Mapping):
                continue
            tool_id = str(entry.get("id", "") or entry.get("tool_id", ""))
            if not tool_id:
                continue
            env_name = str(entry.get("env_name", "") or plugin_envs.get(tool_id, ""))
            yield RuntimeToolDescriptor.from_registry_entry(
                tool_id, entry, plugin=plugin, env_name=env_name
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
        actual_env = str(getattr(reg_entry, "env_name", "") or "")
        if expected_env != actual_env:
            parts.append(f"env_name({expected_env!r} vs {actual_env!r})")

        expected_exe = cd.executable
        if expected_exe:
            actual_exe = str(getattr(reg_entry, "executable", "") or "")
            if expected_exe != actual_exe:
                parts.append(f"executable({expected_exe!r} vs {actual_exe!r})")

        return "; ".join(parts) if parts else None
