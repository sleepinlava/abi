"""Extended unit tests for abi.workflow.manifest — ResourceManifest edge paths."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from abi.workflow.manifest import (
    ResourceManifest,
    _checksum_path,
    checksum_file,
)


# ── ResourceManifest.__init__ with resources list ───────────────────────


def test_resource_manifest_init_with_resources_returns_clones() -> None:
    """ResourceManifest.__init__ stores clones of resource dicts, not originals."""
    original = [
        {"id": "ref_genome", "path": "resources/genome.fa", "version": "1.0"},
    ]
    manifest = ResourceManifest("test_type", resources=original)
    # resources() returns a list copy
    res = manifest.resources
    assert len(res) == 1
    assert res[0]["id"] == "ref_genome"
    # modifying the original does not affect stored resources
    original[0]["id"] = "modified"
    assert manifest.resources[0]["id"] == "ref_genome"
    # modifying the returned list doesn't affect internal state either
    res.append({"id": "fake", "path": "nowhere"})
    assert len(manifest.resources) == 1


# ── add_resources_from_config(): non-Mapping config → early return ──────


def test_add_resources_from_config_non_mapping_returns_early() -> None:
    """add_resources_from_config() with non-Mapping resources block returns early."""
    manifest = ResourceManifest("test")
    # resources key does not exist → config.get returns empty dict
    manifest.add_resources_from_config({})
    assert manifest.resources == []

    # resources key present but not a Mapping
    manifest.add_resources_from_config({"resources": "not_a_dict"})
    assert manifest.resources == []


# ── add_resources_from_config(): with dict config ──────────────────────


def test_add_resources_from_config_with_dict_config_creates_resources(tmp_path: Path) -> None:
    """add_resources_from_config() reads path/version/source_url from dict values."""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    (db_dir / "database.fa").write_text(">seq\nACGT\n")

    config: Mapping = {
        "resources": {
            "test_db": {
                "path": str(db_dir),
                "version": "2.0",
                "source_url": "https://example.com/db",
                "license": "MIT",
            },
        }
    }
    manifest = ResourceManifest("test")
    manifest.add_resources_from_config(config)
    resources = manifest.resources
    assert len(resources) == 1
    assert resources[0]["id"] == "test_db"
    assert resources[0]["path"] == str(db_dir)
    assert resources[0]["version"] == "2.0"
    assert resources[0]["source_url"] == "https://example.com/db"
    assert resources[0]["license"] == "MIT"


# ── add_resources_from_config(): with plain path config value ───────────


def test_add_resources_from_config_with_plain_path_value(tmp_path: Path) -> None:
    """add_resources_from_config() treats non-dict values as plain paths."""
    ref_file = tmp_path / "ref.fa"
    ref_file.write_text(">ref\nACGT\n")

    config: Mapping = {
        "resources": {
            "reference": str(ref_file),
        }
    }
    manifest = ResourceManifest("test")
    manifest.add_resources_from_config(config)
    resources = manifest.resources
    assert len(resources) == 1
    assert resources[0]["id"] == "reference"
    assert resources[0]["path"] == str(ref_file)


# ── validate(): missing resource path → error ──────────────────────────


def test_validate_missing_resource_path_returns_error() -> None:
    """ResourceManifest.validate() reports error for non-existent resource path."""
    manifest = ResourceManifest("test", resources=[{"id": "missing_db", "path": "/nonexistent/path"}])
    errors = manifest.validate()
    assert len(errors) == 1
    assert "missing_db" in errors[0]
    assert "does not exist" in errors[0]


# ── missing_resources(): returns IDs of non-existent paths ──────────────


def test_missing_resources_returns_ids_of_nonexistent_paths(tmp_path: Path) -> None:
    """missing_resources() returns IDs of resources whose paths don't exist."""
    existing = tmp_path / "exists.fa"
    existing.write_text(">seq\nACGT\n")
    manifest = ResourceManifest(
        "test",
        resources=[
            {"id": "present", "path": str(existing)},
            {"id": "missing", "path": "/no/such/path"},
            {"id": "also_missing", "path": "/another/fake/path"},
        ],
    )
    missing_ids = manifest.missing_resources()
    assert "missing" in missing_ids
    assert "also_missing" in missing_ids
    assert "present" not in missing_ids


# ── checksum_file(): path not regular file → "" ────────────────────────


def test_checksum_file_non_regular_file_returns_empty(tmp_path: Path) -> None:
    """checksum_file() returns '' when path is a directory, not a file."""
    result = checksum_file(tmp_path)  # tmp_path is a directory
    assert result == ""


def test_checksum_file_nonexistent_returns_empty() -> None:
    """checksum_file() returns '' when path does not exist."""
    result = checksum_file("/nonexistent/file_xyz.abc")
    assert result == ""


# ── _checksum_path(): dir vs file branching ────────────────────────────


def test_checksum_path_directory_returns_empty(tmp_path: Path) -> None:
    """_checksum_path() returns '' for a directory (not a file)."""
    result = _checksum_path(tmp_path)
    assert result == ""


def test_checksum_path_regular_file_returns_hash(tmp_path: Path) -> None:
    """_checksum_path() returns a hex digest for a regular file."""
    f = tmp_path / "data.txt"
    f.write_text("hello world")
    result = _checksum_path(f)
    assert len(result) == 64  # SHA-256 hex digest
    assert result == checksum_file(f)
