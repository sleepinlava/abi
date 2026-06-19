"""Declarative TSV/CSV column mapper for ABI plugin output parsing.

This module provides ``TSVMapper``, a generic parser that reads YAML
declarations (``parsers.yaml``) and maps tool output TSV/CSV columns to
ABI standard table columns — replacing ~14 hand-written Python parsers
that all follow the same ``csv.DictReader`` → remap columns pattern.

Design
~~~~~~
- **TSVMapper**: loads a ``parsers.yaml`` spec and dispatches ``parse()`` calls.
- **generate_rows()**: low-level function that executes one parser spec.
- Extensible via ``source.type`` — currently supports ``"tsv_mapping"``;
  ``"json_mapping"`` and ``"fasta_count"`` can be added later.

Schema (``parsers.yaml``)
~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    parsers:
      amrfinderplus:
        source:
          type: tsv_mapping
          pattern: "*amr*.tsv"
          delimiter: "\\t"
        target_table: amr_profile
        columns:
          gene_symbol:
            sources: ["Gene symbol", "gene_symbol"]
            default: ""
        constants:
          tool: amrfinderplus

Usage::

    from abi.tsv_mapping import TSVMapper
    mapper = TSVMapper.from_yaml(plugin_root / "parsers.yaml")
    rows = mapper.parse("amrfinderplus", output_dir, sample_id="S1")
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

import yaml

_logger = logging.getLogger("abi.tsv_mapping")

__all__ = ["TSVMapper", "generate_rows"]


class TSVMapper:
    """Load parser declarations and map tool output → standard table rows.

    Usage::

        mapper = TSVMapper.from_yaml(plugin_root / "parsers.yaml")
        rows = mapper.parse("amrfinderplus", output_dir, sample_id="S1")
        # rows is List[Dict[str, Any]] (standard table rows)
    """

    def __init__(self, parsers: Mapping[str, Any]) -> None:
        self._parsers: Dict[str, Dict[str, Any]] = {
            str(k): dict(v) for k, v in parsers.items() if isinstance(v, Mapping)
        }

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TSVMapper":
        """Load parser declarations from a YAML file.

        Args:
            path: Path to a ``parsers.yaml`` file.

        Returns:
            A new ``TSVMapper`` instance.  Returns an empty mapper if the file
            does not exist (so plugins can call this unconditionally).
        """
        yaml_path = Path(path)
        if not yaml_path.exists():
            _logger.debug("parsers.yaml not found: %s", yaml_path)
            return cls({})
        with yaml_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, Mapping):
            _logger.warning("parsers.yaml is not a mapping: %s", yaml_path)
            return cls({})
        parsers = data.get("parsers")
        if not isinstance(parsers, Mapping):
            _logger.warning("parsers.yaml missing 'parsers' key: %s", yaml_path)
            return cls({})
        return cls(parsers)

    def parse(
        self,
        tool_id: str,
        output_dir: str | Path,
        *,
        sample_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Parse tool output and return standard table rows.

        Args:
            tool_id: The registered tool ID (matches a key in ``parsers.yaml``).
            output_dir: Directory where the tool wrote its output files.
            sample_id: Sample identifier injected into every row.

        Returns:
            List of row dicts ready for ``StandardTableManager.append_rows()``.
            Returns an empty list if *tool_id* has no declaration or no files
            are found.
        """
        spec = self._parsers.get(tool_id)
        if spec is None:
            return []
        return generate_rows(spec, Path(output_dir), sample_id=sample_id)

    def get_target_table(self, tool_id: str) -> Optional[str]:
        """Return the standard table name for a tool_id, if declared."""
        spec = self._parsers.get(tool_id)
        if spec is None:
            return None
        target = spec.get("target_table")
        return str(target) if target else None

    def has_parser(self, tool_id: str) -> bool:
        """Return True if a declarative parser exists for *tool_id*."""
        return tool_id in self._parsers

    @property
    def tool_ids(self) -> List[str]:
        """List of tool IDs with declared parsers."""
        return sorted(self._parsers.keys())


