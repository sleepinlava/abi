"""Unit tests for helper functions and properties in abi.dag_planner."""

from __future__ import annotations

import pytest

from abi.dag_planner import (
    PathTemplateContext,
    UniversalDAG,
    _resolve_input_path,
    _resolve_script_path,
    detect_platform,
    node_id_to_tool_id,
)
from abi.schemas import SampleInput

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_minimal_dag() -> UniversalDAG:
    """Build a minimal UniversalDAG with 3 nodes across two platforms."""
    spec = {
        "pipeline_id": "test_pipeline",
        "platforms": ["illumina", "ont"],
        "category_dirs": {
            "qc": "01_qc",
            "assembly": "02_assembly",
        },
        "nodes": {
            "qc": {
                "id": "qc",
                "platforms": ["illumina"],
                "category": "qc",
                "outputs": {"clean_read1": {}},
            },
            "assembly": {
                "id": "assembly",
                "platforms": ["illumina", "ont"],
                "category": "assembly",
                "outputs": {"contigs": {}},
                "depends_on": ["qc"],
            },
            "report": {
                "id": "report",
                "platforms": ["illumina", "ont"],
                "category": "reporting",
                "outputs": {"report_html": {}},
                "depends_on": ["assembly"],
            },
        },
    }
    return UniversalDAG(spec)


# ═══════════════════════════════════════════════════════════════════════════
# 1. detect_platform
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectPlatform:
    def test_pacbio_hifi_by_technology(self):
        sample = SampleInput(
            sample_id="S1", platform="generic", technology="hifi", long_reads="reads.fastq"
        )
        assert detect_platform(sample) == "pacbio_hifi"

    def test_pacbio_by_long_reads_filename(self):
        sample = SampleInput(sample_id="S1", platform="generic", long_reads="pacbio.fastq")
        assert detect_platform(sample) == "pacbio_hifi"

    def test_ont_by_long_reads(self):
        sample = SampleInput(sample_id="S1", platform="generic", long_reads="ont_reads.fastq")
        assert detect_platform(sample) == "ont"

    def test_illumina_paired_end(self):
        sample = SampleInput(sample_id="S1", platform="generic", read1="R1.fq", read2="R2.fq")
        assert detect_platform(sample) == "illumina"

    def test_illumina_single_end(self):
        sample = SampleInput(sample_id="S1", platform="generic", read1="R1.fq")
        assert detect_platform(sample) == "illumina"

    def test_assembly_only(self):
        sample = SampleInput(sample_id="S1", platform="generic", assembly="contigs.fasta")
        assert detect_platform(sample) == "assembly"

    def test_default_illumina_no_inputs(self):
        sample = SampleInput(sample_id="S1", platform="generic")
        assert detect_platform(sample) == "illumina"

    def test_explicit_valid_platform_passed_through(self):
        sample = SampleInput(sample_id="S1", platform="ont", long_reads="reads.fastq")
        assert detect_platform(sample) == "ont"

    def test_explicit_pacbio_hifi_passed_through(self):
        sample = SampleInput(sample_id="S1", platform="pacbio_hifi", long_reads="reads.fastq")
        assert detect_platform(sample) == "pacbio_hifi"


# ═══════════════════════════════════════════════════════════════════════════
# 2. UniversalDAG properties
# ═══════════════════════════════════════════════════════════════════════════


class TestUniversalDAGProperties:
    def test_platforms(self):
        dag = _make_minimal_dag()
        assert dag.platforms == ["illumina", "ont"]

    def test_category_dirs(self):
        dag = _make_minimal_dag()
        assert dag.category_dirs == {"qc": "01_qc", "assembly": "02_assembly"}

    def test_node_ids(self):
        dag = _make_minimal_dag()
        assert dag.node_ids == ["qc", "assembly", "report"]

    def test_get_node_returns_copy(self):
        dag = _make_minimal_dag()
        node = dag.get_node("qc")
        assert node["id"] == "qc"
        assert node["platforms"] == ["illumina"]
        # Verify it is a copy (modify does not affect internal state)
        node["extra"] = "should_not_persist"
        node2 = dag.get_node("qc")
        assert "extra" not in node2

    def test_get_node_missing_returns_empty_dict(self):
        dag = _make_minimal_dag()
        assert dag.get_node("nonexistent") == {}


