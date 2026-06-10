"""Tests for ABI config module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from abi.config import compact_overrides, deep_merge, load_yaml, write_yaml


def test_load_yaml(tmp_path):
    p = tmp_path / "test.yaml"
    p.write_text("key: value\nnested:\n  a: 1\n", encoding="utf-8")
    data = load_yaml(p)
    assert data["key"] == "value"
    assert data["nested"]["a"] == 1


def test_load_yaml_missing():
    import pytest

    with pytest.raises(Exception):
        load_yaml(Path("/nonexistent/file.yaml"))


def test_write_yaml(tmp_path):
    p = tmp_path / "out.yaml"
    result = write_yaml({"key": "value"}, p)
    assert result.exists()
    data = yaml.safe_load(result.read_text(encoding="utf-8"))
    assert data["key"] == "value"


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99, "e": 4}, "f": 5}
    result = deep_merge(base, override)
    assert result["a"] == 1
    assert result["b"]["c"] == 99
    assert result["b"]["d"] == 3
    assert result["b"]["e"] == 4
    assert result["f"] == 5


def test_deep_merge_none_skip():
    base = {"a": 1}
    override = {"a": None}
    result = deep_merge(base, override)
    assert result["a"] == 1


def test_compact_overrides():
    result = compact_overrides({"a": 1, "b": None, "c": "hello"})
    assert result == {"a": 1, "c": "hello"}


def test_compact_overrides_nested():
    result = compact_overrides({"a": {"b": 1, "c": None}})
    assert result == {"a": {"b": 1}}


def test_compact_overrides_none():
    assert compact_overrides(None) == {}
