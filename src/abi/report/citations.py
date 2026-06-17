"""Citation registry and formatter for ABI reports.

# Purpose / 目的
Provides a structured way for plugins to declare literature citations
for each tool and pipeline stage, and formats them into report sections.

# Why structured citations / 为什么需要结构化引用
Bioinformatics pipelines depend on published methods.  Citing the right
paper for each tool is essential for scientific reproducibility.  A
structured citation registry lets:
- Plugins declare citations once in YAML.
- Reports auto-generate a formatted citation section.
- Agents discover which papers support each analysis choice.

# Format / 格式
``citation_registry.yaml``:
```yaml
citations:
  - tool: fastp
    stage: qc
    citation: "Chen et al. 2018, Bioinformatics, doi:10.1093/bioinformatics/bty560"
  - tool: STAR
    stage: alignment
    citation: "Dobin et al. 2013, Bioinformatics, doi:10.1093/bioinformatics/bts635"
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Mapping, Sequence

__all__ = [
    "CitationRegistry",
    "format_citations_markdown",
    "format_citations_html",
    "load_citations",
]


class CitationRegistry:
    """Holds and queries structured literature citations for a plugin.

    # Usage / 用法
        registry = CitationRegistry.from_yaml(plugin_root / "citation_registry.yaml")
        for cite in registry.for_step("qc_fastp"):
            print(cite["citation"])
    """

    def __init__(self, citations: Sequence[Mapping[str, str]]) -> None:
        self._citations: List[Dict[str, str]] = [
            {
                "tool": str(c.get("tool", "")),
                "stage": str(c.get("stage", c.get("step", ""))),
                "citation": str(c.get("citation", "")),
            }
            for c in citations
        ]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CitationRegistry":
        """Load citations from a ``citation_registry.yaml`` file."""
        from abi.config import load_yaml

        data = load_yaml(Path(path))
        items = data.get("citations", [])
        if not isinstance(items, list):
            items = []
        return cls(items)

    @property
    def all(self) -> List[Dict[str, str]]:
        """All citations as a list of dicts."""
        return list(self._citations)

    def for_tool(self, tool_id: str) -> List[Dict[str, str]]:
        """Return citations matching *tool_id*."""
        return [c for c in self._citations if c["tool"] == tool_id]

    def for_stage(self, stage: str) -> List[Dict[str, str]]:
        """Return citations matching *stage*."""
        return [c for c in self._citations if c["stage"] == stage]

    def unique_citations(self) -> List[str]:
        """Return deduplicated citation strings, preserving order."""
        seen: set[str] = set()
        result: List[str] = []
        for c in self._citations:
            text = c["citation"]
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    def to_dicts(self) -> List[Dict[str, str]]:
        """Return all citations as the canonical dict list for report generation."""
        return self.all


def load_citations(
    source: str | Path | Sequence[Mapping[str, str]],
) -> List[Dict[str, str]]:
    """Load citations from YAML path or list of dicts.

    Convenience wrapper around ``CitationRegistry`` for callers that
    just need the dict list.
    """
    if isinstance(source, (list, tuple)):
        return CitationRegistry(source).all
    return CitationRegistry.from_yaml(source).all


def format_citations_markdown(
    citations: Sequence[Mapping[str, str]],
    *,
    title: str = "References",
) -> str:
    """Format citations as a numbered Markdown reference list.

    Returns an empty string if *citations* is empty.
    """
    if not citations:
        return ""
    lines = [f"## {title}", ""]
    for i, c in enumerate(citations, 1):
        tool = c.get("tool", "")
        stage = c.get("stage", "")
        citation = c.get("citation", "")
        if tool and stage:
            lines.append(f"{i}. **{tool}** ({stage}): {citation}")
        elif tool:
            lines.append(f"{i}. **{tool}**: {citation}")
        else:
            lines.append(f"{i}. {citation}")
    lines.append("")
    return "\n".join(lines)


def format_citations_html(
    citations: Sequence[Mapping[str, str]],
    *,
    title: str = "References",
) -> str:
    """Format citations as an HTML ordered reference list.

    Returns an empty string if *citations* is empty.
    """
    if not citations:
        return ""
    from html import escape

    lines = [f"<h2>{escape(title)}</h2>", "<ol>"]
    for c in citations:
        tool = escape(str(c.get("tool", "")))
        stage = escape(str(c.get("stage", "")))
        citation = escape(str(c.get("citation", "")))
        if tool and stage:
            lines.append(f"<li><strong>{tool}</strong> ({stage}): {citation}</li>")
        elif tool:
            lines.append(f"<li><strong>{tool}</strong>: {citation}</li>")
        else:
            lines.append(f"<li>{citation}</li>")
    lines.append("</ol>")
    return "\n".join(lines)
