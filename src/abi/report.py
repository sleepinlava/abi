"""Generic ABI report writer."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, Mapping


def write_generic_report(
    plan: Any,
    result_dir: str | Path,
    *,
    table_summary: Mapping[str, Mapping[str, Any]],
    title: str = "ABI Report",
) -> Dict[str, Path]:
    root = Path(result_dir)
    report_dir = root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    plan_data = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
    project_name = str(plan_data.get("project_name", root.name))
    analysis_type = str(plan_data.get("analysis_type", "unknown"))
    selected_tools = plan_data.get("selected_tools", [])
    markdown = report_dir / "report.md"
    html = report_dir / "report.html"

    markdown.write_text(
        "\n".join(
            [
                f"# {title}: {project_name}",
                "",
                f"- Analysis type: `{analysis_type}`",
                f"- Planned steps: {len(plan_data.get('steps', []))}",
                f"- Selected tools: {', '.join(str(tool) for tool in selected_tools) or 'none'}",
                "",
                "## Standard Tables",
                "",
                "| Table | Rows | Path |",
                "| --- | ---: | --- |",
                *[
                    f"| `{table}.tsv` | {meta.get('rows', 0)} | `{meta.get('path', '')}` |"
                    for table, meta in sorted(table_summary.items())
                ],
                "",
                "Dry-run artifacts prove planning, command rendering, provenance, and table "
                "contracts only; biological conclusions require real tool outputs.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    html_rows = [
        (
            f"<tr><td>{escape(table)}.tsv</td>"
            f"<td>{escape(str(meta.get('rows', 0)))}</td>"
            f"<td><code>{escape(str(meta.get('path', '')))}</code></td></tr>"
        )
        for table, meta in sorted(table_summary.items())
    ]
    html.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                f'<head><meta charset="utf-8"><title>{escape(title)}</title></head>',
                "<body>",
                f"<h1>{escape(title)}: {escape(project_name)}</h1>",
                f"<p>Analysis type: <code>{escape(analysis_type)}</code></p>",
                f"<p>Planned steps: {len(plan_data.get('steps', []))}</p>",
                "<h2>Selected Tools</h2>",
                "<ul>",
                *[f"<li>{escape(str(tool))}</li>" for tool in selected_tools],
                "</ul>",
                "<h2>Standard Tables</h2>",
                "<table><thead><tr><th>Table</th><th>Rows</th><th>Path</th></tr></thead>",
                "<tbody>",
                *html_rows,
                "</tbody></table>",
                "<p>Dry-run artifacts prove planning, command rendering, provenance, and "
                "table contracts only.</p>",
                "</body>",
                "</html>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "report_summary.json").write_text(
        json.dumps(
            {
                "project_name": project_name,
                "analysis_type": analysis_type,
                "selected_tools": selected_tools,
                "standard_tables": dict(table_summary),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"report": markdown, "report_html": html}
