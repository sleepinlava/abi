"""Schema-driven standard table helpers for ABI plugins."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

__all__ = ["StandardTableManager"]


class StandardTableManager:
    def __init__(self, schemas: Mapping[str, Iterable[str]]) -> None:
        self.schemas: Dict[str, List[str]] = {
            table_name: list(fields) for table_name, fields in schemas.items()
        }
        if not self.schemas:
            raise ValueError("ABI standard table schemas cannot be empty")

    def table_path(self, tables_dir: str | Path, table_name: str) -> Path:
        if table_name not in self.schemas:
            raise ValueError(f"Unknown ABI standard table: {table_name}")
        return Path(tables_dir) / f"{table_name}.tsv"

    def ensure_tables(self, tables_dir: str | Path) -> Dict[str, Path]:
        paths = {}
        for table_name, fields in self.schemas.items():
            path = self.table_path(tables_dir, table_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                self._write_header(path, fields)
            paths[table_name] = path
        return paths

    def append_rows(
        self,
        tables_dir: str | Path,
        rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]],
    ) -> Dict[str, Path]:
        self.ensure_tables(tables_dir)
        written = {}
        for table_name, rows in rows_by_table.items():
            rows = list(rows)
            if not rows:
                continue
            written[table_name] = self.write_table(tables_dir, table_name, rows, append=True)
        return written

    def write_table(
        self,
        tables_dir: str | Path,
        table_name: str,
        rows: Iterable[Mapping[str, Any]],
        *,
        append: bool = False,
    ) -> Path:
        if table_name not in self.schemas:
            raise ValueError(f"Unknown ABI standard table: {table_name}")
        fields = self.schemas[table_name]
        path = self.table_path(tables_dir, table_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(rows)
        mode = "a" if append and path.exists() else "w"
        with path.open(mode, encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                delimiter="\t",
                extrasaction="ignore",
                lineterminator="\n",
            )
            if mode == "w" or path.stat().st_size == 0:
                writer.writeheader()
            for row in rows:
                writer.writerow({field: _tsv_value(row.get(field, "")) for field in fields})
        return path

    def summarize(self, tables_dir: str | Path) -> Dict[str, Dict[str, Any]]:
        self.ensure_tables(tables_dir)
        summary = {}
        for table_name in self.schemas:
            path = self.table_path(tables_dir, table_name)
            with path.open("r", encoding="utf-8", newline="") as handle:
                row_count = sum(1 for _ in csv.DictReader(handle, delimiter="\t"))
            summary[table_name] = {"rows": row_count, "path": str(path)}
        return summary

    @staticmethod
    def _write_header(path: Path, fields: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()


def _tsv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
