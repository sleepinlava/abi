"""Schema-driven standard table helpers for ABI plugins.

# Purpose / 目的
Standard tables are the ABI pipeline's primary structured output. They are
declared once (the schema — a mapping of table_name → column_names), written
once per pipeline step, and consumed by downstream tools, reports, and dashboards.

# Pattern / 模式
    1. Declare schemas: {"samples": ["sample_id", "platform", ...], "steps": [...]}
    2. ensure_tables: create .tsv files with headers if they don't exist yet
    3. append_rows / write_table: append data rows, only writing declared columns
    4. summarize: count rows per table for reports

# Why TSV? / 为什么用 TSV？
TSV is simpler than CSV for bioinformatics data (no quoting issues with commas
in sequences, no escaping complexity) and is the de facto standard in the ABI
ecosystem. / TSV 比 CSV 简单，是 ABI 生态的事实标准。

# Schema-driven / 模式驱动
Only columns declared in the schema are written — extra fields in the input
data are silently ignored (extrasaction="ignore"). This prevents schema drift:
if a plugin adds a new field, it won't leak into the TSV until the schema is
updated, keeping consumers stable. / 只写入模式中声明的列，防止模式漂移。
"""

from __future__ import annotations

import csv
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

__all__ = ["StandardTableManager"]