# ═══════════════════════════════════════════════════════════════════════════
# 3. _evaluate_condition (static method on UniversalDAG)
# ═══════════════════════════════════════════════════════════════════════════


class TestEvaluateCondition:
    def test_value_equals_match(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "mode", "operator": "value", "value": "auto"},
                {"mode": "auto"},
            )
            is True
        )

    def test_value_equals_no_match(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "mode", "operator": "value", "value": "interactive"},
                {"mode": "auto"},
            )
            is False
        )

    def test_not_empty_with_non_empty_string(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "name", "operator": "not_empty"},
                {"name": "hello"},
            )
            is True
        )

    def test_not_empty_with_whitespace_string(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "name", "operator": "not_empty"},
                {"name": "   "},
            )
            is False
        )

    def test_not_empty_with_non_empty_list(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "items", "operator": "not_empty"},
                {"items": [1, 2, 3]},
            )
            is True
        )

    def test_not_empty_with_empty_list(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "items", "operator": "not_empty"},
                {"items": []},
            )
            is False
        )

    def test_not_empty_with_non_empty_dict(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "cfg", "operator": "not_empty"},
                {"cfg": {"a": 1}},
            )
            is True
        )

    def test_not_empty_with_empty_dict(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "cfg", "operator": "not_empty"},
                {"cfg": {}},
            )
            is False
        )

    def test_not_empty_with_none_value(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "name", "operator": "not_empty"},
                {"name": None},
            )
            is False
        )

    def test_not_empty_with_missing_field(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "missing", "operator": "not_empty"},
                {},
            )
            is False
        )

    def test_list_contains_match(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "platforms", "operator": "list_contains", "value": "illumina"},
                {"platforms": ["illumina", "ont"]},
            )
            is True
        )

    def test_list_contains_no_match(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "platforms", "operator": "list_contains", "value": "pacbio"},
                {"platforms": ["illumina", "ont"]},
            )
            is False
        )

    def test_list_contains_with_string_value(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "mode", "operator": "list_contains", "value": "auto"},
                {"mode": "auto"},
            )
            is True
        )

    def test_list_contains_with_string_value_no_match(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "mode", "operator": "list_contains", "value": "interactive"},
                {"mode": "auto"},
            )
            is False
        )

    def test_list_contains_non_list_non_string(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "num", "operator": "list_contains", "value": 5},
                {"num": 5},
            )
            is False
        )

    def test_unknown_operator_returns_false(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "mode", "operator": "bogus_operator", "value": "auto"},
                {"mode": "auto"},
            )
            is False
        )

    def test_default_operator_is_value(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "mode", "value": "auto"},
                {"mode": "auto"},
            )
            is True
        )

    def test_dotted_field_path_navigation(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "host_removal.host_reference", "operator": "not_empty"},
                {"host_removal": {"host_reference": "/path/to/host.fa"}},
            )
            is True
        )

    def test_dotted_field_path_missing(self):
        assert (
            UniversalDAG._evaluate_condition(
                {"field": "host_removal.host_reference", "operator": "not_empty"},
                {"host_removal": {}},
            )
            is False
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. _category_explicitly_enabled (static method on UniversalDAG)
# ═══════════════════════════════════════════════════════════════════════════


class TestCategoryExplicitlyEnabled:
    def test_string_true(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": "true"}}, "qc") is True

    def test_string_yes(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": "yes"}}, "qc") is True

    def test_string_one(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": "1"}}, "qc") is True

    def test_string_false(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": "false"}}, "qc") is False

    def test_string_no(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": "no"}}, "qc") is False

    def test_string_zero(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": "0"}}, "qc") is False

    def test_bool_true(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": True}}, "qc") is True

    def test_bool_false(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"enable": False}}, "qc") is False

    def test_missing_category(self):
        assert UniversalDAG._category_explicitly_enabled({}, "qc") is False

    def test_non_mapping_block(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": "just_a_string"}, "qc") is False

    def test_missing_enable_key(self):
        assert UniversalDAG._category_explicitly_enabled({"qc": {"threads": 4}}, "qc") is False


# ═══════════════════════════════════════════════════════════════════════════
# 5. _resolve_script_path
# ═══════════════════════════════════════════════════════════════════════════


class TestResolveScriptPath:
    def test_non_script_key_returns_value_as_is_with_empty_value(self):
        """When key does not end with _script, return the value string as-is."""
        result = _resolve_script_path("host_reference", "")
        assert result == ""

    def test_non_script_key_returns_value_as_is_with_not_configured(self):
        result = _resolve_script_path("host_reference", "NOT_CONFIGURED")
        assert result == "NOT_CONFIGURED"

    def test_non_empty_script_value_returned_as_is(self):
        result = _resolve_script_path("diversity_script", "/custom/path/diversity.py")
        assert result == "/custom/path/diversity.py"

    def test_not_configured_sentinel_for_script_key(self):
        """When a _script key has NOT_CONFIGURED and no bundled script, returns empty."""
        result = _resolve_script_path("nonexistent_script", "DIVERSITY_SCRIPT_NOT_CONFIGURED")
        assert result == "DIVERSITY_SCRIPT_NOT_CONFIGURED"

    def test_empty_value_for_non_script_key(self):
        result = _resolve_script_path("description", "")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════
# 6. _resolve_input_path
# ═══════════════════════════════════════════════════════════════════════════


class TestResolveInputPath:
    def test_plain_string_no_braces(self):
        result = _resolve_input_path("just/a/path.fastq", {}, None)
        assert result == "just/a/path.fastq"

    def test_template_with_outdir(self):
        result = _resolve_input_path(
            "{outdir}/results/file.txt",
            {"outdir": "/output"},
            None,
        )
        assert result == "/output/results/file.txt"

    def test_template_with_sample_id(self):
        sample = SampleInput(sample_id="S1", platform="illumina")
        result = _resolve_input_path(
            "{sample_id}_report.html",
            {"outdir": "/tmp"},
            sample,
        )
        assert result == "S1_report.html"

    def test_template_with_non_empty_int_value(self):
        result = _resolve_input_path(42, {}, None)
        assert result == "42"

    def test_template_with_broken_key_returns_raw(self):
        result = _resolve_input_path("{nonexistent_key}", {"outdir": "/tmp"}, None)
        assert result == "{nonexistent_key}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. node_id_to_tool_id
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeIdToToolId:
    def test_node_with_explicit_tool_id(self):
        spec = {
            "nodes": {
                "my_qc": {
                    "id": "my_qc",
                    "tool_id": "fastp",
                    "platforms": [],
                }
            }
        }
        dag = UniversalDAG(spec)
        assert node_id_to_tool_id(dag, "my_qc") == "fastp"

    def test_node_without_tool_id_returns_node_id(self):
        dag = _make_minimal_dag()
        assert node_id_to_tool_id(dag, "qc") == "qc"

    def test_node_with_none_tool_id_returns_node_id(self):
        spec = {
            "nodes": {
                "my_qc": {
                    "id": "my_qc",
                    "tool_id": None,
                    "platforms": [],
                }
            }
        }
        dag = UniversalDAG(spec)
        assert node_id_to_tool_id(dag, "my_qc") == "my_qc"

    def test_missing_node_returns_node_id(self):
        dag = _make_minimal_dag()
        assert node_id_to_tool_id(dag, "no_such_node") == "no_such_node"


# ═══════════════════════════════════════════════════════════════════════════
# 8. PathTemplateContext
# ═══════════════════════════════════════════════════════════════════════════


class TestPathTemplateContext:
    def test_is_dict_subclass(self):
        ctx = PathTemplateContext(config={"outdir": "/tmp"})
        assert isinstance(ctx, dict)

    def test_outdir_and_category_dir(self):
        ctx = PathTemplateContext(
            config={"outdir": "/output", "threads": 8},
            category_dir="01_qc",
        )
        assert ctx["outdir"] == "/output"
        assert ctx["category_dir"] == "01_qc"

    def test_sample_id_and_sample_dot_attrs(self):
        sample = SampleInput(
            sample_id="S1",
            platform="illumina",
            read1="S1_R1.fq",
            read2="S1_R2.fq",
        )
        ctx = PathTemplateContext(
            config={"outdir": "/tmp"},
            sample=sample,
        )
        assert ctx["sample_id"] == "S1"
        assert ctx["sample.platform"] == "illumina"
        assert ctx["sample.read1"] == "S1_R1.fq"
        assert ctx["sample.read2"] == "S1_R2.fq"

    def test_sample_attribute_not_set_in_ctx_when_none(self):
        sample = SampleInput(sample_id="S2", platform="illumina")
        ctx = PathTemplateContext(
            config={"outdir": "/tmp"},
            sample=sample,
        )
        assert "sample.read2" not in ctx  # read2 is None
        assert "sample.group" not in ctx  # group is None

    def test_config_level_keys(self):
        ctx = PathTemplateContext(
            config={"outdir": "/tmp", "threads": "16", "mode": "auto", "project_name": "myproj"},
        )
        assert ctx["threads"] == "16"
        assert ctx["mode"] == "auto"
        assert ctx["project_name"] == "myproj"

    def test_resources_keys(self):
        ctx = PathTemplateContext(
            config={
                "outdir": "/tmp",
                "resources": {
                    "db_host": "/data/host.fa",
                    "db_plasmid": "/data/plasmids.fa",
                },
            },
        )
        assert ctx["resources.db_host"] == "/data/host.fa"
        assert ctx["resources.db_plasmid"] == "/data/plasmids.fa"

    def test_upstream_outputs(self):
        ctx = PathTemplateContext(
            config={"outdir": "/tmp"},
            upstream_outputs={
                "qc": {"clean_read1": "/out/clean_R1.fq", "clean_read2": "/out/clean_R2.fq"},
                "filter": {"passed": "/out/passed.fq"},
            },
        )
        assert ctx["upstream_qc.outputs.clean_read1"] == "/out/clean_R1.fq"
        assert ctx["upstream_qc.outputs.clean_read2"] == "/out/clean_R2.fq"
        assert ctx["upstream_filter.outputs.passed"] == "/out/passed.fq"

    def test_format_map_with_template(self):
        sample = SampleInput(sample_id="S1", platform="illumina")
        ctx = PathTemplateContext(
            config={"outdir": "/output", "resources": {"db": "/refs/db.fa"}},
            sample=sample,
            category_dir="02_assembly",
        )
        result = "{outdir}/{category_dir}/{sample_id}/assembly.fa".format_map(ctx)
        assert result == "/output/02_assembly/S1/assembly.fa"

    def test_missing_key_raises_keyerror(self):
        ctx = PathTemplateContext(config={"outdir": "/tmp"})
        with pytest.raises(KeyError):
            "{missing_key}".format_map(ctx)

    def test_no_sample_no_sample_id_key(self):
        ctx = PathTemplateContext(config={"outdir": "/tmp"})
        assert "sample_id" not in ctx
        assert "sample.platform" not in ctx

    def test_none_resources_handled_gracefully(self):
        ctx = PathTemplateContext(
            config={"outdir": "/tmp", "resources": None},
        )
        # Should not raise; simply no resources.* keys
        resource_keys = [k for k in ctx if k.startswith("resources.")]
        assert resource_keys == []

    def test_none_upstream_outputs_handled_gracefully(self):
        ctx = PathTemplateContext(
            config={"outdir": "/tmp"},
            upstream_outputs=None,
        )
        upstream_keys = [k for k in ctx if k.startswith("upstream_")]
        assert upstream_keys == []
