"""Tests for ResourceDownloader."""

from __future__ import annotations

import json
from pathlib import Path

from abi.resources.downloader import DownloadSpec, ResourceDownloader


def test_url_success_is_atomic_and_writes_sentinel(tmp_path, monkeypatch) -> None:
    downloader = ResourceDownloader(tmp_path)

    def fake_download(url: str, dest: Path) -> None:
        (dest / "payload.txt").write_text("payload", encoding="utf-8")

    monkeypatch.setattr(downloader, "_download_url", fake_download)

    result = downloader.ensure(DownloadSpec(resource_id="db", source_url="https://example/db"))

    assert result.status == "ok"
    assert (tmp_path / "db" / "payload.txt").is_file()
    assert (tmp_path / "db" / ResourceDownloader.SENTINEL).is_file()
    assert not (tmp_path / "db.part").exists()
    assert downloader.check(DownloadSpec(resource_id="db")).status == "ok"


def test_resource_downloader_url_failure_cleans_part(tmp_path, monkeypatch) -> None:
    downloader = ResourceDownloader(tmp_path)

    def failing_download(url: str, dest: Path) -> None:
        (dest / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("boom")

    monkeypatch.setattr(downloader, "_download_url", failing_download)

    result = downloader.ensure(DownloadSpec(resource_id="db", source_url="https://example/db"))

    assert result.status == "error"
    assert "boom" in result.message
    assert not (tmp_path / "db.part").exists()


def test_resource_downloader_mock_creates_sentinel(tmp_path) -> None:
    downloader = ResourceDownloader(tmp_path, mock=True)

    result = downloader.ensure(DownloadSpec(resource_id="mock_db", version="v1"))

    assert result.status == "ok"
    assert (tmp_path / "mock_db" / ResourceDownloader.SENTINEL).is_file()


def test_resource_downloader_batch_ensure(tmp_path) -> None:
    downloader = ResourceDownloader(tmp_path, mock=True)

    results = downloader.batch_ensure(
        [DownloadSpec(resource_id="a"), DownloadSpec(resource_id="b")]
    )

    assert {result.resource_id for result in results} == {"a", "b"}
    assert all(result.status == "ok" for result in results)


class TestIntegrityEnforcement:
    """Integrity fields (expected_checksum, min_file_count, min_size_bytes,
    expected_files) must be enforced at download time and on re-check."""

    def test_checksum_mismatch_marks_corrupted_on_recheck(self, tmp_path) -> None:
        """When expected_checksum is set and the stored resource has a
        different checksum, _check_existing() returns status='corrupted'."""
        downloader = ResourceDownloader(tmp_path)

        # Plant a resource with a known checksum.
        dest = tmp_path / "db"
        dest.mkdir()
        (dest / "data.txt").write_text("hello", encoding="utf-8")

        # Write a sentinel claiming a different checksum.
        fake_sentinel = {
            "abi_version": "2.0",
            "resource_id": "db",
            "tool_id": "",
            "version": "",
            "checksum_algorithm": "sha256",
            "checksum": "aaaabbbbccccddddeeeeffff00001111aaaabbbbccccddddeeeeffff00001111",
            "file_count": 1,
            "total_size_bytes": 5,
            "integrity_validated": True,
            "integrity_checks_passed": True,
            "downloaded_at": "2026-01-01T00:00:00+00:00",
        }
        (dest / downloader.SENTINEL).write_text(json.dumps(fake_sentinel), encoding="utf-8")

        spec = DownloadSpec(
            resource_id="db",
            expected_checksum="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )

        result = downloader.check(spec)
        assert result.status == "corrupted"
        assert "checksum mismatch" in result.message

    def test_checksum_match_passes_recheck(self, tmp_path) -> None:
        """When expected_checksum matches, re-verification passes."""
        downloader = ResourceDownloader(tmp_path)

        dest = tmp_path / "db"
        dest.mkdir()
        (dest / "data.txt").write_text("hello", encoding="utf-8")

        # Compute the actual checksum.
        actual = downloader._compute_checksum(dest, "sha256")

        fake_sentinel = {
            "abi_version": "2.0",
            "resource_id": "db",
            "tool_id": "",
            "version": "",
            "checksum_algorithm": "sha256",
            "checksum": actual,
            "file_count": 1,
            "total_size_bytes": 5,
            "integrity_validated": True,
            "integrity_checks_passed": True,
            "downloaded_at": "2026-01-01T00:00:00+00:00",
        }
        (dest / downloader.SENTINEL).write_text(json.dumps(fake_sentinel), encoding="utf-8")

        spec = DownloadSpec(
            resource_id="db",
            expected_checksum=actual,
        )

        result = downloader.check(spec)
        assert result.status == "ok"

    def test_min_file_count_not_met(self, tmp_path, monkeypatch) -> None:
        """Download succeeds but min_file_count not met → error."""
        downloader = ResourceDownloader(tmp_path)

        def fake_download(url: str, dest: Path) -> None:
            (dest / "payload.txt").write_text("x", encoding="utf-8")

        monkeypatch.setattr(downloader, "_download_url", fake_download)

        spec = DownloadSpec(
            resource_id="db",
            source_url="https://example/db",
            min_file_count=5,
        )

        result = downloader.ensure(spec)
        assert result.status == "error"
        assert "insufficient files" in result.message

    def test_min_size_bytes_not_met(self, tmp_path, monkeypatch) -> None:
        """Download succeeds but min_size_bytes not met → error."""
        downloader = ResourceDownloader(tmp_path)

        def fake_download(url: str, dest: Path) -> None:
            (dest / "payload.txt").write_text("tiny", encoding="utf-8")

        monkeypatch.setattr(downloader, "_download_url", fake_download)

        spec = DownloadSpec(
            resource_id="db",
            source_url="https://example/db",
            min_size_bytes=1024 * 1024,
        )

        result = downloader.ensure(spec)
        assert result.status == "error"
        assert "insufficient size" in result.message

    def test_expected_files_missing(self, tmp_path, monkeypatch) -> None:
        """Download succeeds but expected_file is missing → error."""
        downloader = ResourceDownloader(tmp_path)

        def fake_download(url: str, dest: Path) -> None:
            (dest / "payload.txt").write_text("x", encoding="utf-8")

        monkeypatch.setattr(downloader, "_download_url", fake_download)

        spec = DownloadSpec(
            resource_id="db",
            source_url="https://example/db",
            expected_files=["db.fa", "db.fa.h3m", "db.fa.h3p"],
        )

        result = downloader.ensure(spec)
        assert result.status == "error"
        assert "missing expected files" in result.message

    def test_expected_files_all_present(self, tmp_path, monkeypatch) -> None:
        """Download with all expected files present → ok."""
        downloader = ResourceDownloader(tmp_path)

        def fake_download(url: str, dest: Path) -> None:
            (dest / "db.fa").write_text("seq", encoding="utf-8")
            (dest / "db.fa.h3m").write_text("idx", encoding="utf-8")
            (dest / "db.fa.h3p").write_text("idx2", encoding="utf-8")

        monkeypatch.setattr(downloader, "_download_url", fake_download)

        spec = DownloadSpec(
            resource_id="db",
            source_url="https://example/db",
            expected_files=["db.fa", "db.fa.h3m", "db.fa.h3p"],
        )

        result = downloader.ensure(spec)
        assert result.status == "ok"

    def test_checksum_mismatch_on_download(self, tmp_path, monkeypatch) -> None:
        """Integrity check is run on freshly downloaded resources too."""
        downloader = ResourceDownloader(tmp_path)

        def fake_download(url: str, dest: Path) -> None:
            (dest / "payload.txt").write_text("wrong", encoding="utf-8")

        monkeypatch.setattr(downloader, "_download_url", fake_download)

        spec = DownloadSpec(
            resource_id="db",
            source_url="https://example/db",
            expected_checksum="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )

        result = downloader.ensure(spec)
        assert result.status == "error"
        assert "checksum mismatch" in result.message

    def test_corrupted_on_recheck_min_file_count(self, tmp_path) -> None:
        """Re-check with min_file_count detects corruption."""
        downloader = ResourceDownloader(tmp_path)

        dest = tmp_path / "db"
        dest.mkdir()
        (dest / "data.txt").write_text("hi", encoding="utf-8")

        fake_sentinel = {
            "abi_version": "2.0",
            "resource_id": "db",
            "tool_id": "",
            "version": "",
            "checksum_algorithm": "",
            "checksum": "",
            "file_count": 1,
            "total_size_bytes": 2,
            "integrity_validated": True,
            "integrity_checks_passed": True,
            "downloaded_at": "2026-01-01T00:00:00+00:00",
        }
        (dest / downloader.SENTINEL).write_text(json.dumps(fake_sentinel), encoding="utf-8")

        spec = DownloadSpec(resource_id="db", min_file_count=10)
        result = downloader.check(spec)
        assert result.status == "corrupted"
