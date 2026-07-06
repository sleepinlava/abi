"""Unit tests for the metagenomic_plasmid JSON utilities (_engine/json_utils.py)."""

from __future__ import annotations

import pytest

from abi.plugins.metagenomic_plasmid._engine.json_utils import (
    JSONDataError,
    load_json_file,
    load_json_object,
    loads_json,
)


# ---------------------------------------------------------------------------
# loads_json
# ---------------------------------------------------------------------------
class TestLoadsJson:
    def test_valid_str_returns_dict(self):
        result = loads_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_str_returns_list(self):
        result = loads_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_bytes_input_decoded(self):
        result = loads_json(b'{"x": 1}')
        assert result == {"x": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(JSONDataError, match="Invalid JSON"):
            loads_json("{bad")

    def test_non_utf8_bytes_raises(self):
        with pytest.raises(JSONDataError, match="not valid UTF-8"):
            loads_json(b"\xff\xfe")


# ---------------------------------------------------------------------------
# load_json_file
# ---------------------------------------------------------------------------
class TestLoadJsonFile:
    def test_valid_file_returns_data(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text('{"a": 1}')
        result = load_json_file(path)
        assert result == {"a": 1}

    def test_file_not_found_raises(self, tmp_path):
        path = tmp_path / "missing.json"
        with pytest.raises(JSONDataError, match="Could not read"):
            load_json_file(path)

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid")
        with pytest.raises(JSONDataError, match="Invalid JSON"):
            load_json_file(path)


# ---------------------------------------------------------------------------
# load_json_object
# ---------------------------------------------------------------------------
class TestLoadJsonObject:
    def test_valid_dict_returns_dict(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"ok": true}')
        result = load_json_object(path)
        assert result == {"ok": True}

    def test_list_raises_error(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(JSONDataError, match="Expected a JSON object"):
            load_json_object(path)
