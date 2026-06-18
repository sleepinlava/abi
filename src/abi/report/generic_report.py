"""Generic ABI report writer.

# Purpose / 目的
Produces three output files in a report/ subdirectory:
    report.md          — Markdown (human-readable, portable) / 人类可读的 Markdown
    report.html        — HTML (browser-friendly, styled) / 浏览器友好的 HTML
    report_summary.json — JSON (machine-readable, API-friendly) / 机器可读的 JSON

# Plugin usage / 插件用法
Plugins call write_generic_report() at the end of a pipeline run, passing the
plan object (for metadata like project name, analysis type, tool list) and the
table_summary from StandardTableManager.summarize() (for row counts per table).

# Design decisions / 设计决策
- **Three formats, one function**: Generating all three from a single call
  ensures consistency — the Markdown, HTML, and JSON all reflect the same data.
  / 一个调用生成三种格式确保一致性
- **Minimal dependencies**: No template engine is used. The HTML is built with
  string concatenation so there are zero dependencies beyond the stdlib.
  / 无模板引擎，零额外依赖
- **Escape early**: html.escape() is applied at generation time so plugins that
  later embed the HTML don't need to remember to escape. / 生成时转义 HTML
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

__all__ = ["write_generic_report", "write_full_report", "write_plugin_report"]


def write_generic_report(
    plan: Any,
    result_dir: str | Path,
    *,
    table_summary: Mapping[str, Mapping[str, Any]],
    title: str = "ABI Report",
) -> Dict[str, Path]:
    """Write a human-readable + machine-readable pipeline report.

    # What plugins need to provide / 插件需要提供
    - plan: The pipeline plan object (duck-typed: needs .to_dict() or be dict) / 管道计划
    - result_dir: Where to create the report/ subdirectory / 报告输出目录
    - table_summary: Dict from StandardTableManager.summarize() / 表格汇总

    # What is produced / 生成内容
    - report/report.md: Markdown with project metadata and a table summary. / Markdown 格式
    - report/report.html: HTML with the same content, escaped for safety. / HTML 格式
    - report/report_summary.json: Machine-readable summary (same data as Markdown).
      / 机器可读的 JSON

    # Duck-typing the plan / plan 的鸭子类型
    The `plan` parameter is typed as `Any` intentionally: it can be a dataclass
    with .to_dict(), a plain dict, or any object with dict-like access. This
    decouples the report writer from the plan schema so plugins can evolve their
    plan structures independently. / 接受任何有 to_dict() 或 dict 访问的对象。
    """
    root = Path(result_dir)
    report_dir = root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    # Normalize plan to a dict for uniform access / 将 plan 统一转为 dict
    plan_data = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
    project_name = str(plan_data.get("project_name", root.name))
    analysis_type = str(plan_data.get("analysis_type", "unknown"))
    selected_tools = plan_data.get("selected_tools", [])
    markdown = report_dir / "report.md"
    html = report_dir / "report.html"

    # ── Markdown report / Markdown 格式 ──
    # Build line by line via join() for clarity (f-strings would be unwieldy
    # with this many lines). / 逐行构建，比 f-string 更清晰。
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
                # Right-aligned "Rows" column for numeric data / 行数列右对齐
                "| Table | Rows | Path |",
                "| --- | ---: | --- |",
                *[
                    f"| `{table}.tsv` | {meta.get('rows', 0)} | `{meta.get('path', '')}` |"
                    for table, meta in sorted(table_summary.items())
                ],
                "",
                # Disclaimer: dry-run = structural validation only / 免责声明
                "Dry-run artifacts prove planning, command rendering, provenance, and table "
                "contracts only; biological conclusions require real tool outputs.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # ── HTML report / HTML 格式 ──
    # Build table rows first then interpolate into the HTML template. / 先构建行再插入模板。
    # Every dynamic value is escaped via html.escape() to prevent XSS. / 所有动态值都转义防 XSS。
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

    # ── JSON summary / JSON 格式 ──
    # Machine-readable version: suitable for API responses, CI checks, and
    # dashboard ingestion. / 适合 API 响应、CI 检查和仪表盘摄取。
    (report_dir / "report_summary.json").write_text(
        json.dumps(
            {
                "project_name": project_name,
                "analysis_type": analysis_type,
                "selected_tools": selected_tools,
                "standard_tables": dict(table_summary),
            },
            indent=2,
            ensure_ascii=False,  # Allow Unicode in project names / 允许中文项目名
        )
        + "\n",
        encoding="utf-8",
    )
    return {"report": markdown, "report_html": html}


def write_full_report(
    plan: Any,
    result_dir: str | Path,
    *,
    table_summary: Mapping[str, Mapping[str, Any]],
    title: str = "ABI Report",
    rendered_figures: Optional[Dict[str, Path]] = None,
    citations: Optional[List[Dict[str, str]]] = None,
    limitations: Optional[List[str]] = None,
    config: Optional[Mapping[str, Any]] = None,
    methods: bool = True,
    resource_manifest: bool = True,
) -> Dict[str, Path]:
    """Write a complete ABI report with all sections.

    This is the **recommended** function for plugins to call.  It produces
    a full report suite in ``report/``:
    - ``report.md`` — Executive summary with table overview.
    - ``report.html`` — Full styled HTML report with figures, methods,
      limitations, and citations embedded.
    - ``methods.md`` — Standalone methods section for publication.
    - ``report_summary.json`` — Machine-readable summary.
    - ``resource_manifest.json`` (in ``provenance/``) — Resource inventory.

    # Parameters / 参数
    - **plan**: Execution plan (duck-typed: needs ``.to_dict()`` or be dict-like).
    - **result_dir**: Pipeline output directory (must contain ``tables/`` and
      ``provenance/`` subdirectories).
    - **table_summary**: Dict from ``StandardTableManager.summarize()``.
    - **title**: Report title (defaults to plugin's ``report_title``).
    - **rendered_figures**: ``{spec_id: path}`` from ``FigureEngine.render_all()``.
    - **citations**: List of citation dicts with ``tool``, ``stage``, ``citation`` keys.
    - **limitations**: List of limitation strings.
    - **config**: Plugin config dict (used for resource manifest generation).
    - **methods**: If True, generate ``methods.md``.
    - **resource_manifest**: If True, generate ``resource_manifest.json``.

    # Returns / 返回
    Dict mapping section name → Path to generated file.
    """
    from abi.report.html import write_html_report
    from abi.report.methods import write_methods

    root = Path(result_dir)
    paths: Dict[str, Path] = {}

    # ── Generic report (Markdown + HTML + JSON) ──
    generic = write_generic_report(plan, result_dir, table_summary=table_summary, title=title)
    paths.update(generic)

    # ── Full HTML report (overwrites the simpler one) ──
    methods_md = None
    if methods:
        methods_path = write_methods(
            result_dir,
            plan=plan,
            citations=citations,
            limitations=limitations,
            title=f"{title} — Methods",
        )
        paths["methods"] = methods_path
        methods_md = methods_path.read_text(encoding="utf-8")

    html_path = write_html_report(
        result_dir,
        plan=plan,
        table_summary=table_summary,
        rendered_figures=rendered_figures,
        methods_md=methods_md,
        limitations_yaml=limitations,
        citations=citations,
        title=title,
    )
    paths["report_html"] = html_path

    # ── Resource manifest ──
    if resource_manifest and config:
        from abi.workflow.manifest import write_resource_manifest

        plan_data = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        analysis_type = str(plan_data.get("analysis_type", "unknown"))
        manifest_path = write_resource_manifest(
            root / "provenance",
            analysis_type=analysis_type,
            config=config,
            checksum=True,
        )
        paths["resource_manifest"] = manifest_path

    return paths


def _render_figures_via_sciplot(
    plugin: Any,
    specs_path: Path,
    tables_dir: Path,
    figures_dir: Path,
) -> Dict[str, Path]:
    """Render figures using abi_sciplot — PDF+SVG+PNG+provenance+lint.

    Loads legacy-format ``figure_specs.yaml``, adapts each spec to the
    new abi_sciplot FigureSpec, and renders through MatplotlibRenderer.
    Returns ``{spec_id: png_path}`` for HTML report embedding.
    """
    from abi.config import load_yaml
    from abi.sciplot.adapters import adapt_spec
    from abi.sciplot.api import render_figure

    data = load_yaml(specs_path)
    old_specs: list[dict] = data.get("figures", [])
    if not old_specs:
        return {}

    plugin_name = getattr(plugin, "report_title", None) or plugin.__class__.__name__
    abi_version = getattr(plugin, "abi_version", None)

    rendered: Dict[str, Path] = {}
    for old in old_specs:
        spec_id = old.get("id", "")
        if not spec_id:
            continue

        # Skip optional figures whose source table doesn't exist
        source_table = old.get("source_table", "")
        if not old.get("required", True):
            table_path = tables_dir / f"{source_table}.tsv"
            if not table_path.exists():
                continue

        try:
            spec = adapt_spec(
                old,
                tables_dir,
                figures_dir,
                plugin_name=plugin_name,
                abi_version=abi_version,
            )
            result = render_figure(spec)
            # Find the PNG output for HTML embedding
            png_files = [p for p in result.output_files if p.suffix == ".png"]
            if png_files:
                rendered[spec_id] = png_files[0]
        except Exception:
            # Best-effort: skip figures that fail to render
            pass

    return rendered


def _render_figures_via_legacy(
    plugin: Any,
    specs_path: Path,
    tables_dir: Path,
    figures_dir: Path,
) -> Dict[str, Path]:
    """Render figures using the legacy FigureEngine (PNG only).

    Kept for backward compatibility.  Use ``_render_figures_via_sciplot``
    for new code.
    """
    from abi.figures import FigureEngine

    engine = FigureEngine(
        plugin.table_schemas(),
        tables_dir,
        figures_dir,
    )
    engine.load_specs(specs_path)
    return engine.render_all()


def write_plugin_report(
    plugin: Any,
    plan: Any,
    result_dir: str | Path,
    *,
    render_figures: bool = True,
    use_sciplot: bool = True,
) -> Dict[str, Path]:
    """Convenience wrapper that implements the standard plugin ``write_report()``.

    Every inline plugin (rnaseq_expression, wgs_bacteria, amplicon_16s,
    metatranscriptomics) follows the same pattern.  This function
    centralises it so plugins only need a one-liner::

        def write_report(self, plan, result_dir):
            return write_plugin_report(self, plan, result_dir)

    # What it does / 做了什么
    1. Summarises standard tables via ``StandardTableManager``.
    2. Loads ``citation_registry.yaml`` and ``limitations.yaml`` from
       the plugin root (if they exist).
    3. Renders figures via ``abi_sciplot`` (if *use_sciplot*) or legacy
       ``FigureEngine`` (if *render_figures* and a ``figure_specs.yaml`` exists).
    4. Calls ``write_full_report()`` with methods, resource manifest,
       and the stashed config (``plugin._last_config``).

    .. versionchanged:: 1.3.3
       Added *use_sciplot* flag (default True). When True, renders figures
       through ``abi.sciplot`` with PDF+SVG+PNG export, provenance, and lint.
    """
    from pathlib import Path

    from abi.report.citations import load_citations
    from abi.report.limitations import load_limitations
    from abi.tables import StandardTableManager

    # ── Table summary ──
    tm = StandardTableManager(plugin.table_schemas())
    summary = tm.summarize(Path(result_dir) / "tables")

    # ── Citations & limitations ──
    root = plugin.root
    cit_path = root / "citation_registry.yaml"
    lim_path = root / "limitations.yaml"
    citations = load_citations(cit_path) if cit_path.exists() else []
    limitations = load_limitations(lim_path) if lim_path.exists() else []

    # ── Figures ──
    rendered_figures: Optional[Dict[str, Path]] = None
    if render_figures:
        fig_specs_path = root / "figure_specs.yaml"
        if fig_specs_path.exists():
            try:
                if use_sciplot:
                    rendered_figures = _render_figures_via_sciplot(
                        plugin,
                        fig_specs_path,
                        Path(result_dir) / "tables",
                        Path(result_dir) / "figures",
                    )
                else:
                    rendered_figures = _render_figures_via_legacy(
                        plugin,
                        fig_specs_path,
                        Path(result_dir) / "tables",
                        Path(result_dir) / "figures",
                    )
            except Exception:  # noqa: S110
                pass

    # ── Stashed config (for resource manifest) ──
    config = getattr(plugin, "_last_config", None)

    return write_full_report(
        plan,
        result_dir,
        table_summary=summary,
        title=plugin.report_title,
        rendered_figures=rendered_figures,
        citations=citations,
        limitations=limitations,
        config=config,
        methods=True,
        resource_manifest=True,
    )
