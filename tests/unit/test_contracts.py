"""Comprehensive unit tests for abi.contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from abi.contracts import (
    ContractValidationError,
    WorkflowSpec,
    _normalize_template,
    _require_mapping,
    _require_non_empty_string,
    _require_string_list,
    _template_fields,
    _validate_contract_matches_registry,
    _validate_declared_tables,
    _validate_manifest,
    _validate_resources_block,
    _validate_workflow_section,
    load_plugin_manifest,
    load_tool_contracts,
    load_workflow_spec,
    validate_plugin_contract_files,
    validate_tool_contract,
)

# ====== YAML Constants ======

MANIFEST_YAML = """abi_version: "0.1"
plugin_id: test_plugin
display_name: "Test Plugin"
description: "For unit testing"
plugin_type: standalone
entry_point: abi.plugins.test:TestPlugin
tool_registry: tool_registry.yaml
standard_tables: standard_tables.yaml
tool_contracts: tool_contracts
core_contracts: [test_tool]
"""

STANDARD_TABLES_YAML = """tables:
  test_table:
    - col_a
    - col_b
"""

TOOL_CONTRACT_YAML = """abi_version: "0.1"
tool_id: test_tool
name: Test Tool
category: qc
purpose: Unit testing
inputs:
  input_file:
    type: file
    format: txt
outputs:
  output_file:
    type: file
    format: txt
execution:
  executable: test_tool
  command_template: test_tool -i {input_file} -o {output_file}
  network: false
  writes_output: true
failure_handling:
  missing_input:
    hint: Check input
"""

TOOL_REGISTRY_YAML = """tools:
  - id: test_tool
    name: Test Tool
    executable: test_tool
    command_template: "test_tool -i {input_file} -o {output_file}"
    category: qc
    inputs: [input_file]
    outputs: [output_file]
