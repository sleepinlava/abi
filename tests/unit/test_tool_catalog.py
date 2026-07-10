"""Tests for ToolCatalog — compilation, query, shadow comparison."""

from __future__ import annotations

from pathlib import Path

import yaml

from abi.tool_catalog import (
    CatalogComparison,
    RuntimeToolDescriptor,
    ToolCatalog,
)
from abi.tools import ToolRegistry


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
        d = RuntimeToolDescriptor.from_registry_entry("t", {"id": "t"}, env_name="env")
        assert d.container_image is None


class TestToolCatalog:
    def test_empty_catalog(self) -> None:
        c = ToolCatalog()
        assert len(c) == 0
        assert c.tool_ids() == []
        assert not c.has("x")

    def test_from_project_root_merges_authoritative_contract(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        plugin = tmp_path / "plugins" / "demo"
        contracts = plugin / "tool_contracts"
        contracts.mkdir(parents=True)
        (plugin / "tool_registry.yaml").write_text(
            yaml.safe_dump(
                {
                    "tools": [
                        {
                            "id": "aligner",
                            "name": "Registry Name",
                            "executable": "old-aligner",
                            "inputs": ["reads"],
                            "resources": {"cpu": 1, "memory": "1GB"},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (contracts / "aligner.yaml").write_text(
            yaml.safe_dump(
                {
                    "tool_id": "aligner",
                    "name": "Contract Name",
                    "inputs": {"reads": {"type": "file", "required": True}},
                    "outputs": {"bam": {"type": "file"}},
                    "resources": {"cpu": 8, "memory": "16GB"},
                    "execution": {
                        "executable": "new-aligner",
                        "command_template": "new-aligner {reads} -o {bam}",
                        "network": False,
                        "writes_output": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "abi.runtime_environment.load_environment_assignments",
            lambda: {"tool_assignments": {"demo": {"aligner": "demo-env"}}},
        )

        descriptor = ToolCatalog.from_project_root(tmp_path).get("aligner")

        assert descriptor.name == "Contract Name"
        assert descriptor.executable == "new-aligner"
        assert descriptor.command_template == "new-aligner {reads} -o {bam}"
        assert descriptor.env_name == "demo-env"
        assert descriptor.resources.cpu == 8
        assert descriptor.inputs["reads"]["required"] is True
        assert descriptor.outputs == {"bam": {"type": "file"}}
        assert descriptor.execution == {
            "executable": "new-aligner",
            "command_template": "new-aligner {reads} -o {bam}",
            "network": False,
            "writes_output": True,
        }

    def test_tool_registry_uses_catalog_merged_contract(self, tmp_path: Path, monkeypatch) -> None:
        plugin = tmp_path / "plugins" / "demo"
        contracts = plugin / "tool_contracts"
        contracts.mkdir(parents=True)
        (plugin / "tool_registry.yaml").write_text(
            yaml.safe_dump(
                {
                    "tools": [
                        {
                            "id": "aligner",
                            "executable": "old-aligner",
                            "resources": {"cpu": 1, "memory": "1GB"},
                            "output_dir_policy": "must_not_exist",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (contracts / "aligner.yaml").write_text(
            yaml.safe_dump(
                {
                    "tool_id": "aligner",
                    "resources": {"cpu": 8, "memory": "16GB"},
                    "execution": {
                        "executable": "new-aligner",
                        "command_template": "new-aligner {input}",
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "abi.runtime_environment.load_environment_assignments",
            lambda: {"tool_assignments": {"demo": {"aligner": "demo-env"}}},
        )

        metadata = ToolRegistry.from_path(plugin / "tool_registry.yaml").get("aligner")

        assert metadata["resources"] == {"cpu": 8, "memory": "16GB"}
        assert metadata["executable"] == "new-aligner"
        assert metadata["command_template"] == "new-aligner {input}"
        assert metadata["env_name"] == "demo-env"
        assert metadata["output_dir_policy"] == "must_not_exist"


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
