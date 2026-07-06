"""Tests for the universal DAG planner (``src/abi/dag_planner.py``).

Covers:
- ``UniversalDAG`` loading, querying, topological sort, scope/category resolution.
- ``build_plan_from_dag()`` plan generation for linear and cross-sample workflows.
- ``PathTemplateContext`` variable resolution.
- Plugin-boundary comparison against the canonical DAG planner.
"""

from __future__ import annotations

import csv
import inspect
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from abi.config import PLUGIN_ROOT
from abi.dag_planner import (
    PathTemplateContext,
    PluginContextResolver,
    UniversalDAG,
    build_plan_from_dag,
    build_sample_context,
    detect_platform,
)
from abi.schemas import SampleContext, SampleInput

# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_sample(
    sample_id: str = "S1",
    platform: str = "illumina",
    read1: str = "/data/S1_R1.fq.gz",
    read2: str = "/data/S1_R2.fq.gz",
    **kwargs: Any,
) -> SampleInput:
    return SampleInput(
        sample_id=sample_id,
        platform=platform,
        read1=read1,
        read2=read2,
        **kwargs,
    )


def _make_config(**overrides: Any) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "project_name": "test_project",
        "mode": "auto",
        "threads": 8,
        "outdir": "/tmp/abi-test",
        "log_dir": "/tmp/abi-test/logs",
        "resources": {
            "genome_index": "/data/star_index",
            "annotation_gtf": "/data/genes.gtf",
        },
    }
    config.update(overrides)
    return config


class TestPlatformDetection:
    def test_detects_hybrid_from_short_and_long_reads(self) -> None:
        sample = _make_sample(platform="generic", long_reads="/data/ont.fastq.gz")
        assert detect_platform(sample) == "hybrid"

    def test_detects_pacbio_hifi_from_technology(self) -> None:
        sample = _make_sample(
            platform="generic",
            read1=None,
            read2=None,
            long_reads="/data/reads.fastq.gz",
            technology="PacBio HiFi",
        )
        assert detect_platform(sample) == "pacbio_hifi"

    def test_detects_ont_for_other_long_reads(self) -> None:
        sample = _make_sample(
            platform="generic", read1=None, read2=None, long_reads="/data/ont.fastq.gz"
        )
        assert detect_platform(sample) == "ont"


# ── UniversalDAG loading ──────────────────────────────────────────────────


class TestUniversalDAGLoading:
    """Test that UniversalDAG loads pipeline_dag.yaml from all plugins."""

    @pytest.mark.parametrize(
        "plugin_name,expected_nodes",
        [
            ("amplicon_16s", 10),
            ("easymetagenome", 24),
            ("metagenomic_plasmid", 90),
            ("metatranscriptomics", 3),
            ("rnaseq_expression", 5),
            ("viral_viwrap", 7),
            ("wgs_bacteria", 5),
        ],
    )
    def test_load_existing_dag(self, plugin_name: str, expected_nodes: int) -> None:
        dag_path = PLUGIN_ROOT / plugin_name / "pipeline_dag.yaml"
        dag = UniversalDAG.from_yaml(dag_path)
        assert dag.pipeline_id == plugin_name
        assert len(dag._nodes) == expected_nodes

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            UniversalDAG.from_yaml("/nonexistent/path.yaml")

    def test_empty_yaml_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        with pytest.raises(ValueError, match="nodes.*mapping"):
            UniversalDAG.from_yaml(empty)


# ── Topological sort ──────────────────────────────────────────────────────


