"""Read-only validation for completed AutoPlasm result directories."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from abi._shared import _read_tsv
from abi.plugins.metagenomic_plasmid._engine.standard_tables import TABLE_SCHEMAS

CORE_TABLES = {
    "sample_qc",
    "assembly_qc",
    "plasmid_predictions",
    "plasmid_consensus",
    "plasmid_structure",
    "plasmid_catalog",
    "plasmid_abundance",
    "plasmid_annotation",
    "amr_genes",
    "plasmid_typing",
}


def validate_result_dir(
    result_dir: str | Path,
    *,
    allow_empty_tables: bool = True,
) -> Dict[str, Any]:
    root = Path(result_dir)
    errors: List[str] = []
    warnings: List[str] = []

    if not root.exists():
        return {
            "result_dir": str(root),
            "valid": False,
            "errors": [f"Result directory does not exist: {root}"],
            "warnings": [],
            "status": "missing",
            "failed_steps": [],
            "tables": {},
        }

    plan_path = root / "execution_plan.json"
    summary_path = root / "provenance" / "run_summary.json"
    commands_path = root / "provenance" / "commands.tsv"
    report_md = root / "report" / "report.md"
    report_html = root / "report" / "report.html"

    _require_file(plan_path, errors)
    _require_file(summary_path, errors)
    _require_file(commands_path, errors)
    _require_file(report_md, warnings)
    _require_file(report_html, warnings)

    summary = _read_json(summary_path, errors)
    status = str(summary.get("status", "unknown")) if summary else "unknown"
    if status != "success":
        errors.append(f"run_summary status is {status!r}, not 'success'")

    commands = _read_tsv(commands_path)
    failed_steps = [row for row in commands if row.get("status") == "failed"]
    if failed_steps:
        errors.append(f"commands.tsv contains {len(failed_steps)} failed step(s)")

    tables = _table_status(root / "tables")
    missing_core = [
        name for name in CORE_TABLES if name not in tables or not tables[name]["exists"]
    ]
    if missing_core:
        errors.append("Missing core standard table(s): " + ", ".join(sorted(missing_core)))
    if not allow_empty_tables:
        empty_core = [
            name
            for name in CORE_TABLES
            if name in tables and tables[name]["exists"] and tables[name]["rows"] == 0
        ]
        if empty_core:
            errors.append("Empty core standard table(s): " + ", ".join(sorted(empty_core)))

    if tables.get("network_edges", {}).get("rows", 0) and not tables.get("network_nodes", {}).get(
        "rows", 0
    ):
        warnings.append("network_edges.tsv has rows but network_nodes.tsv is empty")

    return {
        "result_dir": str(root),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "status": status,
        "failed_steps": failed_steps,
        "tables": tables,
    }


def _require_file(path: Path, issues: List[str]) -> None:
    if not path.exists():
        issues.append(f"Missing file: {path}")
    elif path.is_file() and path.stat().st_size == 0:
        issues.append(f"Empty file: {path}")


def _read_json(path: Path, errors: List[str]) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in {path}: {exc}")
        return {}


def _table_status(tables_dir: Path) -> Dict[str, Dict[str, Any]]:
    status = {}
    for table_name, fields in TABLE_SCHEMAS.items():
        path = tables_dir / f"{table_name}.tsv"
        if not path.exists():
            status[table_name] = {"exists": False, "rows": 0, "path": str(path)}
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)
            missing_fields = [field for field in fields if field not in (reader.fieldnames or [])]
        status[table_name] = {
            "exists": True,
            "rows": len(rows),
            "path": str(path),
            "missing_fields": missing_fields,
        }
    return status