class StandardTableManager:
    """Manages schema-declared TSV tables for pipeline output.

    # Responsibilities / 职责
    - **Schema enforcement**: Only declared table names and columns are allowed.
      Unknown table names raise ValueError. Extra fields in input rows are
      silently dropped (extrasaction="ignore"). / 强制模式约束
    - **Idempotent initialization**: ensure_tables() creates missing .tsv files
      with headers; existing files are left untouched (no data loss). / 幂等初始化
    - **Append-friendly**: write_table() with append=True adds rows without
      re-reading the file; headers are never duplicated. / 追加友好
    - **Summary**: summarize() returns row counts for dashboards and reports. / 汇总行数
    - **Thread-safe**: per-table locks prevent race conditions on concurrent
      writes from parallel pipeline steps. / 每表锁防止多线程竞争写入。

    # Usage pattern / 使用模式
        manager = StandardTableManager({"samples": ["sample_id", "platform"]})
        manager.ensure_tables("output_dir/")
        manager.append_rows(
            "output_dir/", {"samples": [{"sample_id": "S1", "platform": "illumina"}]}
        )
        manager.summarize("output_dir/")  # {"samples": {"rows": 1, "path": "..."}}
    """

    def __init__(self, schemas: Mapping[str, Iterable[str]]) -> None:
        """Initialize with a schema dict: {table_name: [column_name, ...]}.

        # Why convert to list immediately? / 为什么立即转为列表？
        Column order matters for TSV headers. Converting the input iterable to a
        list freezes the order so we don't depend on the caller providing the
        same order every time. / 列顺序很重要，转为列表冻结顺序。
        """
        self.schemas: Dict[str, List[str]] = {
            table_name: list(fields) for table_name, fields in schemas.items()
        }
        if not self.schemas:
            raise ValueError("ABI standard table schemas cannot be empty")
        self._global_lock = threading.Lock()
        self._table_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, table_name: str) -> threading.Lock:
        """Return a per-table lock, creating it on first access."""
        with self._global_lock:
            if table_name not in self._table_locks:
                self._table_locks[table_name] = threading.Lock()
            return self._table_locks[table_name]

    def table_path(self, tables_dir: str | Path, table_name: str) -> Path:
        """Return the filesystem path for a standard table .tsv file.

        # Naming convention / 命名约定
        The file is always {table_name}.tsv in the tables directory. / 文件名
        始终是 {table_name}.tsv。
        """
        if table_name not in self.schemas:
            raise ValueError(f"Unknown ABI standard table: {table_name}")
        return Path(tables_dir) / f"{table_name}.tsv"

    def ensure_tables(self, tables_dir: str | Path) -> Dict[str, Path]:
        """Create .tsv files with headers for all declared tables.

        # Idempotent / 幂等
        Existing files are NOT overwritten — only missing files are created.
        This means ensure_tables() is safe to call multiple times during a
        pipeline run (e.g. once per step). / 只创建缺失文件，不覆盖已有文件。

        # Thread-safe / 线程安全
        Per-table locks prevent duplicate header writes when multiple threads
        call ensure_tables() concurrently on the same schema. / 每表锁防止
        多线程同时创建表头时的竞争。
        """
        paths = {}
        for table_name, fields in self.schemas.items():
            path = self.table_path(tables_dir, table_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock_for(table_name):
                if not path.exists():
                    # Only write header if file doesn't exist yet / 文件不存在时才写表头
                    self._write_header(path, fields)
            paths[table_name] = path
        return paths

    def append_rows(
        self,
        tables_dir: str | Path,
        rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]],
    ) -> Dict[str, Path]:
        """Append rows to multiple tables in one call.

        # Batch convenience / 批量操作便利方法
        Wraps ensure_tables + write_table for each table that has non-empty rows.
        Skips tables with empty row lists entirely (no file write). / 跳过空行列表。
        """
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
        """Write rows to a single standard table.

        # Mode selection / 模式选择
        - append=True and file exists → 'a' mode, no header written (header is
          already in the file from ensure_tables). / 追加模式不写表头
        - append=False or file doesn't exist → 'w' mode, header is written
          before data rows. / 写入模式写表头
        - File exists but is empty → header is written even in append mode
          (covers edge case of truncated files due to crashes). / 空文件也写表头

        # extrasaction="ignore" / 忽略额外字段
        Only fields declared in the schema are written. Extra keys in input rows
        are silently dropped. This is a feature, not a bug: it prevents
        accidental schema drift. / 只写声明的列，防止意外模式漂移。
        """
        if table_name not in self.schemas:
            raise ValueError(f"Unknown ABI standard table: {table_name}")
        fields = self.schemas[table_name]
        path = self.table_path(tables_dir, table_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(rows)
        with self._lock_for(table_name):
            # Determine write mode: append to existing file, or create/overwrite / 确定写入模式
            mode = "a" if append and path.exists() else "w"
            with path.open(mode, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=fields,
                    delimiter="\t",
                    extrasaction="ignore",  # Drop extra keys silently / 静默丢弃额外字段
                    lineterminator="\n",
                )
                # Write header if starting fresh or file is empty / 新模式或空文件写表头
                if mode == "w" or path.stat().st_size == 0:
                    writer.writeheader()
                for row in rows:
                    writer.writerow({field: _tsv_value(row.get(field, "")) for field in fields})
        return path

    def summarize(self, tables_dir: str | Path) -> Dict[str, Dict[str, Any]]:
        """Count rows in all standard tables and return a summary.

        # Performance note / 性能说明
        This reads every .tsv file in full to count rows. For very large tables
        (millions of rows) this is O(n). Consider caching the counts in a
        separate metadata file if summarization becomes a bottleneck. / 大表计数
        是 O(n)，瓶颈时可缓存。
        """
        self.ensure_tables(tables_dir)
        summary = {}
        for table_name in self.schemas:
            path = self.table_path(tables_dir, table_name)
            with self._lock_for(table_name):
                with path.open("r", encoding="utf-8", newline="") as handle:
                    # csv.DictReader skips the header row automatically / DictReader 自动跳表头
                    row_count = sum(1 for _ in csv.DictReader(handle, delimiter="\t"))
            summary[table_name] = {"rows": row_count, "path": str(path)}
        return summary

    @staticmethod
    def _write_header(path: Path, fields: List[str]) -> None:
        """Write only the header line to a new .tsv file.

        Uses csv.DictWriter.writeheader() which writes the field names
        separated by the configured delimiter (tab). / 写入制表符分隔的表头行。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()


def _tsv_value(value: Any) -> str:
    """Coerce any value to a TSV-safe string. None → "".

    # Why not str(None)? / 为什么不用 str(None)？
    `str(None)` produces "None" which is ambiguous in TSV — it could be the
    string a user intended, or it could be a missing value. We convert to ""
    for unambiguity: an empty TSV cell means "no data". / 空 TSV 格明确表示"无数据"。
    """
    if value is None:
        return ""
    return str(value)
