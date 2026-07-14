from __future__ import annotations

from pathlib import Path

from docs.diagrams.generate_abi_architecture_drawio import render

DIAGRAM_PATH = Path(__file__).parents[2] / "docs/diagrams/abi-architecture.drawio"


def test_architecture_diagram_generation_is_deterministic():
    assert render() == render()


def test_checked_in_architecture_diagram_matches_generator():
    assert DIAGRAM_PATH.read_text(encoding="utf-8") == render()


def test_architecture_diagram_documents_workflow_deepening():
    assert 'name="05-工作流深模块"' in render()