"""


# ====== Helpers ======


def _make_plugin_dir(
    tmp_path,
    manifest_content=None,
    tables_content=None,
    contracts_content=None,
    registry_content=None,
):
    root = tmp_path / "test_plugin"
    root.mkdir()
    if manifest_content is None:
        manifest_content = MANIFEST_YAML
    (root / "abi-plugin.yaml").write_text(manifest_content)
    if tables_content is None:
        tables_content = STANDARD_TABLES_YAML
    (root / "standard_tables.yaml").write_text(tables_content)
    if registry_content is None:
        registry_content = TOOL_REGISTRY_YAML
    (root / "tool_registry.yaml").write_text(registry_content)
    contracts_dir = root / "tool_contracts"
    contracts_dir.mkdir()
    if contracts_content is None:
        contracts_content = {"test_tool": TOOL_CONTRACT_YAML}
    for name, cnt in contracts_content.items():
        (contracts_dir / f"{name}.yaml").write_text(cnt)
    return root


def _make_contract(**overrides):
    c = {
        "abi_version": "0.1",
        "tool_id": "my_tool",
        "name": "My Tool",
        "category": "qc",
        "purpose": "Test",
        "inputs": {"in": {"type": "file"}},
        "outputs": {"out": {"type": "file"}},
        "execution": {
            "executable": "my_tool",
            "command_template": "my_tool {in}",
        },
        "failure_handling": {"err": {"hint": "Fix it"}},
    }
    c.update(overrides)
    return c


class _FakePlugin:
    """Minimal fake plugin."""

    def __init__(self, plugin_id="test_plugin", root=None, registry=None, tables=None):
        self.plugin_id = plugin_id
        self._root = root
        self._registry = registry
        self._tables = tables or {}

    @property
    def root(self):
        return self._root

    def registry(self):
        return self._registry

    def table_schemas(self):
        return self._tables


class _FakeRegistry:
    def __init__(self, tools):
        self._tools = tools

    def list_tools(self):
        return self._tools


# ====== Tests: _require_mapping ======


class TestRequireMapping:
    def test_valid_mapping_returns_value(self):
        d = {"a": 1}
        assert _require_mapping(d, "test") is d

    def test_none_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty mapping"):
            _require_mapping(None, "test")

    def test_empty_dict_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty mapping"):
            _require_mapping({}, "test")

    def test_string_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty mapping"):
            _require_mapping("not a mapping", "test")

    def test_list_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty mapping"):
            _require_mapping([1, 2, 3], "test")

    def test_label_in_error_message(self):
        with pytest.raises(ContractValidationError, match="inputs must be"):
            _require_mapping({}, "inputs")


# ====== Tests: _require_non_empty_string ======


class TestRequireNonEmptyString:
    def test_valid_string_passes(self):
        _require_non_empty_string("hello", "test")

    def test_empty_string_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty string"):
            _require_non_empty_string("", "test")

    def test_whitespace_only_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty string"):
            _require_non_empty_string("   ", "test")

    def test_none_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty string"):
            _require_non_empty_string(None, "test")

    def test_int_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty string"):
            _require_non_empty_string(42, "test")

    def test_list_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty string"):
            _require_non_empty_string([], "test")

    def test_label_in_error_message(self):
        with pytest.raises(ContractValidationError, match="tool_id must be"):
            _require_non_empty_string("", "tool_id")


# ====== Tests: _require_string_list ======


class TestRequireStringList:
    def test_valid_list_passes(self):
        _require_string_list(["a", "b"], "test")

    def test_empty_list_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty list"):
            _require_string_list([], "test")

    def test_none_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty list"):
            _require_string_list(None, "test")

    def test_not_a_list_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty list"):
            _require_string_list("not a list", "test")

    def test_list_with_empty_string_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty strings"):
            _require_string_list(["a", ""], "test")

    def test_list_with_whitespace_str_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty strings"):
            _require_string_list(["a", "   "], "test")

    def test_list_with_non_string_raises(self):
        with pytest.raises(ContractValidationError, match="non-empty strings"):
            _require_string_list(["a", 123], "test")

    def test_label_in_error_message(self):
        with pytest.raises(ContractValidationError, match="when_to_use entries"):
            _require_string_list(["a", ""], "when_to_use")


# ====== Tests: _template_fields ======


class TestTemplateFields:
    def test_simple_braces_field(self):
        assert _template_fields("{input_file}") == ["input_file"]

    def test_dotted_field(self):
        assert _template_fields("{a.b}") == ["a"]

    def test_indexed_field(self):
        assert _template_fields("{a[0]}") == ["a"]

    def test_multiple_distinct_fields(self):
        result = _template_fields("{input_file} {output_file} {input_file}")
        assert sorted(result) == ["input_file", "output_file"]

    def test_no_braces_returns_empty(self):
        assert _template_fields("no braces here") == []

    def test_empty_string_returns_empty(self):
        assert _template_fields("") == []

    def test_mixed_plain_and_braces(self):
        result = _template_fields("echo {x} {y} hello")
        assert sorted(result) == ["x", "y"]

    def test_nested_field_top_level(self):
        assert _template_fields("{a.b.c}") == ["a"]

    def test_indexed_and_dotted(self):
        assert _template_fields("{a[0].b}") == ["a"]


# ====== Tests: _normalize_template ======


class TestNormalizeTemplate:
    def test_collapses_extra_spaces(self):
        assert _normalize_template("a   b   c") == "a b c"

    def test_handles_newlines(self):
        assert _normalize_template("a\nb\tc") == "a b c"

    def test_preserves_field_braces(self):
        assert _normalize_template("tool  {input}  {output}") == "tool {input} {output}"

    def test_no_extra_spaces_already_normalized(self):
        assert _normalize_template("tool -i {in}") == "tool -i {in}"

    def test_empty_string(self):
        assert _normalize_template("") == ""

    def test_whitespace_only(self):
        assert _normalize_template("   ") == ""


# ====== Tests: validate_tool_contract ======


class TestValidateToolContract:
    # -- happy path --

    def test_valid_contract_passes(self):
        validate_tool_contract(_make_contract())

    def test_valid_contract_with_path_label(self):
        validate_tool_contract(_make_contract(), path=Path("/tmp/tools/my_tool.yaml"))

    def test_optional_network_missing_is_ok(self):
        c = _make_contract()
        assert "network" not in c["execution"]
        validate_tool_contract(c)

    def test_optional_writes_output_missing_is_ok(self):
        c = _make_contract()
        assert "writes_output" not in c["execution"]
        validate_tool_contract(c)

    def test_optional_env_name_missing_is_ok(self):
        c = _make_contract()
        validate_tool_contract(c)

    def test_optional_env_name_string_is_ok(self):
        c = _make_contract()
        c["execution"]["env_name"] = "my_env"
        validate_tool_contract(c)

    def test_optional_resources_block_passes(self):
        c = _make_contract()
        c["resources"] = {"cpu": 4, "memory": "8G", "walltime": "01:00:00"}
        validate_tool_contract(c)

    def test_normalization_with_tables_passes(self):
        c = _make_contract()
        c["normalization"] = {"tables": ["t1", "t2"]}
        validate_tool_contract(c)

    def test_when_to_use_valid_list_passes(self):
        c = _make_contract()
        c["when_to_use"] = ["when data is large", "when paired-end"]
        validate_tool_contract(c)

    # -- missing required fields --

    @pytest.mark.parametrize(
        "field",
        [
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
    )
    def test_missing_required_field_raises(self, field):
        c = _make_contract()
        del c[field]
        with pytest.raises(ContractValidationError, match=f"missing required field {field!r}"):
            validate_tool_contract(c)

    # -- unknown fields --

    def test_unknown_field_raises(self):
        c = _make_contract()
        c["bogus_field"] = 123
        with pytest.raises(ContractValidationError, match="unknown contract fields"):
            validate_tool_contract(c)

    # -- non-string string fields --

    @pytest.mark.parametrize("field", ["abi_version", "tool_id", "name", "category", "purpose"])
    def test_string_field_none_raises(self, field):
        c = _make_contract()
        c[field] = None
        with pytest.raises(ContractValidationError, match="non-empty string"):
            validate_tool_contract(c)

    @pytest.mark.parametrize("field", ["abi_version", "tool_id", "name", "category", "purpose"])
    def test_string_field_empty_raises(self, field):
        c = _make_contract()
        c[field] = ""
        with pytest.raises(ContractValidationError, match="non-empty string"):
            validate_tool_contract(c)

    # -- inputs / outputs not mapping --

    def test_inputs_not_mapping_raises(self):
        c = _make_contract()
        c["inputs"] = "not a mapping"
        with pytest.raises(ContractValidationError, match="inputs must be a non-empty mapping"):
            validate_tool_contract(c)

    def test_outputs_not_mapping_raises(self):
        c = _make_contract()
        c["outputs"] = "not a mapping"
        with pytest.raises(ContractValidationError, match="outputs must be a non-empty mapping"):
            validate_tool_contract(c)

    def test_inputs_empty_mapping_raises(self):
        c = _make_contract()
        c["inputs"] = {}
        with pytest.raises(ContractValidationError, match="inputs must be a non-empty mapping"):
            validate_tool_contract(c)

    # -- execution missing sub-fields --

    def test_execution_missing_executable_raises(self):
        c = _make_contract()
        del c["execution"]["executable"]
        with pytest.raises(ContractValidationError, match="execution.executable"):
            validate_tool_contract(c)

    def test_execution_missing_command_template_raises(self):
        c = _make_contract()
        del c["execution"]["command_template"]
        with pytest.raises(ContractValidationError, match="execution.command_template"):
            validate_tool_contract(c)

    # -- execution type checks --

    def test_execution_network_not_boolean_raises(self):
        c = _make_contract()
        c["execution"]["network"] = "yes"
        with pytest.raises(ContractValidationError, match="execution.network must be boolean"):
            validate_tool_contract(c)

    def test_execution_writes_output_not_boolean_raises(self):
        c = _make_contract()
        c["execution"]["writes_output"] = "yes"
        with pytest.raises(
            ContractValidationError, match="execution.writes_output must be boolean"
        ):
            validate_tool_contract(c)

    def test_execution_env_name_not_string_raises(self):
        c = _make_contract()
        c["execution"]["env_name"] = 42
        with pytest.raises(ContractValidationError, match="execution.env_name must be string"):
            validate_tool_contract(c)

    # -- when_to_use --

    def test_when_to_use_not_list_raises(self):
        c = _make_contract()
        c["when_to_use"] = "not a list"
        with pytest.raises(ContractValidationError, match="when_to_use must be a non-empty list"):
            validate_tool_contract(c)

    def test_when_to_use_empty_strings_raises(self):
        c = _make_contract()
        c["when_to_use"] = ["ok", ""]
        with pytest.raises(ContractValidationError, match="when_to_use entries"):
            validate_tool_contract(c)

    # -- normalization --

    def test_normalization_tables_not_list_raises(self):
        c = _make_contract()
        c["normalization"] = {"tables": "not a list"}
        with pytest.raises(ContractValidationError, match="normalization.tables"):
            validate_tool_contract(c)

    # -- failure_handling --

    def test_failure_handling_not_mapping_raises(self):
        c = _make_contract()
        c["failure_handling"] = "not a mapping"
        with pytest.raises(ContractValidationError, match="failure_handling must be"):
            validate_tool_contract(c)

    def test_failure_handling_entry_missing_hint_raises(self):
        c = _make_contract()
        c["failure_handling"] = {"err": {"no_hint_here": True}}
        with pytest.raises(ContractValidationError, match="err.hint"):
            validate_tool_contract(c)

    def test_failure_handling_empty_raises(self):
        c = _make_contract()
        c["failure_handling"] = {}
        with pytest.raises(ContractValidationError, match="failure_handling must be"):
            validate_tool_contract(c)

    # -- resources --

    def test_resources_cpu_negative_raises(self):
        c = _make_contract()
        c["resources"] = {"cpu": -1}
        with pytest.raises(ContractValidationError, match="resources.cpu must be a positive"):
            validate_tool_contract(c)

    def test_resources_cpu_zero_raises(self):
        c = _make_contract()
        c["resources"] = {"cpu": 0}
        with pytest.raises(ContractValidationError, match="resources.cpu must be a positive"):
            validate_tool_contract(c)

    def test_resources_cpu_not_int_raises(self):
        c = _make_contract()
        c["resources"] = {"cpu": "many"}
        with pytest.raises(ContractValidationError, match="resources.cpu must be a positive"):
            validate_tool_contract(c)

    def test_resources_memory_empty_string_raises(self):
        c = _make_contract()
        c["resources"] = {"memory": ""}
        with pytest.raises(ContractValidationError, match="resources.memory must be a non-empty"):
            validate_tool_contract(c)

    def test_resources_walltime_empty_string_raises(self):
        c = _make_contract()
        c["resources"] = {"walltime": ""}
        with pytest.raises(ContractValidationError, match="resources.walltime must be a non-empty"):
            validate_tool_contract(c)

    def test_resources_accelerator_not_string_raises(self):
        c = _make_contract()
        c["resources"] = {"accelerator": 4}
        with pytest.raises(ContractValidationError, match="resources.accelerator must be a string"):
            validate_tool_contract(c)

    def test_resources_disk_not_string_raises(self):
        c = _make_contract()
        c["resources"] = {"disk": 100}
        with pytest.raises(ContractValidationError, match="resources.disk must be a string"):
            validate_tool_contract(c)

    def test_resources_not_mapping_raises(self):
        c = _make_contract()
        c["resources"] = "not mapping"
        with pytest.raises(ContractValidationError, match="resources must be"):
            validate_tool_contract(c)


# ====== Tests: _validate_resources_block ======


class TestValidateResourcesBlock:
    def test_valid_resources_passes(self):
        _validate_resources_block({"cpu": 8, "memory": "32G", "walltime": "24:00:00"}, "tool")

    def test_valid_with_accelerator_and_disk(self):
        _validate_resources_block(
            {
                "cpu": 1,
                "memory": "4G",
                "walltime": "01:00:00",
                "accelerator": "gpu",
                "disk": "50G",
            },
            "tool",
        )

    def test_cpu_must_be_positive_int(self):
        with pytest.raises(ContractValidationError, match="positive integer"):
            _validate_resources_block(
                {"cpu": 0, "memory": "4G", "walltime": "01:00"},
                "tool",
            )

    def test_memory_must_be_non_empty_string(self):
        with pytest.raises(ContractValidationError, match="memory must be a non-empty"):
            _validate_resources_block(
                {"cpu": 1, "memory": "", "walltime": "01:00"},
                "tool",
            )

    def test_walltime_must_be_non_empty_string(self):
        with pytest.raises(ContractValidationError, match="walltime must be a non-empty"):
            _validate_resources_block(
                {"cpu": 1, "memory": "4G", "walltime": ""},
                "tool",
            )

    def test_accelerator_must_be_string(self):
        with pytest.raises(ContractValidationError, match="accelerator must be a string"):
            _validate_resources_block(
                {"cpu": 1, "memory": "4G", "walltime": "01:00", "accelerator": 8},
                "tool",
            )

    def test_disk_must_be_string(self):
        with pytest.raises(ContractValidationError, match="disk must be a string"):
            _validate_resources_block(
                {"cpu": 1, "memory": "4G", "walltime": "01:00", "disk": 100},
                "tool",
            )

    def test_missing_cpu_is_ok(self):
        _validate_resources_block({"memory": "4G", "walltime": "01:00"}, "tool")

    def test_missing_accelerator_is_ok(self):
        _validate_resources_block({"cpu": 1, "memory": "4G", "walltime": "01:00"}, "tool")

    def test_missing_disk_is_ok(self):
        _validate_resources_block({"cpu": 1, "memory": "4G", "walltime": "01:00"}, "tool")


# ====== Tests: _validate_manifest ======


class TestValidateManifest:
    @staticmethod
    def _base_manifest():
        return {
            "abi_version": "0.1",
            "plugin_id": "test_plugin",
            "display_name": "TP",
            "description": "d",
            "plugin_type": "standalone",
            "entry_point": "mod:class",
            "tool_registry": "tool_registry.yaml",
            "standard_tables": "standard_tables.yaml",
            "tool_contracts": "tool_contracts",
            "core_contracts": ["test_tool"],
        }

    def test_valid_manifest_passes(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        plugin = _FakePlugin(root=str(root))
        _validate_manifest(plugin, root, manifest)

    @pytest.mark.parametrize(
        "field",
        [
            "abi_version",
            "plugin_id",
            "display_name",
            "description",
            "plugin_type",
            "entry_point",
            "tool_registry",
            "standard_tables",
            "tool_contracts",
        ],
    )
    def test_missing_required_field_raises(self, tmp_path, field):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        del manifest[field]
        plugin = _FakePlugin(root=str(root))
        with pytest.raises(ContractValidationError, match=f"{field}"):
            _validate_manifest(plugin, root, manifest)

    def test_plugin_id_mismatch_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        manifest["plugin_id"] = "wrong_id"
        plugin = _FakePlugin(root=str(root))
        with pytest.raises(ContractValidationError, match="manifest plugin_id"):
            _validate_manifest(plugin, root, manifest)

    @pytest.mark.parametrize("key", ["tool_registry", "standard_tables", "tool_contracts"])
    def test_declared_file_does_not_exist_raises(self, tmp_path, key):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        manifest[key] = "nonexistent.yaml"
        plugin = _FakePlugin(root=str(root))
        with pytest.raises(ContractValidationError, match="missing manifest path"):
            _validate_manifest(plugin, root, manifest)

    def test_core_contracts_not_list_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        manifest["core_contracts"] = "not a list"
        plugin = _FakePlugin(root=str(root))
        with pytest.raises(ContractValidationError, match="core_contracts"):
            _validate_manifest(plugin, root, manifest)

    def test_core_contracts_empty_list_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        manifest["core_contracts"] = []
        plugin = _FakePlugin(root=str(root))
        with pytest.raises(ContractValidationError, match="core_contracts"):
            _validate_manifest(plugin, root, manifest)

    def test_workflow_section_valid_passes(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        manifest = self._base_manifest()
        manifest["workflow"] = {
            "name": "Test WF",
            "steps": [{"id": "s1", "tool": "test_tool"}],
        }
        plugin = _FakePlugin(root=str(root))
        _validate_manifest(plugin, root, manifest)


# ====== Tests: _validate_workflow_section ======


class TestValidateWorkflowSection:
    @staticmethod
    def _valid(**overrides):
        d = {
            "name": "Standard Pipeline",
            "steps": [
                {"id": "qc", "tool": "fastqc"},
                {"id": "trim", "tool": "trimmomatic", "after": ["qc"]},
            ],
        }
        d.update(overrides)
        return d

    def test_valid_workflow_passes(self):
        _validate_workflow_section(self._valid(), "p", "/root")

    def test_missing_name_raises(self):
        wf = self._valid()
        del wf["name"]
        with pytest.raises(ContractValidationError, match="workflow.name"):
            _validate_workflow_section(wf, "p", "/root")

    def test_missing_steps_raises(self):
        wf = self._valid()
        del wf["steps"]
        with pytest.raises(ContractValidationError, match="non-empty list"):
            _validate_workflow_section(wf, "p", "/root")

    def test_empty_steps_raises(self):
        wf = self._valid()
        wf["steps"] = []
        with pytest.raises(ContractValidationError, match="non-empty list"):
            _validate_workflow_section(wf, "p", "/root")

    def test_step_not_mapping_raises(self):
        wf = self._valid()
        wf["steps"] = ["not a mapping"]
        with pytest.raises(ContractValidationError, match=r"steps\[0\] must be a mapping"):
            _validate_workflow_section(wf, "p", "/root")

    def test_step_missing_id_raises(self):
        wf = self._valid()
        wf["steps"] = [{"tool": "x"}]
        with pytest.raises(ContractValidationError, match=r"steps\[0\].id"):
            _validate_workflow_section(wf, "p", "/root")

    def test_step_missing_tool_raises(self):
        wf = self._valid()
        wf["steps"] = [{"id": "x"}]
        with pytest.raises(ContractValidationError, match=r"steps\[0\].tool"):
            _validate_workflow_section(wf, "p", "/root")

    def test_duplicate_step_id_raises(self):
        wf = self._valid()
        wf["steps"] = [
            {"id": "qc", "tool": "fastqc"},
            {"id": "qc", "tool": "fastqc2"},
        ]
        with pytest.raises(ContractValidationError, match="duplicate step id"):
            _validate_workflow_section(wf, "p", "/root")

    def test_after_not_list_raises(self):
        wf = self._valid()
        wf["steps"] = [{"id": "qc", "tool": "fastqc", "after": "qc"}]
        with pytest.raises(ContractValidationError, match="after must be a list"):
            _validate_workflow_section(wf, "p", "/root")

    def test_after_references_undeclared_step_raises(self):
        wf = self._valid()
        wf["steps"] = [
            {"id": "trim", "tool": "trimmomatic", "after": ["qc"]},
            {"id": "qc", "tool": "fastqc"},
        ]
        with pytest.raises(ContractValidationError, match="not declared before"):
            _validate_workflow_section(wf, "p", "/root")

    def test_optional_not_boolean_raises(self):
        wf = self._valid()
        wf["steps"] = [{"id": "qc", "tool": "fastqc", "optional": "yes"}]
        with pytest.raises(ContractValidationError, match="optional must be a boolean"):
            _validate_workflow_section(wf, "p", "/root")

    def test_citation_not_string_raises(self):
        wf = self._valid()
        wf["steps"] = [{"id": "qc", "tool": "fastqc", "citation": 42}]
        with pytest.raises(ContractValidationError, match="citation must be a string"):
            _validate_workflow_section(wf, "p", "/root")

    def test_citation_none_is_ok(self):
        wf = self._valid()
        wf["steps"] = [{"id": "qc", "tool": "fastqc", "citation": None}]
        _validate_workflow_section(wf, "p", "/root")

    def test_citation_string_is_ok(self):
        wf = self._valid()
        wf["steps"] = [{"id": "qc", "tool": "fastqc", "citation": "doi:10.xxx"}]
        _validate_workflow_section(wf, "p", "/root")


# ====== Tests: load_workflow_spec ======


class TestLoadWorkflowSpec:
    def test_returns_none_when_no_workflow_section(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        result = load_workflow_spec(root)
        assert result is None

    def test_returns_workflow_spec_with_steps(self, tmp_path):
        manifest = """abi_version: "0.1"
