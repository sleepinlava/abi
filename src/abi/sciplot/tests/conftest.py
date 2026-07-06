"""Shared fixtures for sciplot tests.

Extracted from test_render.py and test_biological_renderers.py to avoid
duplication across test files.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    MappingSpec,
    StatSpec,
    StyleSpec,
)
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


@pytest.fixture(scope="session")
def palette() -> PaletteRegistry:
    """Session-scoped PaletteRegistry with built-in palettes loaded."""
    reg = PaletteRegistry()
    reg.load_builtins()
    return reg


@pytest.fixture(scope="session")
def theme() -> ThemeSpec:
    """Session-scoped test theme (minimal, no custom rcParams)."""
    return ThemeSpec(theme_name="test")


def _make_synthetic_tsv(rows: list[dict]) -> Path:
    """Write synthetic data to a temp TSV and return the path.

    The caller is responsible for unlinking the file after use.
    """
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False)
    df.to_csv(tmp.name, sep="\t", index=False)
    tmp.close()
    return Path(tmp.name)


def make_minimal_fig_spec(
    tmp_path: Path,
    figure_type: str,
    *,
    mapping: MappingSpec | None = None,
    statistics: StatSpec | None = None,
    output_dir: str | None = None,
) -> FigureSpec:
    """Create a minimal ``FigureSpec`` for a given figure type.

    Writes a placeholder TSV so the data table path always exists.
    """
    table = tmp_path / f"{figure_type}.tsv"
    table.write_text("placeholder\n", encoding="utf-8")
    return FigureSpec(
        figure_id=figure_type,
        figure_type=figure_type,
        data=DataSpec(table=table),
        mapping=mapping or MappingSpec(),
        statistics=statistics,
        style=StyleSpec(palette="colorblind_safe"),
        export=ExportSpec(
            output_dir=Path(output_dir) if output_dir else (tmp_path / "figures"),
            basename=figure_type,
        ),
    )


def make_sample_dataframe(
    columns: list[str],
    rows: list[list] | None = None,
    n: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a synthetic pandas DataFrame for renderer tests.

    Args:
        columns: Column names.
        rows: Explicit row data (each row is a list of values).
              If ``None``, generates ``n`` rows of random floats.
        n: Number of synthetic rows (ignored when ``rows`` is provided).
        seed: Random seed for reproducibility.
    """
    if rows is not None:
        return pd.DataFrame(rows, columns=columns)
    rng = np.random.default_rng(seed)
    data = {col: rng.normal(loc=10, scale=3, size=n) for col in columns}
    return pd.DataFrame(data)


# Re-export for backward compatibility with existing tests using _make_synthetic_tsv
# directly imported in test_render.py test classes.
_make_synthetic_tsv  # ensure it is available as a module-level name
