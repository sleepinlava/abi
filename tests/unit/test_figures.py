from __future__ import annotations

import pytest

from abi.figures.base import FigureEngine, FigureError, FigureSpec, render_figure


def test_figure_spec_validation_reports_unknown_table_column_and_type():
    schemas = {"metrics": ["sample_id", "value"]}

    assert (
        FigureSpec(
            id="ok", type="bar", source_table="metrics", x="sample_id", y="value"
        ).validate_against_schema(schemas)
        is None
    )
    assert "unknown table" in FigureSpec(
        id="bad", type="bar", source_table="missing"
    ).validate_against_schema(schemas)
    assert "unknown column" in FigureSpec(
        id="bad", type="bar", source_table="metrics", x="missing"
    ).validate_against_schema(schemas)
    assert "unknown type" in FigureSpec(
        id="bad", type="line", source_table="metrics"
    ).validate_against_schema(schemas)


def test_figure_engine_tracks_validation_errors_and_optional_skips(tmp_path):
    engine = FigureEngine(
        {"metrics": ["sample_id", "value"]},
        tmp_path / "tables",
        tmp_path / "figures",
    )
    engine.load_specs(
        [
            {
                "id": "optional",
                "type": "bar",
                "source_table": "metrics",
                "x": "sample_id",
                "y": "value",
            },
            {
                "id": "invalid",
                "type": "bar",
                "source_table": "missing",
                "x": "sample_id",
                "y": "value",
            },
        ]
    )

    assert engine.render_all() == {}
    assert engine.skipped_count == 1
    assert len(engine.errors) == 1


def test_required_figure_missing_data_raises(tmp_path):
    spec = FigureSpec(id="required", type="bar", source_table="metrics", required=True)
    with pytest.raises(FigureError, match="empty or missing"):
        render_figure(spec, tables_dir=tmp_path / "tables", figures_dir=tmp_path)


def test_bar_figure_renders_png(tmp_path):
    try:
        import matplotlib  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"matplotlib runtime is unavailable: {exc}")
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "metrics.tsv").write_text("sample_id\tvalue\nS1\t1\nS2\t2\n", encoding="utf-8")
    spec = FigureSpec(
        id="bar",
        type="bar",
        source_table="metrics",
        x="sample_id",
        y="value",
        required=True,
    )

    output = render_figure(spec, tables_dir=tables, figures_dir=tmp_path / "figures")

    assert output is not None
    assert output.is_file()
    assert output.stat().st_size > 0
