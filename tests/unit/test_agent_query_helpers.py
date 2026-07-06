"""Unit tests for pure query helper functions in ``src/abi/agent/interface.py``.

These functions require zero external dependencies — only in-memory
dicts/lists/SimpleNamespaces. No filesystem, network, or tool execution.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from abi.agent.interface import (
    _build_plan_summary,
    _optional_path,
    _path_values,
    _query_platforms,
    _query_stages,
    _query_step,
    _query_tools,
)


# ------------------------------------------------------------------
# _optional_path
# ------------------------------------------------------------------


class TestOptionalPath:
    """Tests for ``_optional_path`` — str/Path → Path, None preserved."""

    def test_none_returns_none(self) -> None:
        assert _optional_path(None) is None

    def test_str_returns_path(self) -> None:
        result = _optional_path("some/dir")
        assert isinstance(result, Path)
        assert str(result) == "some/dir"

    def test_path_returns_path(self) -> None:
        p = Path("some/dir")
        result = _optional_path(p)
        assert isinstance(result, Path)
        assert result == p


# ------------------------------------------------------------------
# _path_values
# ------------------------------------------------------------------


class TestPathValues:
    """Tests for ``_path_values`` — collect non-None values from a mapping."""

    def test_filters_none_values(self) -> None:
        outputs: Dict[str, Any] = {"a": "/tmp/a", "b": None, "c": "/tmp/c"}
        result = _path_values(outputs)
        assert result == ["/tmp/a", "/tmp/c"]

    def test_empty_mapping(self) -> None:
        assert _path_values({}) == []

    def test_all_none(self) -> None:
        outputs: Dict[str, Any] = {"a": None, "b": None}
        assert _path_values(outputs) == []

    def test_all_non_none(self) -> None:
        outputs: Dict[str, Any] = {"x": 1, "y": "hello"}
        assert _path_values(outputs) == [1, "hello"]

    def test_path_objects_preserved(self) -> None:
        p = Path("/tmp/out")
        outputs: Dict[str, Any] = {"a": p, "b": None}
        result = _path_values(outputs)
        assert result == [p]
        assert result[0] is p


# ------------------------------------------------------------------
# _build_plan_summary
# ------------------------------------------------------------------


class TestBuildPlanSummary:
    """Tests for ``_build_plan_summary`` — lightweight pipeline summary."""

    @staticmethod
    def _step(
        id_: str = "s1",
        tool_id: str = "trimmomatic",
        category: str = "qc",
        enabled: bool = True,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=id_,
            tool_id=tool_id,
            category=category,
            enabled=enabled,
        )

    @staticmethod
    def _sample(
        id_: str = "sample1",
        platform: str = "illumina",
    ) -> SimpleNamespace:
        return SimpleNamespace(id=id_, platform=platform)

    def test_plan_with_categorized_steps(self) -> None:
        plan = SimpleNamespace(
            steps=[
                self._step(id_="s1", tool_id="fastqc", category="qc"),
                self._step(id_="s2", tool_id="trimmomatic", category="qc"),
                self._step(id_="s3", tool_id="spades", category="assembly"),
            ],
            samples=[],
        )
        summary = _build_plan_summary(plan, "metagenomic_plasmid")
        assert summary["pipeline"] == "metagenomic_plasmid"
        assert summary["stages"] == ["qc", "assembly"]
        # key_tools picks the first tool in each unique category
        assert summary["key_tools"] == ["fastqc", "spades"]
        assert summary["platforms"] == []

    def test_steps_without_category(self) -> None:
        plan = SimpleNamespace(
            steps=[
                self._step(id_="s1", tool_id="fastqc", category=""),
                self._step(id_="s2", tool_id="trimmomatic", category=""),
            ],
            samples=[],
        )
        summary = _build_plan_summary(plan, "test")
        # Empty categories are stripped and not added
        assert summary["stages"] == []
        assert summary["key_tools"] == []

    def test_empty_plan(self) -> None:
        plan = SimpleNamespace(steps=[], samples=[])
        summary = _build_plan_summary(plan, "test")
        assert summary["pipeline"] == "test"
        assert summary["stages"] == []
        assert summary["key_tools"] == []
        assert summary["platforms"] == []

    def test_platform_breakdown_aggregates_samples(self) -> None:
        plan = SimpleNamespace(
            steps=[],
            samples=[
                self._sample(id_="s1", platform="illumina"),
                self._sample(id_="s2", platform="illumina"),
                self._sample(id_="s3", platform="nanopore"),
            ],
        )
        summary = _build_plan_summary(plan, "test")
        # Platforms deduplicated in first-appearance order
        assert summary["platforms"] == ["illumina", "nanopore"]

    def test_sample_without_platform_defaults_to_generic(self) -> None:
        plan = SimpleNamespace(
            steps=[],
            samples=[
                SimpleNamespace(id="s1"),  # no platform attribute → default
            ],
        )
        summary = _build_plan_summary(plan, "test")
        assert summary["platforms"] == ["generic"]

    def test_deduplication_of_tools_per_stage(self) -> None:
        plan = SimpleNamespace(
            steps=[
                self._step(id_="s1", tool_id="t1", category="qc"),
                self._step(id_="s2", tool_id="t2", category="qc"),
                self._step(id_="s3", tool_id="t3", category="assembly"),
                self._step(id_="s4", tool_id="t4", category="qc"),  # repeat cat, ignored
            ],
            samples=[],
        )
        summary = _build_plan_summary(plan, "test")
        assert summary["stages"] == ["qc", "assembly"]
        assert summary["key_tools"] == ["t1", "t3"]

    def test_whitespace_only_category(self) -> None:
        plan = SimpleNamespace(
            steps=[
                self._step(id_="s1", tool_id="t1", category="   "),
                self._step(id_="s2", tool_id="t2", category="\t"),
            ],
            samples=[],
        )
        summary = _build_plan_summary(plan, "test")
        assert summary["stages"] == []
        assert summary["key_tools"] == []


# ------------------------------------------------------------------
# _query_stages
# ------------------------------------------------------------------


class TestQueryStages:
    """Tests for ``_query_stages`` — ordered pipeline stages from DAG or registry."""

    def test_dag_with_categorized_nodes(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {"tool_id": "fastqc", "category": "qc"},
                "n2": {"tool_id": "trimmomatic", "category": "qc"},
                "n3": {"tool_id": "spades", "category": "assembly"},
            }
        }
        tools: List[Dict[str, Any]] = []
        result = _query_stages(dag, tools, "metagenomic_plasmid")
        assert result["pipeline"] == "metagenomic_plasmid"
        assert result["stages"] == ["qc", "assembly"]
        assert result["stage_count"] == 2

    def test_dag_without_category_falls_back_to_tools(self) -> None:
        dag: Dict[str, Any] = {"nodes": {}}  # empty nodes → fallback
        tools: List[Dict[str, Any]] = [
            {"id": "fastqc", "category": "qc"},
            {"id": "spades", "category": "assembly"},
            {"id": "trimmomatic", "category": "qc"},  # duplicate cat → dedup
        ]
        result = _query_stages(dag, tools, "test")
        assert result["stages"] == ["qc", "assembly"]
        assert result["stage_count"] == 2

    def test_none_dag_falls_back_to_tools(self) -> None:
        tools: List[Dict[str, Any]] = [
            {"id": "fastqc", "category": "qc"},
        ]
        result = _query_stages(None, tools, "test")
        assert result["stages"] == ["qc"]
        assert result["stage_count"] == 1

    def test_empty_dag_and_tools(self) -> None:
        result = _query_stages({}, [], "test")
        assert result["stages"] == []
        assert result["stage_count"] == 0

    def test_empty_string_category_filtered_out(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {"tool_id": "t1", "category": ""},
                "n2": {"tool_id": "t2", "category": "qc"},
            }
        }
        result = _query_stages(dag, [], "test")
        assert result["stages"] == ["qc"]

    def test_whitespace_category_filtered_out(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {"tool_id": "t1", "category": "  "},
            }
        }
        result = _query_stages(dag, [], "test")
        assert result["stages"] == []


# ------------------------------------------------------------------
# _query_tools
# ------------------------------------------------------------------


class TestQueryTools:
    """Tests for ``_query_tools`` — tools grouped by category from DAG or registry."""

    def test_dag_node_tool_lookup(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {
                    "tool_id": "fastqc",
                    "category": "qc",
                    "optional": False,
                    "depends_on": [],
                },
                "n2": {
                    "tool_id": "spades",
                    "category": "assembly",
                    "optional": True,
                    "depends_on": ["n1"],
                },
            }
        }
        tools: List[Dict[str, Any]] = []
        result = _query_tools(dag, tools)
        assert result["tool_count"] == 2
        assert result["tools"] == [
            {
                "step_id": "n1",
                "tool_id": "fastqc",
                "category": "qc",
                "optional": False,
                "depends_on": [],
            },
            {
                "step_id": "n2",
                "tool_id": "spades",
                "category": "assembly",
                "optional": True,
                "depends_on": ["n1"],
            },
        ]

    def test_fallback_to_tool_registry(self) -> None:
        dag: Dict[str, Any] = {}  # no nodes
        tools: List[Dict[str, Any]] = [
            {"id": "fastqc", "category": "qc", "description": "Quality control"},
            {"id": "spades", "category": "assembly", "description": "Assembly"},
        ]
        result = _query_tools(dag, tools)
        assert result["tool_count"] == 2
        assert result["tools"] == [
            {"tool_id": "fastqc", "category": "qc", "description": "Quality control"},
            {"tool_id": "spades", "category": "assembly", "description": "Assembly"},
        ]

    def test_none_dag_falls_back_to_registry(self) -> None:
        tools: List[Dict[str, Any]] = [
            {"id": "fastqc", "category": "qc", "description": "QC"},
        ]
        result = _query_tools(None, tools)
        assert result["tool_count"] == 1

    def test_empty_dag_and_empty_registry(self) -> None:
        result = _query_tools({}, [])
        assert result["tool_count"] == 0
        assert result["tools"] == []

    def test_node_without_tool_id_defaults_to_node_id(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {"category": "qc"},
            }
        }
        result = _query_tools(dag, [])
        assert result["tools"][0]["tool_id"] == "n1"

    def test_missing_optional_and_depends_on_defaulted(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {"category": "qc"},
            }
        }
        result = _query_tools(dag, [])
        assert result["tools"][0]["optional"] is False
        assert result["tools"][0]["depends_on"] == []


# ------------------------------------------------------------------
# _query_platforms
# ------------------------------------------------------------------


class TestQueryPlatforms:
    """Tests for ``_query_platforms`` — platforms from DAG."""

    def test_dag_with_platform_assignments(self) -> None:
        dag: Dict[str, Any] = {"platforms": ["illumina", "nanopore"]}
        result = _query_platforms(dag)
        assert result["platforms"] == ["illumina", "nanopore"]

    def test_empty_dag(self) -> None:
        result = _query_platforms({})
        assert result["platforms"] == []

    def test_none_dag(self) -> None:
        result = _query_platforms(None)
        assert result["platforms"] == []

    def test_dag_without_platforms_key(self) -> None:
        result = _query_platforms({"nodes": {}})
        assert result["platforms"] == []


# ------------------------------------------------------------------
# _query_step
# ------------------------------------------------------------------


class TestQueryStep:
    """Tests for ``_query_step`` — inputs/outputs/resources for a pipeline node."""

    @staticmethod
    def _dag_with_nodes() -> Dict[str, Any]:
        return {
            "nodes": {
                "fastqc": {
                    "tool_id": "fastqc",
                    "inputs": {"reads": "reads.fq"},
                    "outputs": {"report": "fastqc.html"},
                },
            }
        }

    @staticmethod
    def _tools_registry() -> List[Dict[str, Any]]:
        return [
            {
                "id": "spades",
                "inputs": {"contigs": "contigs.fa"},
                "outputs": {"assembly": "scaffolds.fa"},
            }
        ]

    # -- what="inputs" --------------------------------------------------------

    def test_dag_match_inputs(self) -> None:
        result = _query_step(self._dag_with_nodes(), [], "fastqc", "inputs")
        assert result["step_id"] == "fastqc"
        assert result["tool_id"] == "fastqc"
        assert result["inputs"] == {"reads": "reads.fq"}
        assert "outputs" not in result

    def test_dag_match_outputs(self) -> None:
        result = _query_step(self._dag_with_nodes(), [], "fastqc", "outputs")
        assert result["outputs"] == {"report": "fastqc.html"}
        assert "inputs" not in result

    def test_dag_match_resources(self) -> None:
        result = _query_step(self._dag_with_nodes(), [], "fastqc", "resources")
        assert result["inputs"] == {"reads": "reads.fq"}
        assert result["outputs"] == {"report": "fastqc.html"}

    # -- tool registry fallback -------------------------------------------------

    def test_registry_match(self) -> None:
        result = _query_step({}, self._tools_registry(), "spades", "inputs")
        assert result["step_id"] == "spades"
        assert result["tool_id"] == "spades"
        assert result["inputs"] == {"contigs": "contigs.fa"}

    def test_registry_match_outputs(self) -> None:
        result = _query_step({}, self._tools_registry(), "spades", "outputs")
        assert result["outputs"] == {"assembly": "scaffolds.fa"}

    def test_registry_match_resources(self) -> None:
        result = _query_step({}, self._tools_registry(), "spades", "resources")
        assert result["inputs"] == {"contigs": "contigs.fa"}
        assert result["outputs"] == {"assembly": "scaffolds.fa"}

    # -- error cases -----------------------------------------------------------

    def test_unknown_step_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            _query_step({}, [], "nonexistent", "inputs")

    def test_none_dag_raises_valueerror_for_unknown_step(self) -> None:
        with pytest.raises(ValueError):
            _query_step(None, [], "nonexistent", "outputs")

    # -- edge cases ------------------------------------------------------------

    def test_node_without_tool_id_defaults(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "n1": {"inputs": {"a": "a.txt"}, "outputs": {"b": "b.txt"}},
            }
        }
        result = _query_step(dag, [], "n1", "resources")
        assert result["tool_id"] == "n1"

    def test_step_in_dag_even_if_also_in_registry_prefers_dag(self) -> None:
        dag: Dict[str, Any] = {
            "nodes": {
                "spades": {
                    "tool_id": "spades",
                    "inputs": {"from_dag": True},
                    "outputs": {},
                },
            }
        }
        tools: List[Dict[str, Any]] = [
            {"id": "spades", "inputs": {"from_registry": True}, "outputs": {}}
        ]
        result = _query_step(dag, tools, "spades", "inputs")
        # DAG takes precedence
        assert result["inputs"] == {"from_dag": True}
