"""Versioned final-report manifests for EasyMetagenome workflows."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

REPORT_MANIFEST_SCHEMA_VERSION = "abi.report-manifest.v1"


def write_report_manifest(
    path: str | Path,
    *,
    workflow: str,
    sample_count: int,
    artifacts: Mapping[str, str | Path],
    report: str | Path,
    tables_dir: str | Path,
    table_names: Sequence[str],
    extra: Mapping[str, Any] | None = None,
) -> Path:
    standard_tables = _standard_tables(tables_dir, table_names)
    payload = {
        "schema_version": REPORT_MANIFEST_SCHEMA_VERSION,
        "plugin": "easymetagenome",
        "workflow": workflow,
        "sample_count": sample_count,
        "artifacts": {name: str(value) for name, value in artifacts.items()},
        "report": str(report),
        "standard_tables": standard_tables,
        "consistency": {
            "standard_table_count": len(standard_tables),
            "standard_row_count": sum(item["rows"] for item in standard_tables.values()),
        },
    }
    if extra:
        payload.update(dict(extra))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def validate_report_manifest(
    path: str | Path,
    *,
    workflow: str,
    sample_count: int,
    report: str | Path,
    artifacts_root: str | Path,
    artifact_names: Sequence[str],
    tables_dir: str | Path,
    table_names: Sequence[str],
) -> bool:
    """Validate a persisted manifest against the report and its current TSV tables."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    expected_report = Path(report)
    if (
        payload.get("schema_version") != REPORT_MANIFEST_SCHEMA_VERSION
        or payload.get("plugin") != "easymetagenome"
        or payload.get("workflow") != workflow
        or payload.get("sample_count") != sample_count
        or payload.get("report") != str(expected_report)
        or not expected_report.is_file()
        or expected_report.stat().st_size == 0
    ):
        return False
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(artifact_names):
        return False
    artifact_root = Path(artifacts_root).resolve()
    for value in artifacts.values():
        artifact = Path(str(value))
        if (
            not artifact.is_file()
            or artifact.stat().st_size == 0
            or not artifact.resolve().is_relative_to(artifact_root)
        ):
            return False
    tables = payload.get("standard_tables")
    consistency = payload.get("consistency")
    if not isinstance(tables, dict) or set(tables) != set(table_names):
        return False
    if not isinstance(consistency, dict):
        return False
    actual_rows = 0
    canonical_tables_dir = Path(tables_dir)
    for name in table_names:
        item = tables.get(name)
        if not isinstance(item, dict) or set(item) != {"path", "rows"}:
            return False
        table_path = Path(str(item["path"]))
        expected_table_path = canonical_tables_dir / f"{name}.tsv"
        rows = item.get("rows")
        if (
            table_path != expected_table_path
            or not table_path.is_file()
            or not isinstance(rows, int)
            or rows < 0
        ):
            return False
        if rows != _tsv_row_count(table_path):
            return False
        actual_rows += rows
    return consistency == {
        "standard_table_count": len(table_names),
        "standard_row_count": actual_rows,
    }


def _standard_tables(
    tables_dir: str | Path, table_names: Sequence[str]
) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}
    root = Path(tables_dir)
    for name in table_names:
        path = root / f"{name}.tsv"
        if path.is_file():
            tables[name] = {"path": str(path), "rows": _tsv_row_count(path)}
    return tables


def _tsv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle, delimiter="\t"))
