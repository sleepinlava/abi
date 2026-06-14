"""Unit tests for PipelineDAG — spec loading, platform filtering, dependency
resolution, and topological ordering."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the source tree is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from abi.plugins.metagenomic_plasmid._engine.pipeline_dag import (
    PipelineDAG,
    _evaluate_condition,
)

# ── Minimal DAG spec for testing ─────────────────────────────────────────

MINIMAL_SPEC = {
    "platforms": ["illumina", "ont", "hybrid"],
    "nodes": {
        "qc_trim": {
            "tool_id": "fastp",
            "category": "qc",
            "platforms": ["illumina", "hybrid"],
            "optional": False,
            "depends_on": [],
            "inputs": {"read1": {"type": "file", "source": "sample_sheet"}},
            "outputs": {"clean_reads": {"type": "file"}},
        },
        "qc_plot": {
            "tool_id": "nanoplot",
            "category": "qc",
            "platforms": ["ont", "hybrid"],
            "optional": True,
            "depends_on": [],
            "inputs": {"long_reads": {"type": "file"}},
            "outputs": {"report": {"type": "directory"}},
        },
        "host_filter": {
            "tool_id": "bowtie2",
            "category": "host_removal",
            "platforms": ["illumina", "hybrid"],
            "optional": True,
            "enable_condition": {"field": "host_removal.host_reference", "operator": "not_empty"},
            "depends_on": ["qc_trim"],
            "inputs": {"reads": {"type": "file", "source": "qc_trim.clean_reads"}},
            "outputs": {"clean_reads": {"type": "file"}},
        },
        "assemble": {
            "tool_id": "megahit",
            "category": "assembly",
            "platforms": ["illumina", "hybrid"],
            "optional": False,
            "depends_on": ["host_filter"],
            "fallback_depends": ["qc_trim"],
            "inputs": {
                "reads": {
                    "type": "file",
                    "source": "host_filter.clean_reads",
                    "fallback": "qc_trim.clean_reads",
                }
            },
            "outputs": {"contigs": {"type": "file"}},
        },
        "detect": {
            "tool_id": "genomad",
            "category": "plasmid_detection",
            "platforms": ["illumina", "hybrid"],
            "optional": False,
            "depends_on": ["assemble"],
            "inputs": {"assembly": {"type": "file", "source": "assemble.contigs"}},
            "outputs": {"plasmids": {"type": "file"}},
        },
        "annotate_extra": {
            "tool_id": "plasme",
            "category": "plasmid_detection",
            "platforms": ["illumina", "hybrid"],
            "optional": True,
            "depends_on": ["assemble"],
            "inputs": {"assembly": {"type": "file", "source": "assemble.contigs"}},
            "outputs": {"results": {"type": "file"}},
        },
        "annotate": {
            "tool_id": "bakta",
            "category": "annotation",
            "platforms": ["illumina", "hybrid"],
            "optional": False,
            "depends_on": ["detect", "annotate_extra"],
            "fallback_depends": ["detect", "detect"],
            "inputs": {"plasmids": {"type": "file", "source": "detect.plasmids"}},
            "outputs": {"annotations": {"type": "file"}},
        },
        "report": {
            "tool_id": "report_markdown",
            "category": "report",
            "platforms": ["illumina", "ont", "hybrid"],
            "optional": False,
            "depends_on": ["annotate", "detect"],
            "inputs": {"outdir": {"type": "directory"}},
            "outputs": {"report_md": {"type": "file"}},
        },
    },
}


@pytest.fixture
def dag():
    return PipelineDAG(MINIMAL_SPEC)


# ── Tests: Platform filtering ────────────────────────────────────────────


class TestPlatformFiltering:
    def test_illumina_nodes(self, dag):
        nodes = dag.nodes_for_platform("illumina")
        ids = set(nodes)
        assert "qc_trim" in ids
        assert "host_filter" in ids
        assert "assemble" in ids
        assert "detect" in ids
        assert "report" in ids
        assert "qc_plot" not in ids  # ONT only

    def test_ont_nodes_are_minimal(self, dag):
        nodes = dag.nodes_for_platform("ont")
        ids = set(nodes)
        assert "qc_plot" in ids
        assert "report" in ids
        assert "qc_trim" not in ids

    def test_hybrid_nodes_include_all_platforms(self, dag):
        nodes = dag.nodes_for_platform("hybrid")
        ids = set(nodes)
        assert "qc_trim" in ids
        assert "qc_plot" in ids
        assert "report" in ids


# ── Tests: Active node resolution ────────────────────────────────────────


class TestActiveNodes:
    def test_required_nodes_always_active(self, dag):
        active = dag.active_node_ids("illumina", {"outdir": "/tmp"})
        assert "qc_trim" in active
        assert "assemble" in active
        assert "detect" in active
        assert "report" in active

    def test_optional_without_condition_excluded(self, dag):
        active = dag.active_node_ids("illumina", {"outdir": "/tmp"})
        assert "annotate_extra" not in active  # optional, no condition
        assert "qc_plot" not in active  # not on illumina anyway

    def test_optional_with_condition_met_is_active(self, dag):
        config = {"host_removal": {"host_reference": "/ref/host.fa"}}
        active = dag.active_node_ids("illumina", config)
        assert "host_filter" in active

    def test_optional_with_condition_unmet_is_excluded(self, dag):
        config = {"host_removal": {}}
        active = dag.active_node_ids("illumina", config)
        assert "host_filter" not in active


# ── Tests: Dependency resolution ─────────────────────────────────────────


class TestDependencyResolution:
    def test_direct_deps_resolve(self, dag):
        active = {"qc_trim", "assemble", "detect", "annotate", "report"}
        resolved = dag.resolve_dependencies(active, "illumina")
        assert "assemble" in resolved["detect"]
        assert "qc_trim" in resolved["assemble"]

    def test_fallback_when_optional_missing(self, dag):
        """When host_filter is disabled, assemble should fall back to qc_trim."""
        active = {"qc_trim", "assemble", "detect", "annotate", "report"}
        resolved = dag.resolve_dependencies(active, "illumina")
        assert "qc_trim" in resolved["assemble"]
        assert "host_filter" not in resolved["assemble"]

    def test_fallback_when_optional_present(self, dag):
        """When host_filter is enabled, assemble should use it."""
        active = {"qc_trim", "host_filter", "assemble", "detect", "annotate", "report"}
        resolved = dag.resolve_dependencies(active, "illumina")
        assert "host_filter" in resolved["assemble"]

    def test_positional_fallback_for_optional_annotator(self, dag):
        """annotate_extra missing → fallback to detect (position [1])."""
        active = {"qc_trim", "assemble", "detect", "annotate", "report"}
        resolved = dag.resolve_dependencies(active, "illumina")
        # annotate depends_on: [detect, annotate_extra]
        # fallback: [detect, detect] → when annotate_extra missing, use detect
        assert "detect" in resolved["annotate"]
        # detect should appear only once
        assert resolved["annotate"].count("detect") == 1

    def test_no_duplicate_deps(self, dag):
        active = dag.active_node_ids("illumina", {"host_removal": {"host_reference": "/r.fa"}})
        resolved = dag.resolve_dependencies(active, "illumina")
        for nid, deps in resolved.items():
            assert len(deps) == len(set(deps)), f"Duplicates in {nid}: {deps}"


# ── Tests: Topological ordering ──────────────────────────────────────────


class TestTopologicalOrder:
    def test_linear_chain_order(self, dag):
        active = {"qc_trim", "assemble", "detect", "annotate", "report"}
        resolved = dag.resolve_dependencies(active, "illumina")
        order = dag.topological_order(resolved)
        idx = {n: i for i, n in enumerate(order)}
        assert idx["qc_trim"] < idx["assemble"]
        assert idx["assemble"] < idx["detect"]
        assert idx["detect"] < idx["annotate"]
        assert idx["annotate"] < idx["report"]

    def test_full_pipeline_with_host_removal(self, dag):
        config = {"host_removal": {"host_reference": "/r.fa"}}
        active = dag.active_node_ids("illumina", config)
        resolved = dag.resolve_dependencies(active, "illumina")
        order = dag.topological_order(resolved)
        idx = {n: i for i, n in enumerate(order)}
        assert idx["qc_trim"] < idx["host_filter"] < idx["assemble"] < idx["detect"]

    def test_cycle_detection(self, dag):
        # Create a cycle by faking resolved deps
        cyclic = {
            "qc_trim": ["report"],
            "report": ["qc_trim"],
        }
        with pytest.raises(ValueError, match="Cycle"):
            dag.topological_order(cyclic)


# ── Tests: Enable condition evaluation ───────────────────────────────────


class TestEnableCondition:
    def test_value_match(self):
        assert _evaluate_condition(
            {"field": "mode", "operator": "value", "value": "auto"},
            {"mode": "auto"},
        )

    def test_value_mismatch(self):
        assert not _evaluate_condition(
            {"field": "mode", "operator": "value", "value": "interactive"},
            {"mode": "auto"},
        )

    def test_not_empty_with_value(self):
        assert _evaluate_condition(
            {"field": "host.host_reference", "operator": "not_empty"},
            {"host": {"host_reference": "/path/to/ref.fa"}},
        )

    def test_not_empty_with_none(self):
        assert not _evaluate_condition(
            {"field": "host.host_reference", "operator": "not_empty"},
            {"host": {"host_reference": None}},
        )

    def test_not_empty_with_empty_string(self):
        assert not _evaluate_condition(
            {"field": "host.host_reference", "operator": "not_empty"},
            {"host": {"host_reference": ""}},
        )

    def test_nested_field_path(self):
        assert _evaluate_condition(
            {"field": "a.b.c", "operator": "not_empty"},
            {"a": {"b": {"c": "value"}}},
        )

    def test_missing_field_is_false(self):
        assert not _evaluate_condition(
            {"field": "a.missing", "operator": "value", "value": "x"},
            {"a": {}},
        )


# ── Tests: Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_depends_on(self, dag):
        resolved = dag.resolve_dependencies({"qc_trim"}, "illumina")
        assert resolved["qc_trim"] == []

    def test_nonexistent_node(self, dag):
        with pytest.raises(KeyError):
            dag.node("nonexistent_node")

    def test_platform_with_no_nodes(self, dag):
        # Create a spec with a platform that has no nodes
        spec = {"platforms": ["empty_plat"], "nodes": {}}
        empty_dag = PipelineDAG(spec)
        nodes = empty_dag.nodes_for_platform("empty_plat")
        assert nodes == {}