def generate_rows(
    spec: Mapping[str, Any],
    output_dir: Path,
    *,
    sample_id: str = "",
) -> List[Dict[str, Any]]:
    """Execute one parser spec and return standard table rows.

    This is the low-level entry point.  ``TSVMapper.parse()`` delegates
    to this function after looking up the spec by tool_id.

    Args:
        spec: A single parser declaration dict (from ``parsers.yaml``).
        output_dir: Directory to search for output files.
        sample_id: Sample identifier injected into every row.

    Returns:
        List of row dicts.
    """
    source = spec.get("source")
    if not isinstance(source, Mapping):
        return []
    source_type = source.get("type", "tsv_mapping")
    if source_type == "tsv_mapping":
        return _parse_tsv_mapping(spec, output_dir, sample_id)
    if source_type == "json_mapping":
        return _parse_json_mapping(spec, output_dir, sample_id)
    if source_type == "key_value_log":
        return _parse_key_value_log(spec, output_dir, sample_id)
    _logger.warning("Unknown parser source type: %s", source_type)
    return []


# ── TSV mapping implementation ───────────────────────────────────────────


def _parse_tsv_mapping(
    spec: Mapping[str, Any],
    output_dir: Path,
    sample_id: str,
) -> List[Dict[str, Any]]:
    """Execute a ``tsv_mapping`` parser declaration.

    1. Glob for files matching ``source.pattern``.
    2. Open each file as CSV/TSV with ``source.delimiter``.
    3. For each row, map columns according to the ``columns`` spec.
    4. Inject ``constants`` into every row.
    """
    source = spec.get("source", {})
    pattern = str(source.get("pattern", "*.tsv"))
    delimiter = str(source.get("delimiter", "\t"))
    skip_prefix = source.get("skip_lines_starting_with")
    if skip_prefix is not None:
        skip_prefix = str(skip_prefix)
    # Explicit fieldnames for headerless files (e.g. MLST output)
    explicit_fieldnames = source.get("fieldnames")
    if isinstance(explicit_fieldnames, list):
        explicit_fieldnames = [str(f) for f in explicit_fieldnames]

    columns_spec = spec.get("columns")
    if not isinstance(columns_spec, Mapping):
        _logger.warning("Parser spec missing 'columns' mapping")
        return []

    constants = spec.get("constants")
    if isinstance(constants, Mapping):
        constants = dict(constants)
    else:
        constants = {}

    rows: List[Dict[str, Any]] = []

    for path in sorted(output_dir.glob(pattern)):
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                # Skip comment lines before the header / 跳过表头前的注释行
                lines_iter: Iterator[str]
                if skip_prefix:
                    lines_iter = (line for line in handle if not line.startswith(skip_prefix))
                else:
                    lines_iter = handle

                if explicit_fieldnames:
                    # Headerless file: use reader + explicit fieldnames
                    csv_reader = csv.reader(lines_iter, delimiter=delimiter)
                    fieldnames = explicit_fieldnames
                    for values in csv_reader:
                        csv_row = dict(zip(fieldnames, values))
                        if len(csv_row) < len(fieldnames):
                            continue  # skip incomplete rows
                        row = _map_row(columns_spec, csv_row, fieldnames)
                        row["sample_id"] = sample_id
                        row["source_file"] = str(path)
                        row.update(constants)
                        rows.append(row)
                    continue  # processed with explicit fieldnames

                reader = csv.DictReader(lines_iter, delimiter=delimiter)
                if not reader.fieldnames:
                    continue

                for csv_row in reader:
                    row = _map_row(columns_spec, csv_row, reader.fieldnames)
                    row["sample_id"] = sample_id
                    row["source_file"] = str(path)
                    row.update(constants)
                    rows.append(row)
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            _logger.warning("Failed to parse %s: %s", path, exc)
            continue

    return rows


def _map_row(
    columns_spec: Mapping[str, Any],
    csv_row: Dict[str, Any],
    fieldnames: "Sequence[str]",
) -> Dict[str, Any]:
    """Map one CSV row to standard table columns according to *columns_spec*.

    Resolution order for each target column:
    1. ``sources`` list → try each source name against CSV headers (first match wins).
    2. ``sources_from: last_column`` → use the last column's value.
    3. ``sources_from: column_index`` → use positional index (1-based).
    4. ``default`` → fallback value (default ``""``).
    """
    result: Dict[str, Any] = {}

    for target_key, col_spec in columns_spec.items():
        if not isinstance(col_spec, Mapping):
            result[target_key] = col_spec
            continue

        default = col_spec.get("default", "")

        # Option 1: Named source columns (list) / 命名源列列表
        sources = col_spec.get("sources")
        if isinstance(sources, list):
            value = default
            for src in sources:
                src_str = str(src)
                if src_str in csv_row:
                    value = csv_row[src_str]
                    break
            result[target_key] = value
            continue

        # Option 2: Positional column index (1-based) / 位置索引（从1开始）
        sources_from = col_spec.get("sources_from")
        if sources_from == "last_column":
            if fieldnames:
                last_col = fieldnames[-1]
                result[target_key] = csv_row.get(last_col, default)
            else:
                result[target_key] = default
        elif sources_from == "column_index":
            index = int(col_spec.get("index", 1))
            if 1 <= index <= len(fieldnames):
                col_name = fieldnames[index - 1]
                result[target_key] = csv_row.get(col_name, default)
            else:
                result[target_key] = default
        else:
            # No source declared — use default or look up by target key name
            result[target_key] = csv_row.get(target_key, default)

    return result