plugin_id: test_plugin
display_name: Test Plugin
description: For testing
plugin_type: standalone
entry_point: mod:Class
tool_registry: tool_registry.yaml
standard_tables: standard_tables.yaml
tool_contracts: tool_contracts
core_contracts: [test_tool]
workflow:
  name: Analysis Pipeline
  citation: "doi:10.xxx"
  steps:
    - id: qc
      tool: fastqc
    - id: align
      tool: bwa
      after: [qc]
      optional: true
      citation: "doi:10.yyy"
"""
        root = _make_plugin_dir(tmp_path, manifest_content=manifest)
        spec = load_workflow_spec(root)
        assert spec is not None
        assert isinstance(spec, WorkflowSpec)
        assert spec.name == "Analysis Pipeline"
        assert spec.citation == "doi:10.xxx"
        assert len(spec.steps) == 2
        assert spec.steps[0].id == "qc"
        assert spec.steps[0].tool == "fastqc"
        assert spec.steps[0].after == []
        assert spec.steps[0].optional is False
        assert spec.steps[0].citation is None
        assert spec.steps[1].id == "align"
        assert spec.steps[1].tool == "bwa"
        assert spec.steps[1].after == ["qc"]
        assert spec.steps[1].optional is True
        assert spec.steps[1].citation == "doi:10.yyy"


# ====== Tests: load_plugin_manifest ======


class TestLoadPluginManifest:
    def test_missing_manifest_file_raises(self, tmp_path):
        root = tmp_path / "empty_plugin"
        root.mkdir()
        with pytest.raises(ContractValidationError, match="Missing plugin manifest"):
            load_plugin_manifest(root)

    def test_valid_manifest_loads_successfully(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        manifest = load_plugin_manifest(root)
        assert manifest["plugin_id"] == "test_plugin"
        assert manifest["abi_version"] == "0.1"


# ====== Tests: load_tool_contracts ======


class TestLoadToolContracts:
    def test_missing_tool_contracts_dir_raises(self, tmp_path):
        root = tmp_path / "plugin_no_contracts"
        root.mkdir()
        (root / "abi-plugin.yaml").write_text(MANIFEST_YAML)
        (root / "standard_tables.yaml").write_text(STANDARD_TABLES_YAML)
        (root / "tool_registry.yaml").write_text(TOOL_REGISTRY_YAML)
        with pytest.raises(ContractValidationError, match="Missing tool_contracts directory"):
            load_tool_contracts(root)

    def test_no_contract_files_raises(self, tmp_path):
        root = tmp_path / "plugin"
        root.mkdir()
        (root / "abi-plugin.yaml").write_text(MANIFEST_YAML)
        (root / "standard_tables.yaml").write_text(STANDARD_TABLES_YAML)
        (root / "tool_registry.yaml").write_text(TOOL_REGISTRY_YAML)
        contracts_dir = root / "tool_contracts"
        contracts_dir.mkdir()
        with pytest.raises(ContractValidationError, match="No tool contracts found"):
            load_tool_contracts(root)

    def test_valid_contracts_load(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        contracts = load_tool_contracts(root)
        assert "test_tool" in contracts
        assert contracts["test_tool"]["tool_id"] == "test_tool"

    def test_multiple_contracts(self, tmp_path):
        contract2 = """abi_version: "0.1"
