"""Tests for ResourceDownloader."""

from __future__ import annotations

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
