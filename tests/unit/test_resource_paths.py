"""Tests for uncovered code paths in abi.resources.

Targets _configured_or_default_resource_path, _setup_wgs_bacteria,
_setup_reference_resources, _download_result_to_row, and
_check_rnaseq_expression with mock-based subprocess/downloader paths.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from abi.resource_downloader import DownloadResult, DownloadSpec, ResourceDownloader
from abi.resources import (
    _check_rnaseq_expression,
    _configured_or_default_resource_path,
    _download_result_to_row,
    _is_placeholder_resource_value,
    _setup_reference_resources,
    _setup_wgs_bacteria,
)


# --------------------------------------------------------------------------- #
#  _configured_or_default_resource_path
# --------------------------------------------------------------------------- #

class TestConfiguredOrDefaultResourcePath:
    """Tests for _configured_or_default_resource_path."""

    def test_configured_path_resolved(self, tmp_path: Path) -> None:
        """When a valid, non-placeholder path is configured, use it directly."""
        target = tmp_path / "my_db"
        target.mkdir()
        config = {"resources": {"my_resource": str(target)}}
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == target

    def test_mapping_value_with_path_key(self, tmp_path: Path) -> None:
        """When value is a Mapping with a path key, extract it."""
        target = tmp_path / "nested_db"
        target.mkdir()
        config = {"resources": {"my_resource": {"path": str(target), "version": "1.0"}}}
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == target

    def test_mapping_value_without_path_key_falls_back_to_outdir(self, tmp_path: Path) -> None:
        """When value is a Mapping without path, fall back to outdir/resources/id."""
        config = {
            "resources": {"my_resource": {"version": "1.0", "database": str(tmp_path / "ignored")}},
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == tmp_path / "results" / "resources" / "my_resource"

    def test_placeholder_value_falls_back_to_outdir(self, tmp_path: Path) -> None:
        """Placeholder values like NOT_CONFIGURED fall back to outdir path."""
        config = {
            "resources": {"my_resource": "DB_NOT_CONFIGURED"},
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == tmp_path / "results" / "resources" / "my_resource"

    def test_placeholder_in_mapping_falls_back_to_outdir(self, tmp_path: Path) -> None:
        """Even when in a Mapping, placeholder path values fall back."""
        config = {
            "resources": {"my_resource": {"path": "NOT_CONFIGURED"}},
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == tmp_path / "results" / "resources" / "my_resource"

    def test_path_prefix_placeholder_falls_back(self, tmp_path: Path) -> None:
        """Placeholder-like prefixes such as /path/to/... fall back."""
        config = {
            "resources": {"my_resource": "/path/to/amrfinderplus/database"},
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == tmp_path / "results" / "resources" / "my_resource"

    def test_resource_not_in_config_falls_back(self, tmp_path: Path) -> None:
        """When resource_id is absent, fall back to outdir/resources/id."""
        config = {
            "resources": {"other": "/real/path"},
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "missing_resource")
        assert result == tmp_path / "results" / "resources" / "missing_resource"

    def test_resources_is_not_mapping_falls_back(self, tmp_path: Path) -> None:
        """When resources is not a Mapping, fall back gracefully."""
        config = {
            "resources": ["list_not_dict"],
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "any_resource")
        assert result == tmp_path / "results" / "resources" / "any_resource"

    def test_default_outdir_when_not_set(self) -> None:
        """When outdir is not configured, use results as default."""
        config: dict = {"resources": {"my_resource": "PLACEHOLDER"}}
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == Path("results") / "resources" / "my_resource"

    def test_empty_string_value_falls_back(self, tmp_path: Path) -> None:
        """Empty string value treated as falsy, falls back."""
        config = {
            "resources": {"my_resource": ""},
            "outdir": str(tmp_path / "results"),
        }
        result = _configured_or_default_resource_path(config, "my_resource")
        assert result == tmp_path / "results" / "resources" / "my_resource"


# --------------------------------------------------------------------------- #
#  _setup_wgs_bacteria
# --------------------------------------------------------------------------- #

class TestSetupWGSBacteria:
    """Tests for _setup_wgs_bacteria covering mock/downloader/incomplete paths."""

    def test_resource_filter_returns_empty(self) -> None:
        """When resource_ids does not include amrfinder_db, return empty list."""
        result = _setup_wgs_bacteria(
            {}, resource_ids=["other"], dry_run=False, mock=False
        )
        assert result == []

    def test_dry_run_returns_planned(self, tmp_path: Path) -> None:
        """Dry run returns planned status via ResourceDownloader."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_wgs_bacteria(
            config, resource_ids=None, dry_run=True, mock=False
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "planned"
        assert rows[0]["mock"] is False
        assert rows[0]["resource_id"] == "amrfinder_db"
        assert rows[0]["path"] == str(target)

    def test_mock_creates_mock_resource(self, tmp_path: Path) -> None:
        """Mock mode uses ResourceDownloader mock path to create resource."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_wgs_bacteria(
            config, resource_ids=None, dry_run=False, mock=True
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "ok"
        assert rows[0]["mock"] is True
        assert rows[0]["path"] == str(target)

    def test_incomplete_directory_no_sentinel(self, tmp_path: Path) -> None:
        """Non-empty directory without sentinel returns incomplete status."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        target.mkdir(parents=True)
        (target / "some_file.txt").write_text("data", encoding="utf-8")
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        rows = _setup_wgs_bacteria(
            config, resource_ids=None, dry_run=False, mock=False
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "incomplete"
        assert "lacks the ready sentinel" in rows[0]["message"]

    def test_incomplete_skipped_when_dry_run(self, tmp_path: Path) -> None:
        """Dry run skips incomplete check and goes through downloader."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        target.mkdir(parents=True)
        (target / "some_file.txt").write_text("data", encoding="utf-8")
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        rows = _setup_wgs_bacteria(
            config, resource_ids=None, dry_run=True, mock=False
        )
        assert rows[0]["status"] == "planned"

    def test_incomplete_skipped_when_mock(self, tmp_path: Path) -> None:
        """Mock mode skips incomplete check."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        target.mkdir(parents=True)
        (target / "some_file.txt").write_text("data", encoding="utf-8")
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        rows = _setup_wgs_bacteria(
            config, resource_ids=None, dry_run=False, mock=True
        )
        assert rows[0]["status"] == "ok"

    def test_existing_sentinel_skips_incomplete_check(self, tmp_path: Path) -> None:
        """When .abi_resource.json sentinel exists, incomplete check is skipped."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        target.mkdir(parents=True)
        (target / "some_file.txt").write_text("data", encoding="utf-8")
        (target / ".abi_resource.json").write_text("{}", encoding="utf-8")
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        # With sentinel present and ResourceDownloader detecting "ok", we mock it
        with patch.object(ResourceDownloader, "ensure") as mock_ensure:
            mock_ensure.return_value = DownloadResult(
                resource_id="amrfinder_db",
                path=target,
                status="ok",
                message="Already ready.",
                file_count=5,
                size_bytes=1024,
            )
            rows = _setup_wgs_bacteria(
                config, resource_ids=None, dry_run=False, mock=False
            )
            assert rows[0]["status"] == "ok"
            assert rows[0]["directory_file_count"] == 5

    def test_legacy_sentinel_skips_incomplete_check(self, tmp_path: Path) -> None:
        """When legacy .abi_ready sentinel exists, incomplete check is skipped."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        target.mkdir(parents=True)
        (target / "some_file.txt").write_text("data", encoding="utf-8")
        (target / ".abi_ready").write_text("amrfinderplus\n", encoding="utf-8")
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        with patch.object(ResourceDownloader, "ensure") as mock_ensure:
            mock_ensure.return_value = DownloadResult(
                resource_id="amrfinder_db",
                path=target,
                status="ok",
                message="Already ready.",
            )
            rows = _setup_wgs_bacteria(
                config, resource_ids=None, dry_run=False, mock=False
            )
            assert rows[0]["status"] == "ok"

    def test_download_error_propagates(self, tmp_path: Path) -> None:
        """When downloader.ensure returns error status, it is propagated."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        with patch.object(ResourceDownloader, "ensure") as mock_ensure:
            mock_ensure.return_value = DownloadResult(
                resource_id="amrfinder_db",
                path=target,
                status="error",
                message="Download failed: network unreachable",
            )
            rows = _setup_wgs_bacteria(
                config, resource_ids=None, dry_run=False, mock=False
            )
            assert rows[0]["status"] == "error"
            assert "network unreachable" in rows[0]["message"]

    def test_configured_resource_id_as_mapping(self, tmp_path: Path) -> None:
        """When amrfinder_db is configured as a Mapping with path key."""
        target = tmp_path / "custom" / "amrfinder_db"
        target.mkdir(parents=True)
        config = {
            "resources": {"amrfinder_db": {"path": str(target)}},
        }
        with patch.object(ResourceDownloader, "ensure") as mock_ensure:
            mock_ensure.return_value = DownloadResult(
                resource_id="amrfinder_db",
                path=target,
                status="ok",
                message="Already ready.",
            )
            rows = _setup_wgs_bacteria(
                config, resource_ids=None, dry_run=False, mock=False
            )
            assert rows[0]["path"] == str(target)

    def test_empty_directory_not_incomplete(self, tmp_path: Path) -> None:
        """Empty directory does not trigger incomplete check (any(iterdir) is False)."""
        target = tmp_path / "results" / "resources" / "amrfinder_db"
        target.mkdir(parents=True)
        # Empty directory - any(target.iterdir()) is False, so no incomplete check
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"amrfinder_db": str(target)},
        }
        with patch.object(ResourceDownloader, "ensure") as mock_ensure:
            mock_ensure.return_value = DownloadResult(
                resource_id="amrfinder_db",
                path=target,
                status="ok",
                message="Ready.",
            )
            rows = _setup_wgs_bacteria(
                config, resource_ids=None, dry_run=False, mock=False
            )
            # Should not be "incomplete" because the dir is empty
            assert rows[0]["status"] == "ok"


# --------------------------------------------------------------------------- #
#  _setup_reference_resources
# --------------------------------------------------------------------------- #

class TestSetupReferenceResources:
    """Tests for _setup_reference_resources covering mock/dry_run/existing paths."""

    def test_dry_run_planned(self, tmp_path: Path) -> None:
        """Dry run returns planned status for both resources."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=None, dry_run=True, mock=False
        )
        assert len(rows) == 2
        assert all(r["status"] == "planned" for r in rows)
        assert all(r["mock"] is False for r in rows)
        ids = {r["resource_id"] for r in rows}
        assert ids == {"genome_index", "annotation_gtf"}

    def test_dry_run_with_mock_message(self, tmp_path: Path) -> None:
        """Dry run with mock=True includes mock-specific message."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=["genome_index"],
            dry_run=True, mock=True,
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "planned"
        assert rows[0]["mock"] is True
        assert "mock" in rows[0]["message"].lower()

    def test_mock_genome_index_creates_resource(self, tmp_path: Path) -> None:
        """Mock mode for genome_index creates ResourceDownloader mock."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=["genome_index"],
            dry_run=False, mock=True,
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "ok"
        assert rows[0]["mock"] is True
        assert rows[0]["resource_id"] == "genome_index"
        assert rows[0]["tool_id"] == "star"

    def test_mock_annotation_gtf_writes_file(self, tmp_path: Path) -> None:
        """Mock mode for annotation_gtf writes a GTF snippet."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=["annotation_gtf"],
            dry_run=False, mock=True,
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "ok"
        assert rows[0]["mock"] is True
        assert Path(rows[0]["path"]).is_file()
        content = Path(rows[0]["path"]).read_text()
        assert "gene_id \"MOCK1\"" in content
        assert rows[0]["tool_id"] == "featurecounts"

    def test_existing_target_is_ok(self, tmp_path: Path) -> None:
        """When target already exists, status is ok."""
        target = tmp_path / "results" / "resources" / "genome_index"
        target.mkdir(parents=True)
        (target / "index_file").write_text("data", encoding="utf-8")
        config = {
            "outdir": str(tmp_path / "results"),
            "resources": {"genome_index": str(target)},
        }
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=["genome_index"],
            dry_run=False, mock=False,
        )
        assert rows[0]["status"] == "ok"
        assert "exists" in rows[0]["message"].lower()

    def test_missing_target_is_manual_required(self, tmp_path: Path) -> None:
        """When target does not exist, status is manual_required."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=["genome_index"],
            dry_run=False, mock=False,
        )
        assert rows[0]["status"] == "manual_required"

    def test_resource_filter_includes_only_selected(self, tmp_path: Path) -> None:
        """When resource_ids is specified, only include those resources."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=["genome_index"],
            dry_run=True, mock=False,
        )
        assert len(rows) == 1
        assert rows[0]["resource_id"] == "genome_index"

    def test_both_resources_with_mock(self, tmp_path: Path) -> None:
        """Both genome_index and annotation_gtf are created in mock mode."""
        config = {"outdir": str(tmp_path / "results"), "resources": {}}
        rows = _setup_reference_resources(
            "rnaseq_expression", config, resource_ids=None,
            dry_run=False, mock=True,
        )
        assert len(rows) == 2
        assert all(r["status"] == "ok" for r in rows)
        assert all(r["mock"] is True for r in rows)
        # genome_index uses ResourceDownloader mock, annotation_gtf writes a file
        gtf_row = next(r for r in rows if r["resource_id"] == "annotation_gtf")
        assert Path(gtf_row["path"]).is_file()


# --------------------------------------------------------------------------- #
#  _download_result_to_row
# --------------------------------------------------------------------------- #

class TestDownloadResultToRow:
    """Tests for _download_result_to_row."""

    def test_basic_conversion(self, tmp_path: Path) -> None:
        """Basic DownloadResult conversion to row dict."""
        d = tmp_path / "resource_dir"
        d.mkdir()
        (d / "f1.txt").write_text("a", encoding="utf-8")
        (d / "f2.txt").write_text("bb", encoding="utf-8")
        result = DownloadResult(
            resource_id="test_resource",
            path=d,
            status="ok",
            version="1.0",
            checksum="abc123",
            file_count=2,
            size_bytes=3,
            downloaded_at="2024-01-01",
            message="All good.",
            command=["cmd", "arg"],
        )
        row = _download_result_to_row(
            result,
            tool_id="test_tool",
            field="test_field",
            source_url="http://example.com",
            ready_check="sentinel",
            mock=True,
        )
        assert row["resource_id"] == "test_resource"
        assert row["tool_id"] == "test_tool"
        assert row["field"] == "test_field"
        assert row["path"] == str(d)
        assert row["status"] == "ok"
        assert row["version"] == "1.0"
        assert row["source_url"] == "http://example.com"
        assert row["checksum"] == "abc123"
        assert row["command"] == ["cmd", "arg"]
        assert row["ready_check"] == "sentinel"
        assert row["directory_file_count"] == 2
        assert row["directory_size_bytes"] == 3
        assert row["message"] == "All good."
        assert row["mock"] is True

    def test_field_falls_back_to_resource_id(self, tmp_path: Path) -> None:
        """When field is empty, use resource_id as field."""
        result = DownloadResult(
            resource_id="my_resource",
            path=tmp_path,
            status="ok",
        )
        row = _download_result_to_row(result)
        assert row["field"] == "my_resource"

    def test_file_count_from_filesystem_when_not_in_result(self, tmp_path: Path) -> None:
        """When file_count is 0/None, count files from filesystem."""
        d = tmp_path / "count_dir"
        d.mkdir()
        (d / "a.txt").write_text("x", encoding="utf-8")
        (d / "b.txt").write_text("y", encoding="utf-8")
        sub = d / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("z", encoding="utf-8")
        result = DownloadResult(
            resource_id="count_test",
            path=d,
            status="ok",
            file_count=0,
        )
        row = _download_result_to_row(result)
        assert row["directory_file_count"] == 3

    def test_size_bytes_from_filesystem_when_not_in_result(self, tmp_path: Path) -> None:
        """When size_bytes is 0/None, compute from filesystem."""
        d = tmp_path / "size_dir"
        d.mkdir()
        (d / "small.txt").write_text("hello", encoding="utf-8")  # 5 bytes
        result = DownloadResult(
            resource_id="size_test",
            path=d,
            status="ok",
            size_bytes=0,
        )
        row = _download_result_to_row(result)
        assert row["directory_size_bytes"] == 5

    def test_file_count_zero_for_non_directory(self, tmp_path: Path) -> None:
        """When path is not a directory, file_count is 0."""
        result = DownloadResult(
            resource_id="no_dir",
            path=tmp_path / "nonexistent",
            status="ok",
            file_count=0,
            size_bytes=0,
        )
        row = _download_result_to_row(result)
        assert row["directory_file_count"] == 0
        assert row["directory_size_bytes"] == 0

    def test_default_parameters(self, tmp_path: Path) -> None:
        """Default parameter values are used correctly."""
        result = DownloadResult(
            resource_id="def_test",
            path=tmp_path,
            status="ok",
        )
        row = _download_result_to_row(result)
        assert row["tool_id"] == ""
        assert row["field"] == "def_test"
        assert row["source_url"] == ""
        assert row["ready_check"] == "sentinel"
        assert row["mock"] is False

    def test_preserves_empty_command_list(self, tmp_path: Path) -> None:
        """Empty or None command is preserved as empty list."""
        result = DownloadResult(
            resource_id="no_cmd",
            path=tmp_path,
            status="ok",
            command=[],
        )
        row = _download_result_to_row(result)
        assert row["command"] == []

        result2 = DownloadResult(
            resource_id="no_cmd2",
            path=tmp_path,
            status="ok",
        )
        row2 = _download_result_to_row(result2)
        assert row2["command"] == []


# --------------------------------------------------------------------------- #
#  _check_rnaseq_expression
# --------------------------------------------------------------------------- #

class TestCheckRNASeqExpression:
    """Tests for _check_rnaseq_expression subprocess paths."""

    def test_filter_skips_when_deseq2_not_selected(self, tmp_path: Path) -> None:
        """When resource_ids specified but does not include deseq2_package, skip."""
        config = {"resources": {"genome_index": str(tmp_path)}}
        rows = _check_rnaseq_expression(
            config, resource_ids=["genome_index"]
        )
        assert len(rows) == 1
        assert rows[0]["resource_id"] == "genome_index"

    def test_deseq2_detection_ok(self, tmp_path: Path) -> None:
        """When subprocess returns OK with version, status is ok."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=0, stdout="OK: 1.42.0\n", stderr=""
            )
            rows = _check_rnaseq_expression(
                config, resource_ids=["deseq2_package"]
            )
            assert rows[-1]["status"] == "ok"
            assert rows[-1]["version"] == "1.42.0"
            assert rows[-1]["resource_id"] == "deseq2_package"

    def test_deseq2_not_installed_timeout(self, tmp_path: Path) -> None:
        """TimeoutExpired results in not_installed status."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("Rscript", 30)
            rows = _check_rnaseq_expression(
                config, resource_ids=["deseq2_package"]
            )
            assert rows[-1]["status"] == "not_installed"
            assert "not installed" in rows[-1]["message"].lower()

    def test_deseq2_not_installed_filenotfound(self, tmp_path: Path) -> None:
        """FileNotFoundError results in not_installed status."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("Rscript not found")
            rows = _check_rnaseq_expression(
                config, resource_ids=["deseq2_package"]
            )
            assert rows[-1]["status"] == "not_installed"

    def test_deseq2_not_installed_oserror(self, tmp_path: Path) -> None:
        """OSError results in not_installed status."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Permission denied")
            rows = _check_rnaseq_expression(
                config, resource_ids=["deseq2_package"]
            )
            assert rows[-1]["status"] == "not_installed"

    def test_deseq2_without_ok_in_output(self, tmp_path: Path) -> None:
        """When subprocess output does not contain OK:, status is not_installed."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=1, stdout="Error: package not found\n", stderr=""
            )
            rows = _check_rnaseq_expression(
                config, resource_ids=["deseq2_package"]
            )
            assert rows[-1]["status"] == "not_installed"
            assert rows[-1]["version"] == ""

    def test_no_resource_filter_includes_deseq2(self, tmp_path: Path) -> None:
        """When resource_ids is None, deseq2_package is included."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=0, stdout="OK: 1.42.0\n", stderr=""
            )
            rows = _check_rnaseq_expression(config, resource_ids=None)
            # Should have at least the deseq2_package row
            deseq2_rows = [r for r in rows if r["resource_id"] == "deseq2_package"]
            assert len(deseq2_rows) == 1
            assert deseq2_rows[0]["status"] == "ok"

    def test_deseq2_message_includes_version_when_ok(self, tmp_path: Path) -> None:
        """When DESeq2 is found, message includes the version string."""
        config = {"resources": {}}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = SimpleNamespace(
                returncode=0, stdout="OK: 1.42.0\n", stderr=""
            )
            rows = _check_rnaseq_expression(
                config, resource_ids=["deseq2_package"]
            )
            assert "1.42.0" in rows[-1]["message"]
            assert "DESeq2 1.42.0 found" in rows[-1]["message"]
