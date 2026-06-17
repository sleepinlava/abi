"""Tests for the metatranscriptomics plugin."""

from __future__ import annotations

from pathlib import Path

from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract

_FIXTURES = Path("tests/fixtures/tool_outputs")


def test_plugin_registered():
    plugins = list_plugins()
    ids = [p.plugin_id for p in plugins]
    assert "metatranscriptomics" in ids


def test_get_plugin():
    plugin = get_plugin("metatranscriptomics")
    assert plugin.plugin_id == "metatranscriptomics"
    assert plugin.display_name == "Metatranscriptomics Demo"


def test_table_schemas():
    plugin = get_plugin("metatranscriptomics")
    schemas = plugin.table_schemas()
    assert "gene_expression" in schemas
    assert "qc_summary" in schemas
    assert "alignment_summary" in schemas


def test_registry():
    plugin = get_plugin("metatranscriptomics")
    registry = plugin.registry()
    assert registry.has("fastp")
    assert registry.has("star")
    assert registry.has("featurecounts")


def test_load_config():
    plugin = get_plugin("metatranscriptomics")
    cfg = plugin.load_config()
    assert cfg["project_name"] == "abi_metatranscriptomics_demo"
    assert cfg["threads"] == 4
    assert Path(cfg["input"]["sample_sheet"]).exists()


def test_default_sample_sheet_resolves_outside_project_cwd(tmp_path, monkeypatch):
    plugin = get_plugin("metatranscriptomics")
    monkeypatch.chdir(tmp_path)

    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results")})
    plan = plugin.build_plan(cfg)

    assert Path(plan.samples[0].read1).exists()
    assert Path(plan.samples[0].read2).exists()


def test_plugin_contract():
    plugin = get_plugin("metatranscriptomics")
    assert_plugin_contract(plugin)


def test_registry_uses_abi_environment_names():
    plugin = get_plugin("metatranscriptomics")
    env_names = {tool["env_name"] for tool in plugin.registry().list_tools()}
    assert env_names == {"abi-qc", "abi-stats"}


# ── Parser tests ──────────────────────────────────────────────────────────


def test_parse_fastp_shared():
    """fastp parser (imported from abi._shared) → qc_summary."""
    plugin = get_plugin("metatranscriptomics")
    result = plugin.parse_outputs("fastp", _FIXTURES / "fastp", "S1")
    rows = result["qc_summary"]
    assert len(rows) >= 4
    assert all(r["tool"] == "fastp" for r in rows)


def test_parse_star_shared():
    """STAR parser (imported from abi._shared) → alignment_summary."""
    plugin = get_plugin("metatranscriptomics")
    result = plugin.parse_outputs("star", _FIXTURES / "star", "S1")
    rows = result["alignment_summary"]
    assert len(rows) >= 20
    assert all(r["tool"] == "star" for r in rows)


def test_parse_outputs_unknown():
    plugin = get_plugin("metatranscriptomics")
    assert plugin.parse_outputs("nonexistent", Path("/tmp"), "S1") == {}
