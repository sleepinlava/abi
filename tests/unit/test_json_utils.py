"""Unit tests for JSON loading utilities (C5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest

from abi.errors import ABIError
from abi.json_utils import load_json_file, loads_json


class TestLoadsJson:
    def test_valid_json_object(self):
        result = loads_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_json_array_accepted(self):
        result = loads_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_bytes_input_decoded(self):
        result = loads_json(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(ABIError, match=r"Invalid JSON"):
            loads_json("{invalid")

    def test_empty_json_object(self):
        assert loads_json("{}") == {}


class TestLoadJsonFile:
    def test_valid_file(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"a": 1, "b": 2}')
        result = load_json_file(str(path))
        assert result == {"a": 1, "b": 2}

    def test_missing_file_raises(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        with pytest.raises(ABIError, match="Could not read"):
            load_json_file(str(path))

    def test_invalid_json_file_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        with pytest.raises(ABIError, match="Invalid JSON"):
            load_json_file(str(path))

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("")
        with pytest.raises(ABIError, match="Invalid JSON"):
            load_json_file(str(path))
