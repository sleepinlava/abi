"""Tests for ToolCatalog — compilation, query, shadow comparison."""

from __future__ import annotations

from pathlib import Path

from abi.tool_catalog import (
    CatalogComparison,
    RuntimeToolDescriptor,
    ToolCatalog,
)
from abi.tools import ResourceSpec


class TestRuntimeToolDescriptor:
    def test_minimal_descriptor(self) -> None:
        d = RuntimeToolDescriptor(tool_id="test_tool")
        assert d.tool_id == "test_tool"
        assert d.name == ""
        assert d.env_name == ""

    def test_from_registry_entry(self) -> None:
        entry = {
            "id": "fastp",
            "name": "FastP QC",
            "category": "qc",
            "executable": "fastp",
            "command_template": "fastp -i {read1} -o {out}",
            "env_name": "",
            "container_image": "docker://example/fastp:v1",
            "resources": {"cpu": 4, "memory": "8GB"},
            "inputs": {"read1": {"type": "file"}},
            "outputs": {"clean_read1": {"type": "file"}},
            "default_enabled": True,
        }
        d = RuntimeToolDescriptor.from_registry_entry(
            "fastp", entry, plugin="metagenomic_plasmid", env_name="autoplasm-qc"
        )
        assert d.tool_id == "fastp"
        assert d.name == "FastP QC"
        assert d.category == "qc"
        assert d.plugin == "metagenomic_plasmid"
        assert d.executable == "fastp"
        assert d.env_name == "autoplasm-qc"
        assert d.container_image == "docker://example/fastp:v1"
        assert d.resources.cpu == 4
        assert d.resources.memory == "8GB"
        assert d.inputs == {"read1": {"type": "file"}}

    def test_from_registry_entry_none_container(self) -> None:
        d = RuntimeToolDescriptor.from_registry_entry(
            "t", {"id": "t"}, env_name="env"
        )
        assert d.container_image is None


class TestToolCatalog:
    def test_empty_catalog(self) -> None:
        c = ToolCatalog()
        assert len(c) == 0
        assert c.tool_ids() == []
        assert not c.has("x")

    def test_from_project_root(self) -> None:
        """Smoke test: catalog compiles from the real project root."""
        catalog = ToolCatalog.from_project_root()
        assert len(catalog) > 0
        # Check a known tool exists.
        assert catalog.has("fastp")
        fastp = catalog.get("fastp")
        assert fastp.tool_id == "fastp"
        assert fastp.name

    def test_shadow_comparison_per_plugin(self) -> None:
        """Compare catalog against per-plugin registries.

        The catalog compiles all plugins; ToolRegistry is per-plugin.
        Compare each plugin's registry against the catalog's view of it.
        """
        from abi.tools import ToolRegistry

        catalog = ToolCatalog.from_project_root()
        plugins_dir = Path(__file__).parent.parent.parent / "plugins"

        for plugin_dir in sorted(plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            reg_path = plugin_dir / "tool_registry.yaml"
            if not reg_path.exists():
                continue
            reg = ToolRegistry.from_path(reg_path)
            reg_ids = set(reg.ids() or ())

            # Every tool in this plugin's registry should be in the catalog.
            for tid in reg_ids:
                assert catalog.has(tid), f"Catalog missing {tid} from {plugin_dir.name}"


class TestCatalogComparison:
    def test_ok_when_no_differences(self) -> None:
        comp = CatalogComparison(total_tools=5, matched=5)
        assert comp.ok

    def test_not_ok_when_mismatches(self) -> None:
        comp = CatalogComparison(total_tools=5, matched=3, mismatched=["fastp"])
        assert not comp.ok

    def test_not_ok_when_tools_missing(self) -> None:
        comp = CatalogComparison(only_in_catalog=["new_tool"])
        assert not comp.ok
