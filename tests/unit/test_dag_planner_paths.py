"""Targeted tests for uncovered code paths in abi.dag_planner.

Covers:
1. UniversalDAG.active_node_ids — unknown nodes in include_nodes
2. UniversalDAG._category_enabled — optional node, no config block
3. UniversalDAG.resolve_dependencies — unresolvable deps (required, no fallback)
4. _resolve_script_path — plugin_root with scripts/ directory
5. _resolve_input_path — template resolution (extended)
6. _resolve_outputs — non-Mapping spec value skip
7. build_plan_from_dag — integration (per-sample, cross-sample, empty platform)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from abi.dag_planner import (
    PathTemplateContext,
    UniversalDAG,
    _resolve_input_path,
    _resolve_outputs,
    _resolve_script_path,
    build_plan_from_dag,
)
from abi.schemas import ExecutionPlan, SampleContext, SampleInput

# -- helpers --


def _make_sample_context(sample_id="S1", platform="illumina", read1="S1_R1.fq", read2="S1_R2.fq"):
    sample = SampleInput(sample_id=sample_id, platform=platform, read1=read1, read2=read2)
    return SampleContext(samples=[sample], multi_sample=False, has_groups=False)


# ====================================================================
# 1. active_node_ids — unknown nodes in include_nodes
# ====================================================================


class TestActiveNodeIdsUnknownInclude:
    def test_raises_valueerror_on_unknown_include_nodes(self):
        spec = {"nodes": {"A": {"platforms": ["illumina"], "category": "qc"}}}
        dag = UniversalDAG(spec)
        config = {"workflow": {"include_nodes": ["C"]}}
        with pytest.raises(ValueError, match="include_nodes references unknown nodes"):
            dag.active_node_ids("illumina", config)

    def test_raises_on_non_list_include_nodes(self):
        spec = {"nodes": {"A": {"platforms": ["illumina"], "category": "qc"}}}
        dag = UniversalDAG(spec)
        config = {"workflow": {"include_nodes": "not-a-list"}}
        with pytest.raises(ValueError, match="must be a list of non-empty node IDs"):
            dag.active_node_ids("illumina", config)

    def test_raises_on_empty_string_in_include_nodes(self):
        spec = {"nodes": {"A": {"platforms": ["illumina"], "category": "qc"}}}
        dag = UniversalDAG(spec)
        config = {"workflow": {"include_nodes": [""]}}
        with pytest.raises(ValueError, match="must be a list of non-empty node IDs"):
            dag.active_node_ids("illumina", config)

    def test_valid_include_nodes_whitelist(self):
        spec = {
            "nodes": {
                "A": {"platforms": ["illumina"], "category": "qc"},
                "B": {"platforms": ["illumina"], "category": "assembly"},
                "C": {"platforms": ["illumina"], "category": "report"},
            }
        }
        dag = UniversalDAG(spec)
        config = {"workflow": {"include_nodes": ["A", "C"]}}
        result = dag.active_node_ids("illumina", config)
        assert result == ["A", "C"]

    def test_workflow_not_a_mapping_ignores_include(self):
        spec = {
            "nodes": {
                "A": {"platforms": ["illumina"], "category": "qc"},
                "B": {"platforms": ["illumina"], "category": "assembly"},
            }
        }
        dag = UniversalDAG(spec)
        config = {"workflow": "not-a-dict"}
        result = dag.active_node_ids("illumina", config)
        assert result == ["A", "B"]


# ====================================================================
# 2. _category_enabled — optional node, no config block
# ====================================================================


class TestCategoryEnabledOptionalNoConfig:
    def test_optional_node_no_config_block_returns_false(self):
        spec = {
            "nodes": {
                "opt": {
                    "platforms": ["illumina"],
                    "category": "nonexistent",
                    "optional": True,
                }
            }
        }
        dag = UniversalDAG(spec)
        result = dag._category_enabled({}, "nonexistent", "opt")
        assert result is False

    def test_empty_node_id_no_config_block_returns_true(self):
        spec = {
            "nodes": {
                "req": {
                    "platforms": ["illumina"],
                    "category": "nonexistent",
                }
            }
        }
        dag = UniversalDAG(spec)
        result = dag._category_enabled({}, "nonexistent", "")
        assert result is True

    def test_required_node_no_config_block_returns_true(self):
        spec = {
            "nodes": {
                "req": {
                    "platforms": ["illumina"],
                    "category": "nonexistent",
                }
            }
        }
        dag = UniversalDAG(spec)
        result = dag._category_enabled({}, "nonexistent", "req")
        assert result is True


# ====================================================================
# 3. resolve_dependencies — unresolvable deps error
# ====================================================================


class TestResolveDependenciesUnresolvable:
    def test_required_node_inactive_dep_no_fallback_raises(self):
        spec = {
            "nodes": {
                "A": {"platforms": ["illumina"], "category": "qc"},
                "B": {"platforms": ["illumina"], "category": "assembly", "depends_on": ["A"]},
            }
        }
        dag = UniversalDAG(spec)
        with pytest.raises(ValueError, match="none are active and no fallbacks are available"):
            dag.resolve_dependencies(["B"], platform="illumina")

    def test_optional_node_inactive_dep_succeeds(self):
        spec = {
            "nodes": {
                "A": {"platforms": ["illumina"], "category": "qc"},
                "B": {
                    "platforms": ["illumina"],
                    "category": "assembly",
                    "depends_on": ["A"],
                    "optional": True,
                },
            }
        }
        dag = UniversalDAG(spec)
        result = dag.resolve_dependencies(["B"], platform="illumina")
        assert result == {"B": []}

    def test_active_fallback_resolves(self):
        spec = {
            "nodes": {
                "A": {"platforms": ["illumina"], "category": "qc"},
                "B": {"platforms": ["illumina"], "category": "assembly"},
                "C": {
                    "platforms": ["illumina"],
                    "category": "reporting",
                    "depends_on": ["A"],
                    "fallback_depends": ["B"],
                },
            }
        }
        dag = UniversalDAG(spec)
        result = dag.resolve_dependencies(["B", "C"], platform="illumina")
        assert result["C"] == ["B"]


# ====================================================================
# 4. _resolve_script_path — plugin_root with scripts/
# ====================================================================


class TestResolveScriptPathPluginRoot:
    def test_plugin_root_scripts_dir_resolves_script(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        script_file = scripts_dir / "my_unique_test_script.py"
        script_file.write_text("# test script")

        result = _resolve_script_path("my_unique_test_script_script", "", plugin_root=str(tmp_path))
        assert "my_unique_test_script.py" in result
        assert str(script_file.resolve()) in result or Path(result).is_file()

    def test_resolves_r_script(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "my_unique_r_test_script.R").write_text("# R script")

        result = _resolve_script_path(
            "my_unique_r_test_script_script", "", plugin_root=str(tmp_path)
        )
        assert "my_unique_r_test_script.R" in result
        assert Path(result).is_file()

    def test_no_matching_file_resolved_from_project_scripts(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "unrelated.py").write_text("# unrelated")

        result = _resolve_script_path("diversity_script", "", plugin_root=str(tmp_path))
        assert "amplicon_diversity.py" in result
        assert Path(result).is_file()

    def test_plugin_scripts_overrides_project_scripts(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        plugin_script = scripts_dir / "zmqf_unique_name_script.py"
        plugin_script.write_text("# plugin script")

        result = _resolve_script_path(
            "zmqf_unique_name_script_script", "", plugin_root=str(tmp_path)
        )
        assert str(plugin_script.resolve()) in result or Path(result).is_file()
        assert "zmqf_unique_name_script.py" in result


# ====================================================================
# 5. _resolve_input_path — template resolution (extended)
# ====================================================================


class TestResolveInputPathExtended:
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

    def test_template_with_category_dir(self):
        result = _resolve_input_path(
            "{outdir}/{category_dir}/file.txt",
            {"outdir": "/out"},
            None,
        )
        assert result == "/out//file.txt"

    def test_template_with_config_level_vars(self):
        result = _resolve_input_path(
            "{threads}_{mode}/input.fq",
            {"outdir": "/out", "threads": 8, "mode": "auto"},
            None,
        )
        assert result == "8_auto/input.fq"

    def test_plain_string_no_braces(self):
        result = _resolve_input_path("just/a/path.fastq", {}, None)
        assert result == "just/a/path.fastq"

    def test_broken_template_returns_raw(self):
        result = _resolve_input_path("{nonexistent_key}", {"outdir": "/tmp"}, None)
        assert result == "{nonexistent_key}"

    def test_integer_template_str_converted(self):
        result = _resolve_input_path(42, {}, None)
        assert result == "42"


# ====================================================================
# 6. _resolve_outputs — non-Mapping spec skip
# ====================================================================


class TestResolveOutputs:
    def test_non_mapping_output_skipped_with_string(self):
        spec = {
            "nodes": {
                "qc": {
                    "platforms": ["illumina"],
                    "category": "qc",
                    "outputs": {"clean": "raw_string", "output_dir": {"path": "{outdir}/qc"}},
                }
            }
        }
        dag = UniversalDAG(spec)
        ctx = PathTemplateContext(config={"outdir": "/out"})
        resolved = _resolve_outputs(dag, "qc", ctx)
        assert resolved["clean"] == "raw_string"

    def test_non_mapping_output_with_int(self):
        spec = {
            "nodes": {
                "qc": {
                    "platforms": ["illumina"],
                    "category": "qc",
                    "outputs": {"threads": 4, "output_dir": {"path": "{outdir}/qc"}},
                }
            }
        }
        dag = UniversalDAG(spec)
        ctx = PathTemplateContext(config={"outdir": "/out"})
        resolved = _resolve_outputs(dag, "qc", ctx)
        assert resolved["threads"] == 4

    def test_path_template_resolved(self):
        spec = {
            "nodes": {
                "assembly": {
                    "platforms": ["illumina"],
                    "category": "assembly",
                    "outputs": {"contigs": {"path": "{outdir}/{category_dir}/contigs.fa"}},
                }
            }
        }
        dag = UniversalDAG(spec)
        ctx = PathTemplateContext(
            config={"outdir": "/out"}, sample=None, category_dir="02_assembly"
        )
        resolved = _resolve_outputs(dag, "assembly", ctx)
        assert resolved["contigs"] == "/out/02_assembly/contigs.fa"
        assert resolved["output_dir"] == "/out/02_assembly"

    def test_output_without_path_defaults_empty(self):
        spec = {
            "nodes": {
                "qc": {
                    "platforms": ["illumina"],
                    "category": "qc",
                    "outputs": {"clean": {}, "output_dir": {"path": "{outdir}/qc"}},
                }
            }
        }
        dag = UniversalDAG(spec)
        ctx = PathTemplateContext(config={"outdir": "/out"})
        resolved = _resolve_outputs(dag, "qc", ctx)
        assert resolved["clean"] == ""

    def test_output_dir_default_with_sample_id(self):
        spec = {
            "nodes": {
                "qc": {
                    "platforms": ["illumina"],
                    "category": "qc",
                    "outputs": {"clean": {"path": "{outdir}/qc/clean.fq"}},
                }
            }
        }
        dag = UniversalDAG(spec)
        sample = SampleInput(sample_id="S1", platform="illumina")
        ctx = PathTemplateContext(config={"outdir": "/out"}, sample=sample, category_dir="01_qc")
        resolved = _resolve_outputs(dag, "qc", ctx)
        assert resolved["output_dir"] == "/out/01_qc/S1"

    def test_no_outputs_spec_adds_default_output_dir(self):
        spec = {"nodes": {"simple": {"platforms": ["illumina"], "category": "qc"}}}
        dag = UniversalDAG(spec)
        ctx = PathTemplateContext(config={"outdir": "/out"}, category_dir="01_qc")
        resolved = _resolve_outputs(dag, "simple", ctx)
        assert resolved["output_dir"] == "/out/01_qc"


# ====================================================================
# 7. build_plan_from_dag — integration
# ====================================================================


class TestBuildPlanFromDag:
    def test_per_sample_node_generates_steps(self, tmp_path):
        dag_yaml = {
            "pipeline_id": "test",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc"},
            "nodes": {
                "qc": {
                    "scope": "per_sample",
                    "category": "qc",
                    "platforms": ["illumina"],
                    "outputs": {"clean": {"path": "{outdir}/{category_dir}/clean.fq"}},
                }
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.dump(dag_yaml))
        ctx = _make_sample_context()
        plan = build_plan_from_dag(dag_path, {"outdir": str(tmp_path / "out")}, ctx)
        assert isinstance(plan, ExecutionPlan)
        assert "qc" in plan.selected_tools
        assert any(s.tool_id == "qc" and s.sample_id == "S1" for s in plan.steps)

    def test_multiple_per_sample_nodes_in_order(self, tmp_path):
        dag_yaml = {
            "pipeline_id": "test_chain",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc", "assembly": "02_assembly"},
            "nodes": {
                "qc": {
                    "scope": "per_sample",
                    "category": "qc",
                    "platforms": ["illumina"],
                    "outputs": {"clean": {"path": "{outdir}/{category_dir}/{sample_id}/clean.fq"}},
                },
                "assembly": {
                    "scope": "per_sample",
                    "category": "assembly",
                    "platforms": ["illumina"],
                    "depends_on": ["qc"],
                    "outputs": {
                        "contigs": {"path": "{outdir}/{category_dir}/{sample_id}/contigs.fa"}
                    },
                },
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.dump(dag_yaml))
        ctx = _make_sample_context()
        plan = build_plan_from_dag(dag_path, {"outdir": str(tmp_path / "out")}, ctx)
        tool_ids = {s.tool_id for s in plan.steps}
        assert tool_ids == {"qc", "assembly"}
        # topological order: qc (level 0) before assembly (depends on qc)
        qc_idx = next(i for i, s in enumerate(plan.steps) if s.tool_id == "qc")
        asm_idx = next(i for i, s in enumerate(plan.steps) if s.tool_id == "assembly")
        assert qc_idx < asm_idx

    def test_no_nodes_match_platform_returns_plan(self, tmp_path):
        dag_yaml = {
            "pipeline_id": "test_ont",
            "platforms": ["ont"],
            "nodes": {
                "qc": {
                    "scope": "per_sample",
                    "category": "qc",
                    "platforms": ["ont"],
                    "outputs": {"clean": {"path": "{outdir}/qc/clean.fq"}},
                }
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.dump(dag_yaml))
        ctx = _make_sample_context(platform="illumina")
        plan = build_plan_from_dag(dag_path, {"outdir": str(tmp_path / "out")}, ctx)
        assert isinstance(plan, ExecutionPlan)

    def test_cross_sample_node_generates_step(self, tmp_path):
        dag_yaml = {
            "pipeline_id": "test_cross",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc", "report": "05_report"},
            "nodes": {
                "qc": {
                    "scope": "per_sample",
                    "category": "qc",
                    "platforms": ["illumina"],
                    "outputs": {"clean": {"path": "{outdir}/{category_dir}/{sample_id}/clean.fq"}},
                },
                "summary": {
                    "scope": "cross_sample",
                    "category": "report",
                    "platforms": ["illumina"],
                    "inputs": {
                        "qc_outs": {"aggregate": "per_sample_outputs", "source": "qc.clean"}
                    },
                    "outputs": {"report": {"path": "{outdir}/{category_dir}/summary.html"}},
                },
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.dump(dag_yaml))
        ctx = _make_sample_context()
        plan = build_plan_from_dag(dag_path, {"outdir": str(tmp_path / "out")}, ctx)
        cross = [s for s in plan.steps if s.sample_id is None]
        assert len(cross) == 1
        assert cross[0].tool_id == "summary"

    def test_execution_plan_metadata(self, tmp_path):
        dag_yaml = {
            "pipeline_id": "test_meta",
            "platforms": ["illumina"],
            "nodes": {
                "qc": {
                    "scope": "per_sample",
                    "category": "qc",
                    "platforms": ["illumina"],
                    "outputs": {"clean": {"path": "{outdir}/qc/clean.fq"}},
                }
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.dump(dag_yaml))
        ctx = _make_sample_context()
        config = {"outdir": str(tmp_path / "out"), "threads": 4, "mode": "batch"}
        plan = build_plan_from_dag(dag_path, config, ctx)
        assert plan.threads == 4
        assert plan.mode == "batch"
        assert len(plan.samples) == 1

    def test_include_nodes_filters_steps(self, tmp_path):
        dag_yaml = {
            "pipeline_id": "test_filter",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc", "assembly": "02_assembly"},
            "nodes": {
                "qc": {
                    "scope": "per_sample",
                    "category": "qc",
                    "platforms": ["illumina"],
                    "outputs": {"clean": {"path": "{outdir}/qc/clean.fq"}},
                },
                "assembly": {
                    "scope": "per_sample",
                    "category": "assembly",
                    "platforms": ["illumina"],
                    "depends_on": ["qc"],
                    "outputs": {"contigs": {"path": "{outdir}/assembly/conts.fa"}},
                },
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.dump(dag_yaml))
        ctx = _make_sample_context()
        config = {"outdir": str(tmp_path / "out"), "workflow": {"include_nodes": ["qc"]}}
        plan = build_plan_from_dag(dag_path, config, ctx)
        tool_ids = {s.tool_id for s in plan.steps}
        assert tool_ids == {"qc"}


# ====================================================================
# 8. PathTemplateContext with upstream_outputs
# ====================================================================


class TestPathTemplateContextUpstream:
    def test_upstream_outputs_context_keys(self):
        ctx = PathTemplateContext(
            config={"outdir": "/out"},
            upstream_outputs={
                "qc": {"clean_read1": "/out/01_qc/S1/clean_R1.fq"},
            },
        )
        assert ctx["upstream_qc.outputs.clean_read1"] == "/out/01_qc/S1/clean_R1.fq"

    def test_multiple_upstream_keys(self):
        ctx = PathTemplateContext(
            config={"outdir": "/out"},
            upstream_outputs={
                "qc": {"clean": "/out/qc/clean.fq"},
                "assembly": {"contigs": "/out/assembly/contigs.fa"},
            },
        )
        assert ctx["upstream_qc.outputs.clean"] == "/out/qc/clean.fq"
        assert ctx["upstream_assembly.outputs.contigs"] == "/out/assembly/contigs.fa"

    def test_upstream_outputs_with_sample_in_template(self):
        ctx = PathTemplateContext(
            config={"outdir": "/out"},
            sample=SampleInput(sample_id="S1", platform="illumina"),
            category_dir="02_assembly",
            upstream_outputs={"qc": {"clean": "/out/qc/S1/clean.fq"}},
        )
        result = "{outdir}/{category_dir}/{sample_id}.fa".format_map(ctx)
        assert result == "/out/02_assembly/S1.fa"


# ====================================================================
# 9. Edge cases
# ====================================================================


class TestEdgeCases:
    def test_from_yaml_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            UniversalDAG.from_yaml(tmp_path / "nonexistent.yaml")

    def test_from_yaml_non_mapping_spec(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            UniversalDAG.from_yaml(bad)

    def test_construct_no_nodes_raises(self):
        with pytest.raises(ValueError, match="nodes.*mapping"):
            UniversalDAG({})

    def test_topological_order_preserves_level_order(self):
        spec = {
            "nodes": {
                "Z": {"platforms": ["illumina"], "category": "z"},
                "A": {"platforms": ["illumina"], "category": "a"},
                "B": {"platforms": ["illumina"], "category": "b"},
            }
        }
        dag = UniversalDAG(spec)
        order = dag.topological_order(["Z", "A", "B"])
        assert order == ["Z", "A", "B"]

    def test_topological_order_with_resolved_edges(self):
        spec = {
            "nodes": {
                "A": {"platforms": ["illumina"], "category": "a"},
                "B": {"platforms": ["illumina"], "category": "b", "depends_on": ["A"]},
            }
        }
        dag = UniversalDAG(spec)
        order = dag.topological_order({"B": ["A"], "A": []})
        assert order == ["A", "B"]

    def test_scope_for_defaults_per_sample(self):
        spec = {"nodes": {"n": {"platforms": ["illumina"], "category": "qc"}}}
        dag = UniversalDAG(spec)
        assert dag.scope_for("n") == "per_sample"

    def test_scope_for_missing_node_defaults(self):
        dag = UniversalDAG({"nodes": {}})
        assert dag.scope_for("nonexistent") == "per_sample"

    def test_is_optional_missing_node_false(self):
        dag = UniversalDAG({"nodes": {}})
        assert dag.is_optional("nonexistent") is False

    def test_node_category_missing_node_empty(self):
        dag = UniversalDAG({"nodes": {}})
        assert dag.node_category("nonexistent") == ""
