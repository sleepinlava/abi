"""Tests for the universal DAG planner (``src/abi/dag_planner.py``).

Covers:
- ``UniversalDAG`` loading, querying, topological sort, scope/category resolution.
- ``build_plan_from_dag()`` plan generation for linear and cross-sample workflows.
- ``PathTemplateContext`` variable resolution.
- Golden-trace comparison: DAG-generated plan vs hand-written plugin plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from abi.config import PLUGIN_ROOT
from abi.dag_planner import (
    PathTemplateContext,
    UniversalDAG,
    build_plan_from_dag,
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


# ── UniversalDAG loading ──────────────────────────────────────────────────


class TestUniversalDAGLoading:
    """Test that UniversalDAG loads pipeline_dag.yaml from all plugins."""

    @pytest.mark.parametrize(
        "plugin_name,expected_nodes",
        [
            ("rnaseq_expression", 5),
            ("wgs_bacteria", 5),
            ("amplicon_16s", 8),
        ],
    )
    def test_load_existing_dag(self, plugin_name: str, expected_nodes: int) -> None:
        dag_path = PLUGIN_ROOT / plugin_name / "pipeline_dag.yaml"
        dag = UniversalDAG.from_yaml(dag_path)
        assert dag.pipeline_id == plugin_name
        assert len(dag._nodes) == expected_nodes

    def test_load_plasmid_dag(self) -> None:
        """The plasmid DAG is large (84 nodes); verify it loads without error."""
        dag_path = PLUGIN_ROOT / "metagenomic_plasmid" / "pipeline_dag.yaml"
        dag = UniversalDAG.from_yaml(dag_path)
        assert dag.pipeline_id == "metagenomic_plasmid"
        assert len(dag._nodes) >= 80

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
            assert de_step.sample_id == "ALL"
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
            per_sample = [s for s in plan.steps if s.sample_id != "ALL"]
            cross = [s for s in plan.steps if s.sample_id == "ALL"]
            assert len(per_sample) == 3
            assert len(cross) == 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ── Golden-trace: DAG plan ≈ hand-written plugin plan ─────────────────────


class TestGoldenTraceParity:
    """Verify that DAG-generated plans match hand-written plugin build_plan().

    These tests require the DAG YAML to be updated with category_dirs, scope,
    and path templates.  They are skipped until the DAG files are updated
    (Task 35 in the uv-ification plan).
    """

    @pytest.mark.skip(reason="DAG YAML not yet updated with scope + path templates")
    def test_rnaseq_dag_matches_handwritten(self) -> None:
        """Compare DAG plan vs rnaseq_expression.build_plan()."""
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
        hand_plan = plugin.build_plan(config, check_files=False)

        assert len(dag_plan.steps) == len(hand_plan.steps)
        for ds, hs in zip(dag_plan.steps, hand_plan.steps):
            assert ds.tool_id == hs.tool_id
            # Output paths may differ; focus on structural parity
            assert ds.sample_id == hs.sample_id
            assert ds.category == hs.category