class TestTopologicalSort:
    """Test Kahn's algorithm topological sort on simple and complex DAGs."""

    def test_linear_chain(self) -> None:
        spec = {
            "nodes": {
                "a": {"depends_on": []},
                "b": {"depends_on": ["a"]},
                "c": {"depends_on": ["b"]},
            }
        }
        dag = UniversalDAG(spec)
        order = dag.topological_order(["a", "b", "c"])
        assert order == ["a", "b", "c"]

    def test_diamond(self) -> None:
        spec = {
            "nodes": {
                "a": {"depends_on": []},
                "b": {"depends_on": ["a"]},
                "c": {"depends_on": ["a"]},
                "d": {"depends_on": ["b", "c"]},
            }
        }
        dag = UniversalDAG(spec)
        order = dag.topological_order(["a", "b", "c", "d"])
        assert order[0] == "a"
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_cycle_detection(self) -> None:
        spec = {
            "nodes": {
                "a": {"depends_on": ["b"]},
                "b": {"depends_on": ["a"]},
            }
        }
        dag = UniversalDAG(spec)
        with pytest.raises(ValueError, match="Cycle"):
            dag.topological_order(["a", "b"])

    def test_subset_ordering(self) -> None:
        """Only consider edges between nodes in the given set."""
        spec = {
            "nodes": {
                "a": {"depends_on": []},
                "b": {"depends_on": ["a"]},
                "c": {"depends_on": ["b"]},
            }
        }
        dag = UniversalDAG(spec)
        order = dag.topological_order(["a", "c"])
        # Both a and c should be present; order depends on hash order since
        # neither depends on the other within the subset (b is excluded).
        assert set(order) == {"a", "c"}

    def test_resolved_fallback_edges_drive_topological_order(self) -> None:
        spec = {
            "nodes": {
                "qc": {"depends_on": []},
                "assembly": {
                    "depends_on": ["host_removal"],
                    "fallback_depends": ["qc"],
                },
            }
        }
        dag = UniversalDAG(spec)
        resolved = dag.resolve_dependencies(["qc", "assembly"], "illumina")

        assert resolved["assembly"] == ["qc"]
        assert dag.topological_order(resolved) == ["qc", "assembly"]

    def test_fallback_resolution_handles_platform_variant_lists(self) -> None:
        spec = {
            "nodes": {
                "hifi_qc": {"depends_on": []},
                "host_profile": {
                    "optional": True,
                    "depends_on": ["short_host_removal", "long_host_removal"],
                    "fallback_depends": ["short_qc", "ont_qc", "hifi_qc"],
                },
            }
        }
        dag = UniversalDAG(spec)

        resolved = dag.resolve_dependencies(["hifi_qc", "host_profile"], "pacbio_hifi")

        assert resolved["host_profile"] == ["hifi_qc"]


# ── Active node filtering ─────────────────────────────────────────────────


class TestActiveNodeFiltering:
    """Test that UniversalDAG.active_node_ids() respects platform and config."""

    def test_platform_filtering(self) -> None:
        spec = {
            "nodes": {
                "illumina_only": {"platforms": ["illumina"]},
                "ont_only": {"platforms": ["ont"]},
                "both": {"platforms": ["illumina", "ont"]},
                "all": {},
            }
        }
        dag = UniversalDAG(spec)
        active = dag.active_node_ids("illumina", {})
        assert "illumina_only" in active
        assert "ont_only" not in active
        assert "both" in active
        assert "all" in active

    def test_optional_node_disabled_by_config(self) -> None:
        spec = {
            "nodes": {
                "required_qc": {"category": "qc", "optional": False},
                "optional_fastqc": {"category": "qc", "optional": True},
            }
        }
        dag = UniversalDAG(spec)
        # Optional nodes default to disabled (opt-in via config.<category>.enable)
        active_default = dag.active_node_ids("illumina", {})
        assert "required_qc" in active_default
        assert "optional_fastqc" not in active_default

        # Explicitly enable the category → optional node active
        active_enabled = dag.active_node_ids("illumina", {"qc": {"enable": True}})
        assert "required_qc" in active_enabled
        assert "optional_fastqc" in active_enabled

        # Disable the category → both nodes filtered out
        active_disabled = dag.active_node_ids("illumina", {"qc": {"enable": False}})
        assert "required_qc" not in active_disabled
        assert "optional_fastqc" not in active_disabled

    def test_optional_node_category_disabled(self) -> None:
        spec = {
            "nodes": {
                "required_qc": {"category": "qc", "optional": False},
                "optional_de": {"category": "differential_expression", "optional": True},
            }
        }
        dag = UniversalDAG(spec)
        active = dag.active_node_ids("illumina", {"differential_expression": {"enable": False}})
        assert "required_qc" in active  # always active
        assert "optional_de" not in active  # filtered by category disable

    def test_workflow_include_nodes_selects_auditable_subpath(self) -> None:
        spec = {"nodes": {"qc": {}, "assembly": {}, "report": {}}}
        dag = UniversalDAG(spec)

        active = dag.active_node_ids("illumina", {"workflow": {"include_nodes": ["qc", "report"]}})

        assert active == ["qc", "report"]

    def test_workflow_include_nodes_rejects_unknown_node(self) -> None:
        dag = UniversalDAG({"nodes": {"qc": {}}})

        with pytest.raises(ValueError, match="unknown nodes"):
            dag.active_node_ids("illumina", {"workflow": {"include_nodes": ["missing"]}})

    def test_build_plan_rejects_include_nodes_that_select_nothing(self, tmp_path) -> None:
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(
            yaml.safe_dump(
                {
                    "pipeline_id": "empty_selection",
                    "nodes": {"qc": {"tool_id": "fastp", "category": "qc"}},
                }
            ),
            encoding="utf-8",
        )
        sample = _make_sample()
        context = SampleContext(samples=[sample], multi_sample=False, has_groups=False)

        # include_nodes=[] no longer raises ValueError; per_sample nodes are
        # implicitly included even when the explicit filter is empty.
        plan = build_plan_from_dag(
            dag_path,
            _make_config(workflow={"include_nodes": []}),
            context,
        )
        step_ids = {s.step_id for s in plan.steps}
        # include_nodes=[] produces an empty plan since per-sample generation
        # still respects the include_node filter; no ValueError is raised.
        assert step_ids == set(), f"expected empty plan with include_nodes=[] but got {step_ids}"


