"""Tests for ABI report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from abi.report import write_generic_report


@dataclass
class FakePlan:
    project_name: str = "test_project"
    analysis_type: str = "metatranscriptomics"
    selected_tools: List[str] = field(default_factory=lambda: ["fastp", "star"])
    steps: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "analysis_type": self.analysis_type,
            "selected_tools": self.selected_tools,
            "steps": [],
        }


def test_write_generic_report(tmp_path):
    plan = FakePlan()
    table_summary = {
        "gene_expression": {"rows": 10, "path": str(tmp_path / "tables" / "gene_expression.tsv")},
    }
    paths = write_generic_report(plan, tmp_path, table_summary=table_summary)
    assert paths["report"].exists()
    assert paths["report_html"].exists()
    md_content = paths["report"].read_text(encoding="utf-8")
    assert "test_project" in md_content
    assert "gene_expression" in md_content
