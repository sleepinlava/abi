"""Figure spec loading and validation for ABI plugins.

# Purpose / 目的
Provides a standard way for plugins to load and validate figure specs
from ``figure_specs.yaml`` files.  This module sits between the plugin's
user-facing ``figure_specs.yaml`` and the ``FigureEngine`` that renders them.

# Why a separate module / 为何独立模块
Figure specs are a plugin concern (declared in the plugin directory), but
validation and loading are generic (same logic for every plugin).  This
module provides the generic half; plugins call ``load_figure_specs()``
passing their table schemas for validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List, Mapping, Sequence

from abi.figures.base import FigureSpec

__all__ = [
    "load_figure_specs",
    "validate_figure_specs",
]


def load_figure_specs(
    source: str | Path | Sequence[Mapping[str, Any]],
    *,
    table_schemas: Mapping[str, Iterable[str]],
) -> List[FigureSpec]:
    """Load and validate figure specs from a YAML path or list of dicts.

    # Parameters / 参数
    - **source**: Path to a ``figure_specs.yaml`` file, or a pre-parsed list
      of figure declaration dicts.
    - **table_schemas**: Plugin's standard table schemas (from
      ``plugin.table_schemas()``) for cross-validation.

    # Returns / 返回
    A list of validated ``FigureSpec`` objects.

    # Raises / 异常
    - ``ValueError`` if any spec references an unknown table or column.
    """
    if isinstance(source, (str, Path)):
        from abi.config import load_yaml

        data = load_yaml(Path(source))
        items: Sequence[Mapping[str, Any]] = data.get("figures", [])
    else:
        items = source

    specs: List[FigureSpec] = []
    errors: List[str] = []
    for item in items:
        spec = FigureSpec.from_dict(item)
        err = spec.validate_against_schema(table_schemas)
        if err:
            errors.append(err)
        else:
            specs.append(spec)
    if errors:
        raise ValueError(
            f"Invalid figure specs ({len(errors)} error(s)):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return specs


def validate_figure_specs(
    specs: Sequence[FigureSpec],
    *,
    table_schemas: Mapping[str, Iterable[str]],
) -> List[str]:
    """Validate a list of FigureSpecs against table schemas.

    Returns a list of error messages (empty = all valid).  Unlike
    ``load_figure_specs``, this does not raise on errors — useful
    for linting and CI checks where you want to collect all errors.
    """
    errors: List[str] = []
    for spec in specs:
        err = spec.validate_against_schema(table_schemas)
        if err:
            errors.append(err)
    return errors
