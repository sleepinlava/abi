"""Integration coverage for compiling the catalog from all real plugins."""

from pathlib import Path

from abi.tool_catalog import ToolCatalog
from abi.tools import ToolRegistry


def test_real_plugin_registries_are_represented_in_catalog() -> None:
    project_root = Path(__file__).parents[2]
    catalog = ToolCatalog.from_project_root(project_root)

    assert catalog.has("fastp")
    for registry_path in sorted((project_root / "plugins").glob("*/tool_registry.yaml")):
        registry = ToolRegistry.from_path(registry_path)
        for tool_id in registry.ids() or ():
            assert catalog.get_qualified(registry_path.parent.name, tool_id)


def test_all_real_plugin_registries_match_compiled_catalog() -> None:
    project_root = Path(__file__).parents[2]
    for registry_path in sorted((project_root / "plugins").glob("*/tool_registry.yaml")):
        catalog = ToolCatalog.from_plugin_dir(registry_path.parent)
        comparison = catalog.compare_with_registry(ToolRegistry.from_path(registry_path))

        assert comparison.only_in_catalog == []
        assert comparison.only_in_registry == []
        assert comparison.mismatched == []
        assert comparison.errors == []
        assert comparison.matched == comparison.total_tools
