"""Limitations handler for ABI reports.

# Purpose / 目的
Loads and formats the known limitations for a plugin's analysis type.
Every plugin should ship a ``limitations.yaml`` that declares the
scientific and technical limitations of its workflow.  The report
engine reads that file and renders it into the report.

# Why explicit limitations / 为什么需要明确声明限制
Bioinformatics tools have inherent limitations: database biases, assembly
ambiguities, statistical assumptions, reference genome completeness, etc.
Stating these explicitly in every report prevents over-interpretation and
makes the analysis auditable.  This is especially important for agent-driven
analysis, where the agent may not have domain expertise to flag caveats.

# Format / 格式
``limitations.yaml``:
```yaml
limitations:
  - "16S rRNA gene sequencing measures relative abundance, not absolute bacterial load."
  - "Primer choice strongly influences taxonomic profiles; results are SILVA v138-biased."
  - "Low-abundance taxa (<0.1% relative abundance) should be interpreted with caution."
```
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Mapping, Sequence

__all__ = ["format_limitations_html", "format_limitations_markdown", "load_limitations"]


def load_limitations(
    source: str | Path | Sequence[str],
) -> List[str]:
    """Load limitations from a YAML path or a list of strings.

    Accepts a path to a ``limitations.yaml`` file or a pre-built list.
    The YAML file must have a top-level ``limitations`` key containing
    a list of strings.

    Returns a list of limitation strings (may be empty).
    """
    if isinstance(source, (list, tuple)):
        return [str(item) for item in source]
    if isinstance(source, Path):
        path = source
    else:
        path = Path(str(source))
    if not path.exists():
        return []
    from abi.config import load_yaml

    data = load_yaml(path)
    if not isinstance(data, Mapping):
        return []
    items = data.get("limitations", [])
    if not isinstance(items, list):
        return []
    return [str(item) for item in items]


def format_limitations_markdown(
    limitations: Sequence[str],
    *,
    title: str = "Known Limitations",
) -> str:
    """Format a list of limitation strings as a Markdown section.

    Returns an empty string if *limitations* is empty.
    """
    if not limitations:
        return ""
    lines = [f"## {title}", ""]
    for i, lim in enumerate(limitations, 1):
        lines.append(f"{i}. {lim}")
    lines.append("")
    return "\n".join(lines)


def format_limitations_html(
    limitations: Sequence[str],
    *,
    title: str = "Known Limitations",
) -> str:
    """Format a list of limitation strings as an HTML section.

    Returns an empty string if *limitations* is empty.
    """
    if not limitations:
        return ""
    from html import escape

    lines = [f"<h2>{escape(title)}</h2>", "<ol>"]
    for lim in limitations:
        lines.append(f"<li>{escape(str(lim))}</li>")
    lines.append("</ol>")
    return "\n".join(lines)