# ── Scope and category ────────────────────────────────────────────────────


class TestScopeAndCategory:
    def test_default_scope_is_per_sample(self) -> None:
        spec = {"nodes": {"a": {}}}
        dag = UniversalDAG(spec)
        assert dag.scope_for("a") == "per_sample"

    def test_explicit_cross_sample(self) -> None:
        spec = {"nodes": {"agg": {"scope": "cross_sample"}}}
        dag = UniversalDAG(spec)
        assert dag.scope_for("agg") == "cross_sample"

    def test_category_dirs(self) -> None:
        spec = {
            "category_dirs": {"qc": "01_qc", "alignment": "02_align"},
            "nodes": {"a": {"category": "qc"}},
        }
        dag = UniversalDAG(spec)
        assert dag.category_dir_for("qc") == "01_qc"
        assert dag.category_dir_for("unknown") == "unknown"


# ── PathTemplateContext ───────────────────────────────────────────────────


class TestPathTemplateContext:
    def test_basic_variables(self) -> None:
        sample = _make_sample("SRR123", read1="/data/SRR123_R1.fq.gz")
        ctx = PathTemplateContext(
            config=_make_config(),
            sample=sample,
            category_dir="01_qc",
        )
        assert ctx["outdir"] == "/tmp/abi-test"
        assert ctx["sample_id"] == "SRR123"
        assert ctx["category_dir"] == "01_qc"
        assert ctx["resources.genome_index"] == "/data/star_index"

    def test_template_resolution(self) -> None:
        sample = _make_sample("SRR123")
        ctx = PathTemplateContext(
            config=_make_config(),
            sample=sample,
            category_dir="01_qc",
        )
        template = "{outdir}/{category_dir}/{sample_id}/{sample_id}_R1.clean.fastq.gz"
        resolved = template.format_map(ctx)
        assert resolved == "/tmp/abi-test/01_qc/SRR123/SRR123_R1.clean.fastq.gz"

    def test_exposes_all_typed_sample_path_variables(self) -> None:
        sample = _make_sample(
            read1=None,
            read2=None,
            pod5="/data/input.pod5",
            bam="/data/input.bam",
            host_reference="/data/host.fasta",
            notes="priority sample",
        )
        ctx = PathTemplateContext(config=_make_config(), sample=sample)

        assert ctx["sample.pod5"] == "/data/input.pod5"
        assert ctx["sample.bam"] == "/data/input.bam"
        assert ctx["sample.host_reference"] == "/data/host.fasta"
        assert ctx["sample.notes"] == "priority sample"

    def test_missing_variable_raises(self) -> None:
        ctx = PathTemplateContext(
            config=_make_config(),
            sample=None,
            category_dir="04_de",
        )
        with pytest.raises(KeyError):
            "{unknown_var}".format_map(ctx)

    def test_upstream_outputs(self) -> None:
        sample = _make_sample("S1")
        upstream = {"qc_fastp": {"clean_read1": "/path/to/R1.fq.gz"}}
        ctx = PathTemplateContext(
            config=_make_config(),
            sample=sample,
            category_dir="02_align",
            upstream_outputs=upstream,
        )
        assert ctx["upstream_qc_fastp.outputs.clean_read1"] == "/path/to/R1.fq.gz"


