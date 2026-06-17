"""Methods section generator for ABI reports.

# Purpose / 目的
Generates a ``methods.md`` file that documents every computational step
in a reproducible way: tool name, version, command parameters, database
versions, resource checksums, and literature citations.

# Why methods.md / 为什么需要 methods.md
A pipeline run produces tool outputs, but without a methods section those
outputs are not reproducible.  The methods section is the bridge between
"the pipeline ran" and "a reviewer can verify every computational choice."
没有方法章节的输出不能称为可复现的。方法章节是"管道跑了"和"审稿人能验证
每个计算选择"之间的桥梁。

# Content / 内容
1. Tool name and version for each step.
2. Command-line parameters.
3. Database versions and checksums.
4. Literature citations.
5. Interpretation limitations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

from abi._shared import _read_tsv

__all__ = ["write_methods"]


def write_methods(
    result_dir: str | Path,
    *,
    plan: Any,
    citations: Optional[Sequence[Mapping[str, str]]] = None,
    limitations: Optional[Sequence[str]] = None,
    resource_manifest: Optional[Mapping[str, Any]] = None,
    title: str = "Methods",
) -> Path:
    """Write ``methods.md`` to the report directory under *result_dir*.

    # Parameters / 参数
    - **result_dir**: Pipeline output directory (must contain ``provenance/``
      and ``tables/`` subdirectories).
    - **plan**: The execution plan (duck-typed: needs ``.to_dict()`` or be
      dict-like).
    - **citations**: Optional list of citation dicts with keys ``tool``,
      ``stage``, ``citation``.
    - **limitations**: Optional list of limitation strings.
    - **resource_manifest**: Optional resource manifest dict with ``resources``
      key.

    # Returns / 返回
    Path to the generated ``methods.md`` file.
    """
    root = Path(result_dir)
    report_dir = root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    plan_data = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
    analysis_type = str(plan_data.get("analysis_type", "unknown"))
    project_name = str(plan_data.get("project_name", root.name))

    lines: List[str] = [
        f"# {title} — {project_name}",
        "",
        f"Analysis type: `{analysis_type}`",
        "",
        "## Pipeline Steps",
        "",
    ]

    # ── Steps table / 步骤表 ──
    steps = plan_data.get("steps", [])
    if steps:
        lines.extend([
            "| Step | Tool | Category | Sample |",
            "| --- | --- | --- | --- |",
        ])
        for step in steps:
            step_name = str(step.get("step_name", step.get("step_id", "")))
            tool_id = str(step.get("tool_id", ""))
            category = str(step.get("category", ""))
            sample_id = str(step.get("sample_id", ""))
            lines.append(f"| {step_name} | `{tool_id}` | {category} | {sample_id} |")
        lines.append("")

    # ── Tool versions / 工具版本 ──
    versions_rows = _read_tsv(root / "provenance" / "tool_versions.tsv")
    if versions_rows:
        lines.extend([
            "## Tool Versions",
            "",
            "| Tool | Version | Command |",
            "| --- | --- | --- |",
        ])
        for row in versions_rows:
            tool = row.get("tool_id", row.get("tool", ""))
            version = row.get("version", "")
            cmd = row.get("executable", row.get("command", ""))
            lines.append(f"| `{tool}` | {version} | `{cmd}` |")
        lines.append("")

    # ── Commands / 命令 ──
    commands_rows = _read_tsv(root / "provenance" / "commands.tsv")
    if commands_rows:
        lines.extend([
            "## Executed Commands",
            "",
        ])
        for row in commands_rows:
            step = row.get("step_id", row.get("step", ""))
            cmd = row.get("command", "")
            if cmd:
                lines.append(f"- **{step}**: `{cmd}`")
        lines.append("")

    # ── Resources / 资源 ──
    if resource_manifest:
        resources = resource_manifest.get("resources", [])
        if resources:
            lines.extend([
                "## Resources & Databases",
                "",
                "| Resource | Version | Path | Checksum |",
                "| --- | --- | --- | --- |",
            ])
            for res in resources:
                rid = res.get("id", "")
                ver = res.get("version", "")
                path = res.get("path", "")
                cs_raw = res.get("checksum_sha256", "")
                cs = cs_raw[:12] + "..." if cs_raw else ""
                lines.append(f"| {rid} | {ver} | `{path}` | {cs} |")
            lines.append("")

    # ── Citations / 文献引用 ──
    if citations:
        lines.extend([
            "## Literature Citations",
            "",
            "| Tool | Stage | Citation |",
            "| --- | --- | --- |",
        ])
        for c in citations:
            tool = c.get("tool", "")
            stage = c.get("stage", "")
            citation = c.get("citation", "")
            lines.append(f"| `{tool}` | {stage} | {citation} |")
        lines.append("")

    # ── Limitations / 限制说明 ──
    if limitations:
        lines.extend([
            "## Known Limitations",
            "",
        ])
        for i, lim in enumerate(limitations, 1):
            lines.append(f"{i}. {lim}")
        lines.append("")

    # ── Provenance summary / 溯源摘要 ──
    lines.extend([
        "## Provenance",
        "",
        f"- **Provenance directory**: `{root / 'provenance'}`",
        "- The full provenance record (commands, tool versions, resource",
        "  checksums, progress log, step logs) is available for audit and",
        "  reproduction.",
        "",
        "---",
        "",
        "*This methods section was auto-generated by the ABI report engine.*",
        "*Dates and versions reflect the pipeline execution environment.*",
        "",
    ])

    output = report_dir / "methods.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
