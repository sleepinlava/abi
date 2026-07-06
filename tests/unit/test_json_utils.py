"""Unit tests for top-level JSON loading utilities (abi.json_utils)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abi.json_utils import ABIJSONError, load_json_file, load_json_object, loads_json
from abi.json_utils import _json_decode_message


# ---------------------------------------------------------------------------
# loads_json
# ---------------------------------------------------------------------------
class TestLoadsJson:
    def test_valid_str_returns_dict(self):
        result = loads_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_valid_str_returns_list(self):
        result = loads_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_bytes_input_decoded(self):
        result = loads_json(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_raises_abi_error(self):
        with pytest.raises(ABIJSONError, match=r"Invalid JSON"):
            loads_json("{invalid")

    def test_non_utf8_bytes_raises(self):
        with pytest.raises(ABIJSONError, match="not valid UTF-8"):
            loads_json(b"\xff\xfe\x00\x00")

    def test_custom_label_in_error_message(self):
        with pytest.raises(ABIJSONError, match=r"Invalid JSON in my payload"):
            loads_json("{bad", label="my payload")


# ---------------------------------------------------------------------------
# load_json_file
# ---------------------------------------------------------------------------
class TestLoadJsonFile:
    def test_valid_file_dict(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"a": 1, "b": 2}')
        result = load_json_file(path)
        assert result == {"a": 1, "b": 2}

    def test_valid_file_list(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("[1, 2, 3]")
        result = load_json_file(path)
        assert result == [1, 2, 3]

    def test_file_not_found_raises(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        with pytest.raises(ABIJSONError, match="Could not read"):
            load_json_file(path)

    def test_invalid_json_file_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        with pytest.raises(ABIJSONError, match="Invalid JSON"):
            load_json_file(path)

    def test_custom_label_in_error(self, tmp_path):
        path = tmp_path / "missing.json"
        with pytest.raises(ABIJSONError, match="my custom label"):
            load_json_file(path, label="my custom label")

        path = tmp_path / "bad.json"
        path.write_text("{bad")
        with pytest.raises(ABIJSONError, match="my label"):
            load_json_file(path, label="my label")

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("")
        with pytest.raises(ABIJSONError, match="Invalid JSON"):
            load_json_file(path)

    def test_pathlib_path_accepted(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"x": 1}')
        result = load_json_file(path)
        assert result == {"x": 1}


# ---------------------------------------------------------------------------
# load_json_object
# ---------------------------------------------------------------------------
class TestLoadJsonObject:
    def test_valid_dict_returns_dict(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"a": 1}')
        result = load_json_object(path)
        assert result == {"a": 1}

    def test_list_raises_abi_error(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ABIJSONError, match=r"Expected a JSON object"):
            load_json_object(path)

    def test_with_custom_label(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ABIJSONError, match="my-obj"):
            load_json_object(path, label="my-obj")


# ---------------------------------------------------------------------------
# _json_decode_message
# ---------------------------------------------------------------------------
class TestJsonDecodeMessage:
    def test_formats_line_column_and_message(self):
        exc = None
        try:
            json.loads("{bad")
        except json.JSONDecodeError as e:
            exc = e
        assert exc is not None
        msg = _json_decode_message("PREFIX", exc)
        assert msg.startswith("PREFIX: line ")
        assert "column" in msg
        # exc.msg should be part of the output
        assert exc.msg in msg