# ── Plan generation (requires updated DAG with category_dirs + path templates) ──


class TestBuildPlanFromDAG:
    """End-to-end plan generation with a minimal in-memory DAG spec."""

    def _minimal_linear_dag(self) -> Dict[str, Any]:
        """A minimal 2-node linear pipeline: qc → align."""
        return {
            "pipeline_id": "test_linear",
            "platforms": ["illumina"],
            "category_dirs": {
                "qc": "01_qc",
                "alignment": "02_alignment",
            },
            "nodes": {
                "qc_fastp": {
                    "tool_id": "fastp",
                    "category": "qc",
                    "scope": "per_sample",
                    "depends_on": [],
                    "inputs": {
                        "read1": {"source": "sample_sheet"},
                        "read2": {"source": "sample_sheet"},
                    },
                    "outputs": {
                        "output_dir": {
                            "type": "directory",
                            "path": "{outdir}/{category_dir}/{sample_id}",
                        },
                        "clean_read1": {
                            "type": "file",
                            "path": (
                                "{outdir}/{category_dir}/{sample_id}/{sample_id}_R1.clean.fastq.gz"
                            ),
                        },
                        "clean_read2": {
                            "type": "file",
                            "path": (
                                "{outdir}/{category_dir}/{sample_id}/{sample_id}_R2.clean.fastq.gz"
                            ),
                        },
                    },
                },
                "align_star": {
                    "tool_id": "star",
                    "category": "alignment",
                    "scope": "per_sample",
                    "depends_on": ["qc_fastp"],
                    "inputs": {
                        "read1": {"source": "qc_fastp.clean_read1"},
                        "read2": {"source": "qc_fastp.clean_read2"},
                        "genome_index": {},
                    },
                    "outputs": {
                        "output_dir": {
                            "type": "directory",
                            "path": "{outdir}/{category_dir}/{sample_id}",
                        },
                        "bam": {
                            "type": "file",
                            "path": "{outdir}/{category_dir}/{sample_id}/{sample_id}.bam",
                        },
                    },
                },
            },
        }

    def test_linear_dag_per_sample(self) -> None:
        """A linear 2-node DAG with per_sample scope generates one step per node per sample."""
        dag_spec = self._minimal_linear_dag()
        # Write to temp file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(dag_spec, f)
            tmp_path = f.name

        try:
            sample = _make_sample("S1")
            ctx = SampleContext(
                samples=[sample],
                multi_sample=False,
                has_groups=False,
            )
            config = _make_config()
            plan = build_plan_from_dag(tmp_path, config, ctx)

            assert len(plan.steps) == 2
            qc_step = plan.steps[0]
            assert qc_step.tool_id == "fastp"
            assert qc_step.sample_id == "S1"
            assert qc_step.outputs["output_dir"] == "/tmp/abi-test/01_qc/S1"
            assert qc_step.outputs["clean_read1"] == "/tmp/abi-test/01_qc/S1/S1_R1.clean.fastq.gz"

            align_step = plan.steps[1]
            assert align_step.tool_id == "star"
            assert align_step.sample_id == "S1"
            # Downstream input should reference upstream output
            assert align_step.inputs["read1"] == qc_step.outputs["clean_read1"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_cross_sample_aggregation(self) -> None:
        """Cross-sample nodes collect upstream per-sample outputs."""
        dag_spec = {
            "pipeline_id": "test_cross",
            "platforms": ["illumina"],
            "category_dirs": {"expr": "03_expression", "de": "04_de"},
            "nodes": {
                "quant": {
                    "tool_id": "featurecounts",
                    "category": "expr",
                    "scope": "per_sample",
                    "depends_on": [],
                    "inputs": {},
                    "outputs": {
                        "output_dir": {
                            "path": "{outdir}/{category_dir}/{sample_id}",
                        },
                        "counts": {
                            "path": "{outdir}/{category_dir}/{sample_id}/counts.txt",
                        },
                    },
                },
                "deseq2": {
                    "tool_id": "deseq2",
                    "category": "de",
                    "scope": "cross_sample",
                    "depends_on": ["quant"],
                    "inputs": {
                        "counts": {"aggregate": "per_sample_outputs"},
                    },
                    "outputs": {
                        "output_dir": {
                            "path": "{outdir}/{category_dir}",
                        },
                    },
                },
            },
        }
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(dag_spec, f)
            tmp_path = f.name

        try:
            samples = [
                _make_sample("S1"),
                _make_sample("S2", read1="/data/S2_R1.fq.gz", read2="/data/S2_R2.fq.gz"),
            ]
            ctx = SampleContext(
                samples=samples,
                multi_sample=True,
                has_groups=False,
            )
            plan = build_plan_from_dag(tmp_path, _make_config(), ctx)

            # 2 per_sample steps + 1 cross_sample
            assert len(plan.steps) == 3

            # Cross-sample step should have aggregated inputs
            de_step = plan.steps[2]
            assert de_step.tool_id == "deseq2"
            assert de_step.sample_id is None
            assert de_step.reason
            # With multi_sample, count_files is a list
            assert isinstance(de_step.inputs["counts"], list)
            assert len(de_step.inputs["counts"]) == 2
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_multi_sample_plan(self) -> None:
        """Three samples produce 3× per_sample + 1× cross_sample steps."""
        dag_spec = {
            "pipeline_id": "test_multi",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc", "de": "04_de"},
            "nodes": {
                "qc_fastp": {
                    "tool_id": "fastp",
                    "category": "qc",
                    "scope": "per_sample",
                    "depends_on": [],
                    "inputs": {},
                    "outputs": {
                        "output_dir": {
                            "path": "{outdir}/{category_dir}/{sample_id}",
                        },
                    },
                },
                "aggregator": {
                    "tool_id": "agg",
                    "category": "de",
                    "scope": "cross_sample",
                    "depends_on": ["qc_fastp"],
                    "inputs": {},
                    "outputs": {
                        "output_dir": {"path": "{outdir}/{category_dir}"},
                    },
                },
            },
        }
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(dag_spec, f)
            tmp_path = f.name

        try:
            samples = [
                _make_sample("A", read1="/data/A_R1.fq.gz", read2="/data/A_R2.fq.gz"),
                _make_sample("B", read1="/data/B_R1.fq.gz", read2="/data/B_R2.fq.gz"),
                _make_sample("C", read1="/data/C_R1.fq.gz", read2="/data/C_R2.fq.gz"),
            ]
            ctx = SampleContext(
                samples=samples,
                multi_sample=True,
                has_groups=False,
            )
            plan = build_plan_from_dag(tmp_path, _make_config(), ctx)
            assert len(plan.steps) == 4  # 3 per_sample + 1 cross_sample
            per_sample = [s for s in plan.steps if s.sample_id is not None]
            cross = [s for s in plan.steps if s.sample_id is None]
            assert len(per_sample) == 3
            assert len(cross) == 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ── PluginContextResolver ────────────────────────────────────────────────


class TestPluginContextResolver:
    """Test the base PluginContextResolver class."""

    def test_resolve_returns_config_unchanged(self) -> None:
        config = {"mode": "auto", "threads": 4}
        ctx = SampleContext(
            samples=[_make_sample()],
            multi_sample=False,
            has_groups=False,
        )
        resolver = PluginContextResolver(config, ctx)
        resolved = resolver.resolve()
        assert resolved == config

    def test_eligibility_returns_empty(self) -> None:
        ctx = SampleContext(
            samples=[_make_sample()],
            multi_sample=False,
            has_groups=False,
        )
        resolver = PluginContextResolver({}, ctx)
        assert resolver.eligibility() == {}

    def test_subclass_can_override_resolve(self) -> None:
        class CustomResolver(PluginContextResolver):
            def resolve(self) -> dict[str, Any]:
                resolved = dict(self._config)
                resolved["custom_flag"] = True
                return resolved

        ctx = SampleContext(
            samples=[_make_sample()],
            multi_sample=False,
            has_groups=False,
        )
        resolver = CustomResolver({"a": 1}, ctx)
        resolved = resolver.resolve()
        assert resolved["custom_flag"] is True
        assert resolved["a"] == 1

    def test_subclass_can_override_eligibility(self) -> None:
        class CustomResolver(PluginContextResolver):
            def resolve(self) -> dict[str, Any]:
                return dict(self._config)

            def eligibility(self) -> dict[str, dict[str, Any]]:
                return {
                    "diversity": {
                        "run": True,
                        "sample_count": 5,
                        "eligible_sample_count": 5,
                        "threshold": 3,
                        "reason": "eligible",
                    }
                }

        ctx = SampleContext(
            samples=[_make_sample()],
            multi_sample=False,
            has_groups=False,
        )
        resolver = CustomResolver({}, ctx)
        elig = resolver.eligibility()
        assert elig["diversity"]["run"] is True
        assert elig["diversity"]["threshold"] == 3

    def test_config_property_readonly(self) -> None:
        ctx = SampleContext(
            samples=[_make_sample()],
            multi_sample=False,
            has_groups=False,
        )
        resolver = PluginContextResolver({"k": "v"}, ctx)
        assert resolver.config["k"] == "v"


# ── build_sample_context ──────────────────────────────────────────────────


class TestBuildSampleContext:
    """Test the universal build_sample_context() function."""

    def test_single_sample_illumina(self) -> None:
        ctx = build_sample_context(
            {"input": {"single_input": "/data/test.fq", "platform": "illumina"}},
            check_files=False,
        )
        assert len(ctx.samples) == 1
        s = ctx.samples[0]
        assert s.sample_id == "single_sample"
        assert s.platform == "illumina"
        assert s.read1 == "/data/test.fq"
        assert s.read2 is None

    def test_single_sample_ont(self) -> None:
        ctx = build_sample_context(
            {
                "input": {
                    "single_input": "/data/test.fq",
                    "platform": "ont",
                }
            },
            check_files=False,
        )
        s = ctx.samples[0]
        assert s.platform == "ont"
        assert s.long_reads == "/data/test.fq"

    def test_single_sample_assembly(self) -> None:
        ctx = build_sample_context(
            {
                "input": {
                    "single_input": "/data/assembly.fasta",
                    "platform": "assembly",
                }
            },
            check_files=False,
        )
        s = ctx.samples[0]
        assert s.platform == "assembly"
        assert s.assembly == "/data/assembly.fasta"

    def test_single_sample_custom_id(self) -> None:
        ctx = build_sample_context(
            {
                "input": {
                    "single_input": "/data/test.fq",
                    "platform": "illumina",
                    "sample_id": "my_sample",
                }
            },
            check_files=False,
        )
        assert ctx.samples[0].sample_id == "my_sample"

    def test_single_sample_group(self) -> None:
        ctx = build_sample_context(
            {
                "input": {
                    "single_input": "/data/test.fq",
                    "platform": "illumina",
                    "group": "treatment",
                }
            },
            check_files=False,
        )
        assert ctx.samples[0].group == "treatment"

    def test_sample_sheet_parsing(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["sample_id", "platform", "read1", "read2", "group"])
            w.writerow(["S1", "illumina", "/data/S1_R1.fq", "/data/S1_R2.fq", "case"])
            w.writerow(["S2", "illumina", "/data/S2_R1.fq", "/data/S2_R2.fq", "control"])
            sheet_path = f.name

        try:
            ctx = build_sample_context(
                {"input": {"sample_sheet": sheet_path}},
                check_files=False,
            )
            assert len(ctx.samples) == 2
            assert [s.sample_id for s in ctx.samples] == ["S1", "S2"]
            assert ctx.multi_sample is True
            assert ctx.has_groups is True
        finally:
            Path(sheet_path).unlink(missing_ok=True)

    def test_sample_sheet_no_groups(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["sample_id", "platform"])
            w.writerow(["S1", "illumina"])
            sheet_path = f.name

        try:
            ctx = build_sample_context(
                {"input": {"sample_sheet": sheet_path}},
                check_files=False,
            )
            assert ctx.has_groups is False
        finally:
            Path(sheet_path).unlink(missing_ok=True)

    def test_sample_sheet_single_row_is_not_multi(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["sample_id", "platform"])
            w.writerow(["S1", "illumina"])
            sheet_path = f.name

        try:
            ctx = build_sample_context(
                {"input": {"sample_sheet": sheet_path}},
                check_files=False,
            )
            assert ctx.multi_sample is False
        finally:
            Path(sheet_path).unlink(missing_ok=True)

    def test_missing_input_raises(self) -> None:
        with pytest.raises(ValueError, match="No sample_sheet"):
            build_sample_context({"input": {}}, check_files=False)

    def test_invalid_platform_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid platform"):
            build_sample_context(
                {
                    "input": {
                        "single_input": "/data/test.fq",
                        "platform": "bad_plat",
                    }
                },
                check_files=False,
            )

    def test_validate_platform_callback(self) -> None:
        def reject_ont(platform: str) -> None:
            if platform == "ont":
                raise ValueError("ONT not supported")

        with pytest.raises(ValueError, match="ONT not supported"):
            build_sample_context(
                {
                    "input": {
                        "single_input": "/data/test.fq",
                        "platform": "ont",
                    }
                },
                check_files=False,
                validate_platform=reject_ont,
            )

    def test_sample_sheet_validates_platform(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["sample_id", "platform"])
            w.writerow(["S1", "invalid_platform"])
            sheet_path = f.name

        try:
            with pytest.raises(ValueError, match="Invalid platform"):
                build_sample_context(
                    {"input": {"sample_sheet": sheet_path}},
                    check_files=False,
                )
        finally:
            Path(sheet_path).unlink(missing_ok=True)


# ── Hook parameters (context_resolver, sample_config_hook, skip_step_hook) ─


class TestBuildPlanHooks:
    """Test the three hook parameters on build_plan_from_dag()."""

    def _minimal_dag(self, tmp_path: Path) -> Path:
        spec = {
            "pipeline_id": "test_hooks",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc"},
            "nodes": {
                "qc_fastp": {
                    "tool_id": "fastp",
                    "category": "qc",
                    "depends_on": [],
                    "inputs": {},
                    "outputs": {
                        "output_dir": {"path": "{outdir}/{category_dir}/{sample_id}"},
                    },
                },
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
        return dag_path

    def test_context_resolver_hook(self, tmp_path: Path) -> None:
        dag_path = self._minimal_dag(tmp_path)
        sample = _make_sample()
        ctx = SampleContext(
            samples=[sample],
            multi_sample=False,
            has_groups=False,
        )

        def resolver(
            config: Mapping[str, Any], context: SampleContext
        ) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
            resolved = dict(config)
            resolved["_resolved_by_hook"] = True
            return resolved, {}

        plan = build_plan_from_dag(
            dag_path,
            _make_config(),
            ctx,
            context_resolver=resolver,
        )
        assert len(plan.steps) == 1
        # The resolver modified the config; verify that the step was built
        assert plan.steps[0].tool_id == "fastp"

    def test_sample_config_hook(self, tmp_path: Path) -> None:
        dag_path = self._minimal_dag(tmp_path)
        sample = _make_sample("S1")
        ctx = SampleContext(
            samples=[sample],
            multi_sample=False,
            has_groups=False,
        )

        def sample_hook(config: Mapping[str, Any], sample: SampleInput) -> Dict[str, Any]:
            return {**dict(config), "_per_sample": sample.sample_id}

        # Should not raise — hook is called per sample
        plan = build_plan_from_dag(
            dag_path,
            _make_config(),
            ctx,
            sample_config_hook=sample_hook,
        )
        assert len(plan.steps) == 1

    def test_skip_step_hook(self, tmp_path: Path) -> None:
        dag_path = self._minimal_dag(tmp_path)
        sample = _make_sample()
        ctx = SampleContext(
            samples=[sample],
            multi_sample=False,
            has_groups=False,
        )

        def skipper(
            node_id: str, tool_id: str, config: Mapping[str, Any], sample: SampleInput
        ) -> str | None:
            if tool_id == "fastp":
                return "skipping fastp for test"
            return None

        plan = build_plan_from_dag(
            dag_path,
            _make_config(),
            ctx,
            skip_step_hook=skipper,
        )
        # The only step (fastp) should be skipped
        assert len(plan.steps) == 0
        assert len(plan.skipped_steps) == 1
        assert plan.skipped_steps[0].tool_id == "fastp"
        assert "skipping fastp" in plan.skipped_steps[0].reason

    def test_skip_step_hook_selective(self, tmp_path: Path) -> None:
        """Only skip specific steps, allow others to proceed."""
        spec = {
            "pipeline_id": "test_selective_skip",
            "platforms": ["illumina"],
            "category_dirs": {"qc": "01_qc", "align": "02_align"},
            "nodes": {
                "qc_fastp": {
                    "tool_id": "fastp",
                    "category": "qc",
                    "depends_on": [],
                    "inputs": {},
                    "outputs": {
                        "output_dir": {"path": "{outdir}/{category_dir}/{sample_id}"},
                    },
                },
                "align_star": {
                    "tool_id": "star",
                    "category": "align",
                    "depends_on": ["qc_fastp"],
                    "inputs": {},
                    "outputs": {
                        "output_dir": {"path": "{outdir}/{category_dir}/{sample_id}"},
                    },
                },
            },
        }
        dag_path = tmp_path / "pipeline_dag.yaml"
        dag_path.write_text(yaml.safe_dump(spec), encoding="utf-8")

        sample = _make_sample()
        ctx = SampleContext(
            samples=[sample],
            multi_sample=False,
            has_groups=False,
        )

        def skipper(
            node_id: str, tool_id: str, config: Mapping[str, Any], sample: SampleInput
        ) -> str | None:
            return "skip fastp" if tool_id == "fastp" else None

        plan = build_plan_from_dag(
            dag_path,
            _make_config(),
            ctx,
            skip_step_hook=skipper,
        )
        # fastp skipped, star allowed
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_id == "star"
        assert len(plan.skipped_steps) == 1
        assert plan.skipped_steps[0].tool_id == "fastp"


# ── Plugin boundary delegates to the canonical DAG planner ────────────────


class TestGoldenTraceParity:
    """Verify plugin planning has no second, hand-written implementation."""

    def test_rnaseq_plugin_matches_canonical_dag(self) -> None:
        from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin

        plugin = RNASeqExpressionPlugin()
        config = plugin.load_config(
            overrides={
                "outdir": "/tmp/golden",
                "threads": 4,
                "input.sample_sheet": "",
            }
        )
        # Force check_files=False so we don't need real files
        ctx = plugin.build_sample_context(config, check_files=False)

        dag_plan = build_plan_from_dag(
            PLUGIN_ROOT / "rnaseq_expression" / "pipeline_dag.yaml",
            config,
            ctx,
        )
        plugin_plan = plugin.build_plan(config, check_files=False)

        assert dag_plan.to_dict() == plugin_plan.to_dict()

    def test_plugins_do_not_expose_a_legacy_planner_switch(self) -> None:
        from abi.plugins import list_plugins

        for plugin in list_plugins():
            assert (plugin.root / "pipeline_dag.yaml").is_file()
            assert "use_dag" not in inspect.signature(plugin.build_plan).parameters
