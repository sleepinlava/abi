"""Unit tests for pure functions and data models in abi.figures.base.

These tests require NO matplotlib — they focus on data models, validation,
and string/number parsing.
"""

from __future__ import annotations

import tempfile

import pytest

from abi.figures.base import FigureEngine, FigureSpec, _numeric

# ── _numeric: pure string→float parser ────────────────────────────────────


def test_numeric_positive_float():
    assert _numeric("3.14") == 3.14


def test_numeric_negative_float():
    assert _numeric("-2.5") == -2.5


def test_numeric_integer_string():
    assert _numeric("42") == 42.0


def test_numeric_empty_string():
    assert _numeric("") == 0.0


def test_numeric_na():
    assert _numeric("NA") == 0.0
    assert _numeric("N/A") == 0.0
    assert _numeric("NaN") == 0.0
    assert _numeric("nan") == 0.0
    assert _numeric("None") == 0.0


def test_numeric_whitespace():
    assert _numeric("  ") == 0.0


def test_numeric_non_numeric_string():
    assert _numeric("hello") == 0.0


def test_numeric_none_value():
    assert _numeric(None) == 0.0


# ── FigureSpec.from_dict: dict→dataclass conversion ───────────────────────


def test_from_dict_basic():
    spec = FigureSpec.from_dict({"id": "fig1", "type": "bar", "source_table": "data"})
    assert spec.id == "fig1"
    assert spec.type == "bar"
    assert spec.source_table == "data"


def test_from_dict_figsize_list_to_tuple():
    spec = FigureSpec.from_dict(
        {"id": "f1", "type": "bar", "source_table": "t", "figsize": [10, 6]}
    )
    assert spec.figsize == (10, 6)


def test_from_dict_figsize_already_tuple():
    spec = FigureSpec.from_dict({"id": "f1", "type": "bar", "source_table": "t", "figsize": (8, 4)})
    assert spec.figsize == (8, 4)


def test_from_dict_default_values():
    spec = FigureSpec.from_dict({"id": "f1", "type": "bar", "source_table": "t"})
    assert spec.required is False
    assert spec.dpi == 150
    assert spec.log_y is False
    assert spec.figsize == (10.0, 6.0)


def test_from_dict_extra_keys_filtered():
    spec = FigureSpec.from_dict(
        {"id": "f1", "type": "bar", "source_table": "t", "unknown_key": "value"}
    )
    # Should not raise — extra keys are filtered; spec is still valid
    assert spec.id == "f1"
    assert spec.type == "bar"
    assert spec.source_table == "t"


# ── FigureEngine: init, load_specs, properties ────────────────────────────


def test_engine_init():
    with tempfile.TemporaryDirectory() as tmp:
        engine = FigureEngine(table_schemas={"t": []}, tables_dir=tmp, figures_dir=tmp)
        assert engine.rendered_count == 0
        assert engine.skipped_count == 0
        assert engine.errors == []
        assert engine.specs == []


def test_engine_load_specs_programmatic_list():
    with tempfile.TemporaryDirectory() as tmp:
        engine = FigureEngine(table_schemas={"t": []}, tables_dir=tmp, figures_dir=tmp)
        engine.load_specs([{"id": "fig1", "type": "bar", "source_table": "t"}])
        assert len(engine.specs) == 1
        assert engine.specs[0].id == "fig1"
        assert engine.errors == []


def test_engine_load_specs_invalid_type():
    with tempfile.TemporaryDirectory() as tmp:
        engine = FigureEngine(table_schemas={"t": []}, tables_dir=tmp, figures_dir=tmp)
        engine.load_specs([{"id": "f1", "type": "invalid_type", "source_table": "t"}])
        assert len(engine.errors) > 0
        assert len(engine.specs) == 0  # invalid spec not added


def test_engine_load_specs_mixed_valid_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        engine = FigureEngine(table_schemas={"t": []}, tables_dir=tmp, figures_dir=tmp)
        engine.load_specs(
            [
                {"id": "valid", "type": "bar", "source_table": "t"},
                {"id": "invalid", "type": "bad", "source_table": "missing"},
            ]
        )
        assert len(engine.specs) == 1  # only valid
        assert len(engine.errors) == 1  # one error for invalid


# ── _get_colormap (requires matplotlib) ───────────────────────────────────


def test_get_colormap_invalid_name():
    """Invalid colormap name returns None, regardless of matplotlib availability."""
    from abi.figures.base import _get_colormap

    cmap = _get_colormap("nonexistent_colormap_xyz", 5)
    assert cmap is None


def test_get_colormap_valid():
    """Valid colormap returns list of colors when matplotlib is available."""
    pytest.importorskip("matplotlib")
    from abi.figures.base import _get_colormap

    cmap = _get_colormap("viridis", 5)
    assert cmap is not None
    assert len(cmap) == 5
    # Each entry should be an RGBA tuple (4 floats)
    for color in cmap:
        assert len(color) == 4
