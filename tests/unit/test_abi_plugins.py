import inspect
from pathlib import Path

import pytest

import abi.plugins as plugin_registry
from abi.agent import ABIAgentInterface
from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract
from abi.tool_descriptors import ABI_AGENT_TOOLS, TOOL_ALIASES, export_openai_tools

FIXTURES = Path("tests/fixtures/tool_outputs")


def test_abi_lists_builtin_plugins():
    plugin_ids = {plugin.plugin_id for plugin in list_plugins()}

    assert "metagenomic_plasmid" in plugin_ids
    assert "metatranscriptomics" in plugin_ids


def test_metatranscriptomics_plan_uses_plugin_schema(tmp_path):
    plugin = get_plugin("metatranscriptomics")
    config = plugin.load_config(overrides={"outdir": str(tmp_path / "results")})

    plan = plugin.build_plan(config)

    assert plan.analysis_type == "metatranscriptomics"
    assert [step.tool_id for step in plan.steps] == ["fastp", "star", "featurecounts"]
    # DAG planner resolves genome_index from config resources into inputs
    assert "genome_index" in plan.steps[1].inputs
    assert "gene_expression" in plugin.table_schemas()
    assert Path(plan.outdir) == tmp_path / "results"


def test_metatranscriptomics_null_alignment_uses_default_aligner(tmp_path):
    plugin = get_plugin("metatranscriptomics")
    config = plugin.load_config(overrides={"outdir": str(tmp_path / "results"), "alignment": None})
    config["alignment"] = None

    plan = plugin.build_plan(config)

    assert plan.steps[1].tool_id == "star"


def test_metagenomic_plasmid_plugin_parses_standard_outputs():
    plugin = get_plugin("metagenomic_plasmid")

    rows = plugin.parse_outputs("genomad", FIXTURES / "genomad", "S1")

    assert rows["plasmid_predictions"]
    assert rows["plasmid_predictions"][0]["sample_id"] == "S1"
    assert rows["plasmid_predictions"][0]["tool"] == "genomad"


def test_builtin_plugins_satisfy_machine_contracts():
    for plugin_id in (
        "metatranscriptomics",
        "metagenomic_plasmid",
        "rnaseq_expression",
        "wgs_bacteria",
        "amplicon_16s",
    ):
        assert_plugin_contract(get_plugin(plugin_id))


def test_inline_plugins_implement_dry_run_protocol():
    from abi.interfaces import ABIDryRunPlugin

    for plugin_id in (
        "metatranscriptomics",
        "rnaseq_expression",
        "wgs_bacteria",
        "amplicon_16s",
    ):
        assert isinstance(get_plugin(plugin_id), ABIDryRunPlugin)


def test_metagenomic_plasmid_uses_plugin_local_registry():
    plugin = get_plugin("metagenomic_plasmid")

    registry = plugin.registry()

    assert registry.has("genomad")
    assert (plugin.root / "tool_registry.yaml").exists()


def test_metagenomic_plasmid_contracts_cover_every_registered_tool():
    plugin = get_plugin("metagenomic_plasmid")
    registry_ids = set(plugin.registry().ids())
    contract_ids = {path.stem for path in (plugin.root / "tool_contracts").glob("*.yaml")}

    assert registry_ids == contract_ids


def test_abi_discovers_entry_point_plugins(monkeypatch):
    class FakePlugin:
        plugin_id = "fake_analysis"
        display_name = "Fake Analysis"
        description = "Test-only plugin."
        report_title = "Fake Analysis Report"

        def load_config(self, config_path=None, *, profile=None, db_profile=None, overrides=None):
            return {}

        def build_plan(self, config, check_files=True):
            from abi.schemas import ExecutionPlan

            return ExecutionPlan(pipeline_id="fake", steps=[])

        def registry(self):
            from abi.tools import ToolRegistry

            return ToolRegistry({})

        def table_schemas(self):
            return {}

        def parse_outputs(self, tool_id, output_dir, sample_id):
            return {}

        def write_report(self, plan, result_dir):
            return {}

    class FakeEntryPoint:
        name = "fake_analysis"

        def load(self):
            return FakePlugin

    monkeypatch.setattr(plugin_registry, "_entry_points", lambda: [FakeEntryPoint()])

    assert get_plugin("fake_analysis").display_name == "Fake Analysis"
    plugin_ids = {plugin.plugin_id for plugin in list_plugins()}
    assert {"fake_analysis", "metagenomic_plasmid", "metatranscriptomics"} <= plugin_ids


def test_abi_skips_broken_entry_point_plugins(monkeypatch):
    class BrokenEntryPoint:
        name = "broken"

        def load(self):
            raise ImportError("broken import")

    monkeypatch.setattr(plugin_registry, "_entry_points", lambda: [BrokenEntryPoint()])

    with pytest.warns(RuntimeWarning, match="Skipping ABI plugin entry point"):
        plugin_ids = {plugin.plugin_id for plugin in list_plugins()}

    assert "broken" not in plugin_ids
    assert {"metagenomic_plasmid", "metatranscriptomics"} <= plugin_ids


def test_openai_tool_export_uses_agent_permissions_and_keeps_execution_opt_in():
    plugin = get_plugin("metagenomic_plasmid")

    tools = export_openai_tools(plugin, descriptor_format="responses")

    names = {tool["name"] for tool in tools}
    assert "abi_validate_result" in names
    assert "abi_export_agent_context" in names
    assert "abi_doctor_agent" in names
    assert "abi_run" not in names
    for tool in tools:
        assert tool["strict"] is True
        assert tool["parameters"]["additionalProperties"] is False

    apps_tools = export_openai_tools(plugin, descriptor_format="apps-sdk")
    apps_by_name = {tool["name"]: tool for tool in apps_tools}
    assert "abi_run" not in apps_by_name
    assert apps_by_name["abi_plan"]["inputSchema"]["additionalProperties"] is False
    assert apps_by_name["abi_inspect"]["annotations"]["readOnlyHint"] is True
    assert apps_by_name["abi_export_agent_context"]["annotations"]["readOnlyHint"] is True

    json_tools = export_openai_tools(
        plugin,
        descriptor_format="json",
        include_execution=True,
    )
    by_name = {tool["name"]: tool for tool in json_tools}
    assert by_name["abi_inspect"]["permission"] == "read_only"
    assert by_name["abi_report"]["permission"] == "planning_write"
    assert by_name["abi_run"]["permission"] == "execution"
    assert by_name["abi_run"]["requires_confirmation"] is True


def test_openai_tool_schemas_cover_agent_interface_parameters():
    # Build mapping from SSOT: only abi_* tool names that have corresponding
    # ABIAgentInterface methods (excludes legacy autoplasm alias).
    mapping = {
        name: TOOL_ALIASES[name]
        for name in ABI_AGENT_TOOLS
        if name in TOOL_ALIASES and not name.startswith("autoplasm")
    }

    for tool_name, method_name in mapping.items():
        signature = inspect.signature(getattr(ABIAgentInterface, method_name))
        method_params = {name for name in signature.parameters if name != "self"}
        schema_params = set(ABI_AGENT_TOOLS[tool_name]["properties"])

        assert method_params <= schema_params, tool_name
