"""Integration tests for FigureEngine.render_all() with real TSV data.

These tests verify end-to-end figure rendering through the FigureEngine,
using real TSV files and matplotlib (no mocking).  Each test constructs a
minimal pipeline: write TSV → load_specs → render_all → assert outputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from abi.figures.base import FigureEngine, FigureError

# All tests require matplotlib — skip the entire module if unavailable.
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")


class TestFigureEngineIntegration:
    """Integration tests for FigureEngine.render_all() with real TSV data."""

    # ── test 1: simplest happy path ────────────────────────────────────────

    def test_render_all_single_bar(self, tmp_path: Path) -> None:
        """1 TSV → 1 bar chart → PNG exists and is non-empty."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        (tables_dir / "metrics.tsv").write_text(
            "sample_id\tvalue\nS1\t1.0\nS2\t2.5\n", encoding="utf-8",
        )

        engine = FigureEngine(
            table_schemas={"metrics": ["sample_id", "value"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "test_bar", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value"},
        ])

        results = engine.render_all()

        assert len(results) == 1
        png = results["test_bar"]
        assert png.is_file()
        assert png.stat().st_size > 0
        assert engine.rendered_count == 1
        assert engine.skipped_count == 0
        assert engine.errors == []

    # ── test 2: two different figure types in one call ─────────────────────

    def test_render_all_two_different_types(self, tmp_path: Path) -> None:
        """2 specs (bar + scatter) in one load_specs → both render → 2 PNGs."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        (tables_dir / "metrics.tsv").write_text(
            "sample_id\tvalue\nS1\t1.0\nS2\t2.5\n", encoding="utf-8",
        )
        (tables_dir / "scatter_data.tsv").write_text(
            "x_val\ty_val\n1.0\t2.0\n3.0\t4.0\n", encoding="utf-8",
        )

        engine = FigureEngine(
            table_schemas={
                "metrics": ["sample_id", "value"],
                "scatter_data": ["x_val", "y_val"],
            },
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "bar_chart", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value"},
            {"id": "scatter_plot", "type": "scatter", "source_table": "scatter_data",
             "x": "x_val", "y": "y_val"},
        ])

        results = engine.render_all()

        assert len(results) == 2
        assert (figures_dir / "bar_chart.png").is_file()
        assert (figures_dir / "scatter_plot.png").is_file()
        assert engine.rendered_count == 2
        assert engine.skipped_count == 0
        assert engine.errors == []

    # ── test 3: optional figure with missing source table → skipped ────────

    def test_render_all_optional_missing_table_skipped(self, tmp_path: Path) -> None:
        """Optional figure with no TSV → skipped_count=1, errors empty, no PNG."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()
        # Do NOT write metrics.tsv

        engine = FigureEngine(
            table_schemas={"metrics": ["sample_id", "value"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "skip_me", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value", "required": False},
        ])

        results = engine.render_all()

        assert results == {}
        assert engine.skipped_count == 1
        assert engine.rendered_count == 0
        assert engine.errors == []
        assert not (figures_dir / "skip_me.png").exists()

    # ── test 4: required figure with missing source table → FigureError ────

    def test_render_all_required_missing_table_raises(self, tmp_path: Path) -> None:
        """Required figure with no TSV → FigureError raised."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        engine = FigureEngine(
            table_schemas={"metrics": ["sample_id", "value"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "must_render", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value", "required": True},
        ])

        with pytest.raises(FigureError, match="empty or missing"):
            engine.render_all()

    # ── test 5: mixed valid + optional missing → renders valid, skips rest ─

    def test_render_all_mixed_valid_and_optional_missing(
        self, tmp_path: Path,
    ) -> None:
        """1 valid spec + 1 optional spec with missing data → valid renders, optional skipped."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        (tables_dir / "metrics.tsv").write_text(
            "sample_id\tvalue\nS1\t1.0\nS2\t2.5\n", encoding="utf-8",
        )
        # Do NOT write missing_table.tsv

        engine = FigureEngine(
            table_schemas={
                "metrics": ["sample_id", "value"],
                "missing_table": ["col_a", "col_b"],
            },
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "valid_bar", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value"},
            {"id": "optional_missing", "type": "bar",
             "source_table": "missing_table",
             "x": "col_a", "y": "col_b", "required": False},
        ])

        results = engine.render_all()

        assert len(results) == 1
        assert "valid_bar" in results
        assert "optional_missing" not in results
        assert (figures_dir / "valid_bar.png").is_file()
        assert not (figures_dir / "optional_missing.png").exists()
        assert engine.rendered_count == 1
        assert engine.skipped_count == 1
        assert engine.errors == []

    # ── test 6: validation error from unknown source_table → tracked ───────

    def test_render_all_spec_validation_error_tracked(
        self, tmp_path: Path,
    ) -> None:
        """Spec with unknown source_table → error tracked in engine.errors, no render."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        engine = FigureEngine(
            table_schemas={"metrics": ["sample_id", "value"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "bad_spec", "type": "bar", "source_table": "nonexistent",
             "x": "sample_id", "y": "value"},
        ])

        results = engine.render_all()

        assert results == {}
        assert engine.rendered_count == 0
        assert engine.skipped_count == 0
        assert len(engine.errors) == 1
        assert "unknown table" in engine.errors[0]
        assert "nonexistent" in engine.errors[0]

    # ── test 7: header-only TSV → optional skipped, required raises ────────

    def test_render_all_empty_tsv_no_png(self, tmp_path: Path) -> None:
        """TSV with header only (no data rows) → optional skipped, required raises."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        (tables_dir / "metrics.tsv").write_text(
            "sample_id\tvalue\n", encoding="utf-8",
        )

        # Case A: optional spec → skipped, no PNG
        engine = FigureEngine(
            table_schemas={"metrics": ["sample_id", "value"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {"id": "opt_empty", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value", "required": False},
        ])
        results = engine.render_all()
        assert results == {}
        assert engine.skipped_count == 1
        assert engine.rendered_count == 0
        assert not (figures_dir / "opt_empty.png").exists()

        # Case B: required spec → FigureError
        engine2 = FigureEngine(
            table_schemas={"metrics": ["sample_id", "value"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine2.load_specs([
            {"id": "req_empty", "type": "bar", "source_table": "metrics",
             "x": "sample_id", "y": "value", "required": True},
        ])
        with pytest.raises(FigureError, match="empty or missing"):
            engine2.render_all()

    # ── test 8: scatter with full spec (title, labels, custom figsize) ─────

    def test_render_all_scatter_with_full_spec(self, tmp_path: Path) -> None:
        """Scatter with title, xlabel, ylabel, custom figsize → PNG exists."""
        tables_dir = tmp_path / "tables"
        figures_dir = tmp_path / "figures"
        tables_dir.mkdir()

        (tables_dir / "data.tsv").write_text(
            "x\ty\n1.0\t2.5\n2.0\t5.0\n3.0\t7.5\n4.0\t10.0\n",
            encoding="utf-8",
        )

        engine = FigureEngine(
            table_schemas={"data": ["x", "y"]},
            tables_dir=tables_dir,
            figures_dir=figures_dir,
        )
        engine.load_specs([
            {
                "id": "fancy_scatter",
                "type": "scatter",
                "source_table": "data",
                "x": "x",
                "y": "y",
                "title": "My Scatter Plot",
                "xlabel": "X Axis",
                "ylabel": "Y Axis",
                "figsize": [12, 8],
            },
        ])

        results = engine.render_all()

        assert len(results) == 1
        png = results["fancy_scatter"]
        assert png.is_file()
        assert png.stat().st_size > 0
        assert engine.rendered_count == 1
        assert engine.skipped_count == 0
        assert engine.errors == []
