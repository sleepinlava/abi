#!/usr/bin/env python3
"""Integrate independently computed plasmid annotations into an ABI result."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abi.plugins.metagenomic_plasmid._engine.parsers import parse_standard_outputs
from abi.plugins.metagenomic_plasmid._engine.standard_tables import (
    expand_standard_rows,
    read_standard_table,
    write_standard_table,
)

try:
    from scripts.repair_plasmid_standard_tables import repair_result
except ModuleNotFoundError:  # Direct execution sets scripts/ as sys.path[0].
    from repair_plasmid_standard_tables import repair_result

TOOL_DIRS = {
    "amrfinderplus": "amrfinderplus",
    "abricate": "abricate",
    "mob_typer": "mob_typer",
}
MERGE_TABLES = {"annotations", "host_predictions", "plasmid_typing"}


def integrate_supplement(
    result_dir: str | Path,
    supplement_dir: str | Path,
    sample_id: str,
) -> dict[str, Any]:
    root = Path(result_dir).resolve()
    supplement = Path(supplement_dir).resolve()
    tables_dir = root / "tables"
    raw_dir = supplement / "raw"
    summary_path = root / "provenance" / "run_summary.json"
    if not tables_dir.is_dir() or not summary_path.is_file():
        raise ValueError(f"Not a complete ABI result directory: {root}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") != "success":
        raise ValueError("Refusing to supplement a result whose run_summary status is not success")

    parsed: dict[str, list[dict[str, Any]]] = {}
    source_files: list[Path] = []
    tool_rows: dict[str, dict[str, int]] = {}
    for tool_id, dirname in TOOL_DIRS.items():
        tool_dir = raw_dir / dirname
        files = sorted(path for path in tool_dir.glob("*") if path.is_file())
        if not files:
            raise ValueError(f"No {tool_id} output found in {tool_dir}")
        source_files.extend(files)
        rows_by_table = parse_standard_outputs(tool_id, tool_dir, sample_id)
        tool_rows[tool_id] = {name: len(rows) for name, rows in rows_by_table.items()}
        for table_name, rows in rows_by_table.items():
            parsed.setdefault(table_name, []).extend(rows)

    if "plasmid_predictions" in parsed:
        raise ValueError("Typing/annotation supplement must not add plasmid detection calls")

    standalone = expand_standard_rows(parsed)
    supplement_tables = supplement / "tables"
    for table_name, rows in standalone.items():
        if rows:
            write_standard_table(supplement_tables, table_name, rows)

    backup_dir = supplement / "provenance" / "pre_integration_tables"
    backup_dir.mkdir(parents=True, exist_ok=True)
    merged_rows: dict[str, int] = {}
    raw_prefix = str(raw_dir) + "/"
    for table_name in sorted(MERGE_TABLES & parsed.keys()):
        path = tables_dir / f"{table_name}.tsv"
        if path.is_file() and not (backup_dir / path.name).exists():
            shutil.copy2(path, backup_dir / path.name)
        existing = read_standard_table(tables_dir, table_name)
        retained = [
            row for row in existing if not str(row.get("source_file", "")).startswith(raw_prefix)
        ]
        combined = retained + parsed[table_name]
        write_standard_table(tables_dir, table_name, combined)
        merged_rows[table_name] = len(parsed[table_name])

    repair_record = repair_result(root)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "integration": "plasmid_amr_mobility_supplement_v1",
        "result_dir": str(root),
        "supplement_dir": str(supplement),
        "sample_id": sample_id,
        "source_sha256": {str(path): _sha256(path) for path in source_files},
        "tool_rows": tool_rows,
        "merged_rows": merged_rows,
        "standalone_rows": {name: len(rows) for name, rows in standalone.items()},
        "repair_timestamp": repair_record["timestamp"],
    }
    provenance = supplement / "provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    (provenance / "integration.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--supplement-dir", required=True, type=Path)
    parser.add_argument("--sample-id", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            integrate_supplement(args.result_dir, args.supplement_dir, args.sample_id),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