tool_id: tool_b
name: Tool B
category: qc
purpose: Test
inputs:
  in_b:
    type: file
outputs:
  out_b:
    type: file
execution:
  executable: tool_b
  command_template: tool_b {in_b} > {out_b}
failure_handling:
  err:
    hint: Fix it
"""
        root = _make_plugin_dir(
            tmp_path,
            contracts_content={"test_tool": TOOL_CONTRACT_YAML, "tool_b": contract2},
        )
        contracts = load_tool_contracts(root)
        assert len(contracts) == 2
        assert "test_tool" in contracts
        assert "tool_b" in contracts

    def test_duplicate_tool_id_raises(self, tmp_path):
        root = _make_plugin_dir(
            tmp_path,
            contracts_content={
                "test_tool": TOOL_CONTRACT_YAML,
                "test_tool_alt": TOOL_CONTRACT_YAML,
            },
        )
        with pytest.raises(ContractValidationError, match="Duplicate tool contract"):
            load_tool_contracts(root)

    def test_filename_mismatch_tool_id_raises(self, tmp_path):
        root = _make_plugin_dir(
            tmp_path,
            contracts_content={"wrong_name": TOOL_CONTRACT_YAML},
        )
        with pytest.raises(ContractValidationError, match="must match tool_id"):
            load_tool_contracts(root)


# ====== Tests: _validate_contract_matches_registry ======


class TestValidateContractMatchesRegistry:
    def _base_contract(self):
        return {
            "abi_version": "0.1",
            "tool_id": "tool_a",
            "name": "Tool A",
            "category": "qc",
            "purpose": "Test",
            "inputs": {"in": {"type": "file"}},
            "outputs": {"out": {"type": "file"}},
            "execution": {
                "executable": "tool_a",
                "command_template": "tool_a {in} > {out}",
            },
            "failure_handling": {"err": {"hint": "Fix"}},
        }

    def _base_registry(self):
        return {
            "id": "tool_a",
            "executable": "tool_a",
            "command_template": "tool_a {in} > {out}",
            "category": "qc",
            "inputs": ["in"],
            "outputs": ["out"],
        }

    def test_matching_passes(self):
        _validate_contract_matches_registry(self._base_contract(), self._base_registry())

    def test_non_matching_executable_raises(self):
        reg = self._base_registry()
        reg["executable"] = "other_tool"
        with pytest.raises(ContractValidationError, match="does not match registry"):
            _validate_contract_matches_registry(self._base_contract(), reg)

    def test_non_matching_command_template_raises(self):
        reg = self._base_registry()
        reg["command_template"] = "other_tool {in}"
        with pytest.raises(ContractValidationError, match="does not match registry"):
            _validate_contract_matches_registry(self._base_contract(), reg)

    def test_non_matching_category_raises(self):
        reg = self._base_registry()
        reg["category"] = "alignment"
        with pytest.raises(ContractValidationError, match="does not match registry"):
            _validate_contract_matches_registry(self._base_contract(), reg)

    def test_registry_inputs_missing_from_contract_raises(self):
        reg = self._base_registry()
        reg["inputs"] = ["in", "extra_input"]
        with pytest.raises(ContractValidationError, match="registry inputs missing from contract"):
            _validate_contract_matches_registry(self._base_contract(), reg)

    def test_template_fields_not_in_contract_inputs_raises(self):
        contract = self._base_contract()
        reg = self._base_registry()
        tmpl = "tool_a {in} {missing_field}"
        contract["execution"]["command_template"] = tmpl
        reg["command_template"] = tmpl
        with pytest.raises(ContractValidationError, match="template fields missing"):
            _validate_contract_matches_registry(contract, reg)
        contract = self._base_contract()
        contract["execution"]["command_template"] = "tool_a  {in}  >  {out}"
        _validate_contract_matches_registry(contract, self._base_registry())


# ====== Tests: _validate_declared_tables ======


class TestValidateDeclaredTables:
    def test_matching_tables_passes(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        root_manifest = {
            "standard_tables": "standard_tables.yaml",
        }
        table_schemas = {"test_table": ["col_a", "col_b"]}
        _validate_declared_tables(root, root_manifest, table_schemas)

    def test_mismatched_declared_vs_runtime_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        root_manifest = {
            "standard_tables": "standard_tables.yaml",
        }
        table_schemas = {"unknown_table": ["col_a"]}
        with pytest.raises(ContractValidationError, match="standard_tables.yaml must match"):
            _validate_declared_tables(root, root_manifest, table_schemas)

    def test_column_mismatch_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        root_manifest = {
            "standard_tables": "standard_tables.yaml",
        }
        table_schemas = {"test_table": ["col_a", "col_c"]}
        with pytest.raises(ContractValidationError, match="declared columns do not match"):
            _validate_declared_tables(root, root_manifest, table_schemas)


# ====== Tests: validate_plugin_contract_files ======


class TestValidatePluginContractFiles:
    def test_no_root_attribute_returns_early(self):
        class NoRootPlugin:
            pass

        plugin = NoRootPlugin()
        validate_plugin_contract_files(plugin)

    def test_full_validation_passes(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        registry = _FakeRegistry(
            [
                {
                    "id": "test_tool",
                    "executable": "test_tool",
                    "command_template": "test_tool -i {input_file} -o {output_file}",
                    "category": "qc",
                    "inputs": ["input_file"],
                    "outputs": ["output_file"],
                }
            ]
        )
        tables = {"test_table": ["col_a", "col_b"]}
        plugin = _FakePlugin(root=str(root), registry=registry, tables=tables)
        validate_plugin_contract_files(plugin)

    def test_pipeline_template_param_violation_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        (root / "config_default.yaml").write_text("outdir: results\n")
        (root / "pipeline_dag.yaml").write_text(
            """
