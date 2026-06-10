"""Tests for ABI StandardTableManager."""

from __future__ import annotations

from abi.tables import StandardTableManager


def test_ensure_tables_creates_files(tmp_path):
    schemas = {"genes": ["gene_id", "count"], "qc": ["sample_id", "reads"]}
    mgr = StandardTableManager(schemas)
    paths = mgr.ensure_tables(tmp_path)
    assert len(paths) == 2
    for path in paths.values():
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert content.strip()  # has header


def test_append_rows(tmp_path):
    schemas = {"genes": ["gene_id", "count"]}
    mgr = StandardTableManager(schemas)
    mgr.ensure_tables(tmp_path)
    written = mgr.append_rows(tmp_path, {"genes": [{"gene_id": "g1", "count": "100"}]})
    assert "genes" in written
    content = written["genes"].read_text(encoding="utf-8")
    assert "g1" in content
    assert "100" in content


def test_summarize(tmp_path):
    schemas = {"genes": ["gene_id", "count"]}
    mgr = StandardTableManager(schemas)
    mgr.ensure_tables(tmp_path)
    summary = mgr.summarize(tmp_path)
    assert "genes" in summary
    assert summary["genes"]["rows"] == 0


def test_empty_schemas_raises():
    import pytest

    with pytest.raises(ValueError):
        StandardTableManager({})