# ── JSON mapping implementation ──────────────────────────────────────────


def _parse_json_mapping(
    spec: Mapping[str, Any],
    output_dir: Path,
    sample_id: str,
) -> List[Dict[str, Any]]:
    """Execute a ``json_mapping`` parser declaration.

    Loads JSON files matching ``source.pattern``, navigates to a nested
    ``root_key``, then iterates ``blocks`` to flatten key-value pairs into
    standard table rows.  Designed for fastp JSON output.

    Schema::

        source:
          type: json_mapping
          pattern: "*.json"
          root_key: summary
          blocks:
            before_filtering: {prefix: "before_filtering"}
            after_filtering:  {prefix: "after_filtering"}
        constants:
          tool: fastp
    """
    import json as _json

    source = spec.get("source", {})
    pattern = str(source.get("pattern", "*.json"))
    root_key = source.get("root_key") or None
    blocks = source.get("blocks")
    if not isinstance(blocks, Mapping):
        _logger.warning("json_mapping requires 'blocks' mapping")
        return []

    constants = spec.get("constants")
    if isinstance(constants, Mapping):
        constants = dict(constants)
    else:
        constants = {}

    rows: List[Dict[str, Any]] = []

    for path in sorted(output_dir.glob(pattern)):
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = _json.load(handle)
        except (_json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue

        # Navigate to root key if specified / 导航到根键
        root = data.get(root_key, data) if root_key else data
        if not isinstance(root, dict):
            continue

        for block_name, block_cfg in blocks.items():
            if not isinstance(block_cfg, dict):
                continue
            prefix = str(block_cfg.get("prefix", block_name))
            block_data = root.get(block_name)
            if not isinstance(block_data, dict):
                continue
            for metric, value in block_data.items():
                row: Dict[str, Any] = {
                    "sample_id": sample_id,
                    "metric": f"{prefix}.{metric}",
                    "value": value,
                    "unit": "",
                    "source_file": str(path),
                }
                row.update(constants)
                rows.append(row)

    return rows


# ── Key-value log implementation ─────────────────────────────────────────


def _parse_key_value_log(
    spec: Mapping[str, Any],
    output_dir: Path,
    sample_id: str,
) -> List[Dict[str, Any]]:
    """Execute a ``key_value_log`` parser declaration.

    Reads text log files matching ``source.pattern``, splits each line on a
    ``delimiter``, strips whitespace, and emits one row per key-value pair.
    Designed for STAR ``Log.final.out``, Filtlong, and HiFiAdapterFilt logs.

    Schema::

        source:
          type: key_value_log
          pattern: "*Log.final.out"
          delimiter: "|"
        constants:
          tool: star
    """
    source = spec.get("source", {})
    pattern = str(source.get("pattern", "*Log.final.out"))
    delimiter = str(source.get("delimiter", "|"))

    constants = spec.get("constants")
    if isinstance(constants, Mapping):
        constants = dict(constants)
    else:
        constants = {}

    rows: List[Dict[str, Any]] = []

    for path in sorted(output_dir.glob(pattern)):
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(delimiter, 1)
                    if len(parts) < 2:
                        continue
                    key = parts[0].strip()
                    value = parts[1].strip()
                    row: Dict[str, Any] = {
                        "sample_id": sample_id,
                        "metric": key,
                        "value": value,
                        "unit": "",
                        "source_file": str(path),
                    }
                    row.update(constants)
                    rows.append(row)
        except (OSError, UnicodeDecodeError) as exc:
            _logger.warning("Failed to parse %s: %s", path, exc)
            continue

    return rows
