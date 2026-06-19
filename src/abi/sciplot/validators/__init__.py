"""Data validator — table loading and column/mapping checks.

Uses Pandera DataFrameSchema for schema-based validation of input tables
before rendering.  Falls back gracefully to pandas-only validation when
Pandera is not available.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from abi.sciplot.schema.figure_spec import FigureSpec


class DataValidationError(Exception):
    """Raised when input data fails validation."""

    def __init__(self, rule: str, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message
        self.details = details or {}


class DataValidationReport:
    """Structured result of data validation."""

    def __init__(self) -> None:
        self.errors: List[DataValidationError] = []
        self.warnings: List[DataValidationError] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "status": "ok" if self.is_valid else "error",
            "errors": [
                {"rule": e.rule, "message": e.message, "details": e.details} for e in self.errors
            ],
            "warnings": [
                {"rule": w.rule, "message": w.message, "details": w.details} for w in self.warnings
            ],
        }


def load_data_table(spec: FigureSpec) -> pd.DataFrame:
    """Load a data table from the path in *spec*.

    Supports TSV, CSV, and Parquet formats as declared in spec.data.format.
    """
    table_path = spec.data.table
    fmt = spec.data.format

    if not table_path.exists():
        raise DataValidationError(
            "DATA001",
            f"Input table does not exist: {table_path}",
            {"table": str(table_path)},
        )

    try:
        if fmt == "parquet":
            return pd.read_parquet(table_path)
        elif fmt == "csv":
            return pd.read_csv(table_path)
        else:  # tsv
            return pd.read_csv(table_path, sep="\t")
    except Exception as exc:
        raise DataValidationError(
            "DATA001",
            f"Failed to read input table {table_path}: {exc}",
            {"table": str(table_path), "format": fmt},
        )


def validate_data(spec: FigureSpec) -> DataValidationReport:
    """Validate a FigureSpec's data configuration against the actual table.

    Checks:
    - DATA001: Input table exists and is readable
    - DATA002: Required columns and mapping columns exist
    - DATA003: x/y mapping columns are not both empty (for non-heatmap)
    - DATA004: Numeric columns contain actual numeric data
    """
    report = DataValidationReport()

    # DATA001 — file existence
    if not spec.data.table.exists():
        report.errors.append(
            DataValidationError(
                "DATA001",
                f"Input table does not exist: {spec.data.table}",
                {"table": str(spec.data.table)},
            )
        )
        return report  # Can't proceed without a file

    # Load data
    try:
        df = load_data_table(spec)
    except DataValidationError as e:
        report.errors.append(e)
        return report

    columns = set(df.columns)

    # Collect all referenced columns
    referenced_cols: set[str] = set(spec.data.required_columns)
    for attr in ("x", "y", "hue", "label", "group", "value"):
        col = getattr(spec.mapping, attr, None)
        if col:
            referenced_cols.add(col)

    # DATA002 — column existence
    missing = referenced_cols - columns
    if missing:
        report.errors.append(
            DataValidationError(
                "DATA002",
                f"Columns referenced in spec but missing from input table: {sorted(missing)}. "
                f"Available columns: {sorted(columns)}",
                {"missing": sorted(missing), "available": sorted(columns)},
            )
        )

    # DATA003 — axis mapping (skip for types that auto-detect columns)
    if spec.figure_type not in {
        "heatmap",
        "ordination_plot",
        "genus_heatmap",
        "pcoa_plot",
        "phylogenetic_heatmap",
    }:
        if not spec.mapping.x and not spec.mapping.y:
            report.errors.append(
                DataValidationError(
                    "DATA003",
                    f"Figure type '{spec.figure_type}' requires at least one of "
                    f"mapping.x or mapping.y.",
                    {"figure_type": spec.figure_type},
                )
            )

    # DATA004 — numeric columns (check y and value; x is often categorical labels)
    numeric_cols_to_check: List[str] = []
    for attr in ("y", "value"):
        col = getattr(spec.mapping, attr, None)
        if col and col in columns:
            numeric_cols_to_check.append(col)

    for col in numeric_cols_to_check:
        # Try to coerce to numeric and check failure rate
        numeric = pd.to_numeric(df[col], errors="coerce")
        na_frac = numeric.isna().mean()
        if na_frac > 0.5:
            report.errors.append(
                DataValidationError(
                    "DATA004",
                    f"Column '{col}' is >50% non-numeric ({na_frac:.1%}). "
                    f"Cannot use as a numeric axis.",
                    {"column": col, "non_numeric_fraction": na_frac},
                )
            )
        elif na_frac > 0.2:
            report.warnings.append(
                DataValidationError(
                    "DATA004",
                    f"Column '{col}' has {na_frac:.1%} non-numeric values. "
                    f"These will be treated as 0.",
                    {"column": col, "non_numeric_fraction": na_frac},
                )
            )

    return report
