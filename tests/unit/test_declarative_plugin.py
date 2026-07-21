from __future__ import annotations

from pathlib import Path

import pytest

import abi.plugins as plugin_registry
from abi.plugin import DeclarativeABIPlugin
from abi.plugins import list_plugins


def _write_plugin_files(root: Path, *, entry_point: str, plugin_id: str = "demo") -> None:
    (root / "tool_contracts").mkdir()
    (root / "abi-plugin.yaml").write_text(
        f"""
abi_version: "0.1"
plugin_id: {plugin_id}
display_name: Demo Plugin
description: Declarative test plugin.
report_title: Demo Report
plugin_type: adapter
entry_point: {entry_point}
tool_registry: tools.yaml
standard_tables: tables.yaml
tool_contracts: tool_contracts
""",
        encoding="utf-8",
    )
    (root / "tools.yaml").write_text(
        "tools:\n  - id: echo\n    executable: echo\n    command_template: echo {value}\n",
        encoding="utf-8",
    )
    (root / "tables.yaml").write_text(
        "tables:\n  results: [sample_id, value]\n",
        encoding="utf-8",
    )


def test_declarative_plugin_supplies_identity_registry_and_tables(tmp_path: Path) -> None:
    _write_plugin_files(tmp_path, entry_point=f"{__name__}:DemoPlugin")

    demo_plugin_class = type(
        "DemoPlugin",
        (DeclarativeABIPlugin,),
        {"plugin_root": tmp_path, "__module__": __name__},
    )

    plugin = demo_plugin_class()

    assert plugin.plugin_id == "demo"
    assert plugin.display_name == "Demo Plugin"
    assert plugin.registry().ids() == ["echo"]
    assert plugin.table_schemas() == {"results": ["sample_id", "value"]}


def test_declarative_plugin_rejects_mismatched_entry_point(tmp_path: Path) -> None:
    _write_plugin_files(tmp_path, entry_point="wrong.module:WrongPlugin")

    with pytest.raises(TypeError, match="declares entry_point"):

        class DemoPlugin(DeclarativeABIPlugin):
            plugin_root = tmp_path


def test_declarative_plugin_rejects_missing_declared_path(tmp_path: Path) -> None:
    _write_plugin_files(tmp_path, entry_point=f"{__name__}:DemoPlugin")
    (tmp_path / "tools.yaml").unlink()

    with pytest.raises(ValueError, match="missing manifest path"):

        class DemoPlugin(DeclarativeABIPlugin):
            plugin_root = tmp_path


def test_declarative_plugin_requires_report_title(tmp_path: Path) -> None:
    _write_plugin_files(tmp_path, entry_point=f"{__name__}:DemoPlugin")
    manifest_path = tmp_path / "abi-plugin.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace("report_title: Demo Report\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="report_title must be a non-empty string"):

        class DemoPlugin(DeclarativeABIPlugin):
            plugin_root = tmp_path


def test_discovery_rejects_entry_point_name_plugin_id_mismatch(monkeypatch) -> None:
    class MismatchedPlugin:
        plugin_id = "actual_name"
        display_name = "Mismatched"
        description = "Test-only plugin."
        report_title = "Mismatched Report"

        def load_config(self):
            return {}

        def build_plan(self):
            return None

        def registry(self):
            return None

        def table_schemas(self):
            return {}

        def parse_outputs(self):
            return {}

        def write_report(self):
            return {}

    class FakeEntryPoint:
        name = "declared_name"

        def load(self):
            return MismatchedPlugin

    monkeypatch.setattr(plugin_registry, "_entry_points", lambda: [FakeEntryPoint()])

    with pytest.warns(RuntimeWarning, match="plugin_id is 'actual_name'"):
        plugin_ids = {plugin.plugin_id for plugin in list_plugins()}

    assert "actual_name" not in plugin_ids