nodes:
  qc_multiqc:
    inputs:
      output_dir:
        source: "{project_outdir}/01_qc"
    outputs:
      report:
        path: "{outdir}/multiqc.html"
"""
        )
        registry = _FakeRegistry(
            [
                {
                    "id": "test_tool",
                    "executable": "test_tool",
                    "command_template": "test_tool -i {input_file} -o {output_file}",
                    "category": "qc",
                    "inputs": ["input_file"],
                    "outputs": ["output_file"],
                }
            ]
        )
        tables = {"test_table": ["col_a", "col_b"]}
        plugin = _FakePlugin(root=str(root), registry=registry, tables=tables)

        with pytest.raises(ContractValidationError, match="pipeline template params"):
            validate_plugin_contract_files(plugin)

    def test_missing_required_contract_raises(self, tmp_path):
        contract2 = """abi_version: "0.1"
tool_id: tool_b
name: Tool B
category: qc
purpose: Test
inputs:
  in_b:
    type: file
outputs:
  out_b:
    type: file
execution:
  executable: tool_b
  command_template: tool_b {in_b} > {out_b}
failure_handling:
  err:
    hint: Fix it
"""
        root = _make_plugin_dir(
            tmp_path,
            contracts_content={"tool_b": contract2},
        )
        registry = _FakeRegistry(
            [
                {
                    "id": "test_tool",
                    "executable": "test_tool",
                    "command_template": "test_tool -i {input_file} -o {output_file}",
                    "category": "qc",
                    "inputs": ["input_file"],
                    "outputs": ["output_file"],
                }
            ]
        )
        tables = {"test_table": ["col_a", "col_b"]}
        plugin = _FakePlugin(root=str(root), registry=registry, tables=tables)
        with pytest.raises(ContractValidationError, match="missing required tool contracts"):
            validate_plugin_contract_files(plugin)

    def test_unknown_contract_raises(self, tmp_path):
        root = _make_plugin_dir(tmp_path)
        registry = _FakeRegistry([])
        tables = {"test_table": ["col_a", "col_b"]}
        plugin = _FakePlugin(root=str(root), registry=registry, tables=tables)
        with pytest.raises(ContractValidationError, match="contracts without registry tools"):
            validate_plugin_contract_files(plugin)
