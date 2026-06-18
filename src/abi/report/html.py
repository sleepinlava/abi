"""HTML report renderer for ABI.

# Purpose / 目的
Renders a self-contained HTML report from standard tables, figures,
methods, limitations, and citations.  The HTML is styled for readability
and can be opened directly in a browser — no web server needed.

# Design / 设计
- **Self-contained**: All CSS is inline; images are referenced by relative
  path so the report directory can be archived or shared as a folder.
- **No JavaScript**: The report is pure HTML+CSS for maximum portability
  and archival stability.
- **Accessible**: Semantic HTML5 elements (``<article>``, ``<section>``,
  ``<figure>``, ``<table>``) with ARIA labels.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

__all__ = ["write_html_report"]


def write_html_report(
    result_dir: str | Path,
    *,
    plan: Any,
    table_summary: Mapping[str, Mapping[str, Any]],
    rendered_figures: Optional[Mapping[str, Path]] = None,
    methods_md: Optional[str] = None,
    limitations_yaml: Optional[Sequence[str]] = None,
    citations: Optional[Sequence[Mapping[str, str]]] = None,
    title: str = "ABI Report",
) -> Path:
    """Write a self-contained HTML report to ``report/report.html``.

    # Parameters / 参数
    - **result_dir**: Pipeline output directory.
    - **plan**: Execution plan (duck-typed).
    - **table_summary**: Dict from ``StandardTableManager.summarize()``.
    - **rendered_figures**: ``{spec_id: path}`` mapping from ``FigureEngine.render_all()``.
    - **methods_md**: Optional pre-rendered methods markdown (embedded as ``<pre>``).
    - **limitations_yaml**: Optional list of limitation strings.
    - **citations**: Optional list of citation dicts.
    - **title**: Report title.

    # Returns / 返回
    Path to the generated ``report.html`` file.
    """
    root = Path(result_dir)
    report_dir = root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    plan_data = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
    project_name = escape(str(plan_data.get("project_name", root.name)))
    analysis_type = escape(str(plan_data.get("analysis_type", "unknown")))
    steps = plan_data.get("steps", [])

    html_parts: List[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)} — {project_name}</title>",
        _CSS,
        "</head>",
        "<body>",
        f'<header><h1>{escape(title)}</h1><p class="subtitle">{project_name}</p></header>',
        "<main>",
        # ── Executive summary ──
        "<section>",
        "<h2>Executive Summary</h2>",
        f"<p>Analysis type: <code>{analysis_type}</code></p>",
        f"<p>Planned steps: {len(steps)}</p>",
    ]
    tool_names = [escape(str(s.get("tool_id", ""))) for s in steps if s.get("tool_id")]
    html_parts.append(f"<p>Tools used: {', '.join(tool_names) or 'none'}</p>")
    html_parts.extend(
        [
            "</section>",
            # ── Workflow overview ──
            "<section>",
            "<h2>Workflow Overview</h2>",
            "<table>",
            "<thead><tr><th>Step</th><th>Tool</th><th>Category</th><th>Sample</th></tr></thead>",
            "<tbody>",
        ]
    )

    for step in steps:
        sid = escape(str(step.get("step_id", "")))
        tool = escape(str(step.get("tool_id", "")))
        cat = escape(str(step.get("category", "")))
        sample = escape(str(step.get("sample_id", "")))
        html_parts.append(
            f"<tr><td>{sid}</td><td><code>{tool}</code></td><td>{cat}</td><td>{sample}</td></tr>"
        )

    html_parts.extend(
        [
            "</tbody>",
            "</table>",
            "</section>",
            # ── Standard Tables ──
            "<section>",
            "<h2>Standard Tables</h2>",
            "<table>",
            "<thead><tr><th>Table</th><th>Rows</th><th>Path</th></tr></thead>",
            "<tbody>",
        ]
    )

    for table, meta in sorted(table_summary.items()):
        rows = str(meta.get("rows", 0))
        path = escape(str(meta.get("path", "")))
        html_parts.append(
            f"<tr><td><code>{escape(table)}.tsv</code></td>"
            f"<td>{rows}</td><td><code>{path}</code></td></tr>"
        )

    html_parts.extend(
        [
            "</tbody>",
            "</table>",
            "</section>",
        ]
    )

    # ── Figures ──
    if rendered_figures:
        html_parts.extend(
            [
                "<section>",
                "<h2>Figures</h2>",
            ]
        )
        for spec_id, fig_path in sorted(rendered_figures.items()):
            # Reference figures relative to the report directory
            try:
                rel = Path(fig_path).relative_to(root)
            except ValueError:
                rel = Path(fig_path)
            html_parts.extend(
                [
                    f'<figure id="fig-{escape(spec_id)}">',
                    f'<img src="../{escape(str(rel))}" alt="{escape(spec_id)}" loading="lazy">',
                    f"<figcaption>{escape(spec_id)}</figcaption>",
                    "</figure>",
                ]
            )
        html_parts.append("</section>")

    # ── Methods ──
    if methods_md:
        html_parts.extend(
            [
                "<section>",
                "<h2>Methods</h2>",
                f"<pre>{escape(methods_md)}</pre>",
                "</section>",
            ]
        )

    # ── Limitations ──
    if limitations_yaml:
        html_parts.extend(
            [
                "<section>",
                "<h2>Known Limitations</h2>",
                "<ol>",
            ]
        )
        for lim in limitations_yaml:
            html_parts.append(f"<li>{escape(str(lim))}</li>")
        html_parts.extend(
            [
                "</ol>",
                "</section>",
            ]
        )

    # ── Citations ──
    if citations:
        html_parts.extend(
            [
                "<section>",
                "<h2>References</h2>",
                "<ol>",
            ]
        )
        for c in citations:
            tool = escape(str(c.get("tool", "")))
            stage = escape(str(c.get("stage", "")))
            citation = escape(str(c.get("citation", "")))
            if tool and stage:
                html_parts.append(f"<li><strong>{tool}</strong> ({stage}): {citation}</li>")
            elif tool:
                html_parts.append(f"<li><strong>{tool}</strong>: {citation}</li>")
            else:
                html_parts.append(f"<li>{citation}</li>")
        html_parts.extend(
            [
                "</ol>",
                "</section>",
            ]
        )

    # ── Footer ──
    html_parts.extend(
        [
            "</main>",
            "<footer>",
            "<p>Generated by the ABI report engine. "
            "Dry-run artifacts prove planning, command rendering, provenance, and "
            "table contracts only; biological conclusions require real tool outputs.</p>",
            "</footer>",
            "</body>",
            "</html>",
        ]
    )

    output = report_dir / "report.html"
    output.write_text("\n".join(html_parts) + "\n", encoding="utf-8")
    return output


# ── Inline CSS / 内联样式 ─────────────────────────────────────────────────

_CSS = """\
<style>
  :root {
    --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280;
    --accent: #2563eb; --border: #e5e7eb; --code-bg: #f3f4f6;
    --radius: 6px;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #111827; --fg: #e5e7eb; --muted: #9ca3af;
      --accent: #60a5fa; --border: #374151; --code-bg: #1f2937;
    }
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      "Helvetica Neue", Arial, sans-serif;
    max-width: 960px; margin: 0 auto; padding: 2rem 1rem;
    background: var(--bg); color: var(--fg); line-height: 1.6;
  }
  header { border-bottom: 2px solid var(--accent); margin-bottom: 2rem; }
  header h1 { margin: 0; font-size: 1.8rem; }
  .subtitle { color: var(--muted); margin: 0.25rem 0 0.5rem; font-size: 1.1rem; }
  h2 { margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }
  table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
  th { background: var(--code-bg); font-weight: 600; }
  code { background: var(--code-bg); padding: 0.15em 0.4em; border-radius: var(--radius);
    font-size: 0.9em; }
  pre { background: var(--code-bg); padding: 1rem; border-radius: var(--radius);
    overflow-x: auto; font-size: 0.85em; line-height: 1.5; }
  figure { margin: 1.5rem 0; text-align: center; }
  figure img { max-width: 100%; height: auto; border: 1px solid var(--border);
    border-radius: var(--radius); }
  figcaption { color: var(--muted); font-size: 0.85em; margin-top: 0.5rem; }
  ol, ul { padding-left: 1.5rem; }
  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 0.85rem; }
  @media print {
    body { max-width: none; padding: 0; }
    figure img { max-width: 100%; page-break-inside: avoid; }
    footer { display: none; }
  }
</style>"""
