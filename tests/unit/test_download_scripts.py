"""Regression tests for download-script hardening (Phase 4).

Covers the atomic-download, timeout, retry, and fallback fixes in
``scripts/setup_rnaseq_benchmark.py`` and ``scripts/download_rdp_sintax.sh``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark_module():
    return _load_script_module("_test_rnaseq_benchmark", SCRIPTS_DIR / "setup_rnaseq_benchmark.py")


def test_download_writes_atomically_no_partial_reuse(benchmark_module, tmp_path, monkeypatch):
    """C1: a failed download must not leave a partial file that is reused as valid."""
    dest = tmp_path / "ref.fna.gz"
    part = tmp_path / "ref.fna.gz.part"

    class _FailResponse:
        def __enter__(self) -> "_FailResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            raise OSError("connection reset")

    def _fail_urlopen(url, timeout=300):
        return _FailResponse()

    monkeypatch.setattr(benchmark_module, "urlopen", _fail_urlopen)
    monkeypatch.setattr(benchmark_module.time, "sleep", lambda _: None)

    ok = benchmark_module._download("http://example.com/ref.fna.gz", dest, "genome")
    assert ok is False
    # No partial file left behind, and dest does not exist (so a later retry
    # or fallback actually re-downloads instead of seeing a stale partial).
    assert not dest.exists()
    assert not part.exists()


def test_download_fallback_triggers_when_primary_fails(benchmark_module, tmp_path, monkeypatch):
    """C2: the fallback URL must actually be fetched when the primary fails."""
    dest = tmp_path / "ref.fna.gz"
    calls = []

    class _OkResponse:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def __enter__(self) -> "_OkResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self, size: int = -1) -> bytes:
            if size is None or size < 0:
                return self._data
            out, self._data = self._data[:size], self._data[size:]
            return out

    def _urlopen(url, timeout=300):
        calls.append(url)
        if "fail.example.com" in url:
            raise OSError("primary down")
        return _OkResponse(b"FASTA_DATA")

    monkeypatch.setattr(benchmark_module, "urlopen", _urlopen)
    monkeypatch.setattr(benchmark_module.time, "sleep", lambda _: None)

    ok1 = benchmark_module._download("http://fail.example.com/ref.fna.gz", dest, "genome")
    assert ok1 is False
    ok2 = benchmark_module._download("http://ok.example.com/ref.fna.gz", dest, "genome")
    assert ok2 is True
    # The fallback URL was actually fetched (not short-circuited by a leftover
    # partial file from the failed primary — the C2 bug).
    assert "ok.example.com" in calls[-1]
    assert dest.exists()
    assert dest.read_bytes() == b"FASTA_DATA"


def test_download_enforces_timeout(benchmark_module, tmp_path, monkeypatch):
    """C3: _download must pass a timeout to urlopen (no unlimited hang)."""
    captured = {}

    class _OkResponse:
        def __init__(self) -> None:
            self._sent = False

        def __enter__(self) -> "_OkResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self, size: int = -1) -> bytes:
            if not self._sent:
                self._sent = True
                return b"data"
            return b""

    def _urlopen(url, timeout=300):
        captured["timeout"] = timeout
        return _OkResponse()

    monkeypatch.setattr(benchmark_module, "urlopen", _urlopen)
    dest = tmp_path / "ref.fna.gz"
    benchmark_module._download("http://example.com/ref.fna.gz", dest, "genome")
    assert captured["timeout"] == benchmark_module.DOWNLOAD_TIMEOUT
    assert captured["timeout"] is not None


def test_rdp_script_decompresses_atomically():
    """M8: download_rdp_sintax.sh must decompress to a .tmp file and verify
    before moving into place (regression guard via shell syntax inspection)."""
    script = SCRIPTS_DIR / "download_rdp_sintax.sh"
    content = script.read_text(encoding="utf-8")
    # The atomic pattern requires a temp file and a trap to clean it up.
    assert "FASTA_TMP" in content
    assert "trap cleanup EXIT" in content
    assert 'mv "$FASTA_TMP" "$FASTA_FILE"' in content
    # The previous non-atomic pattern (direct gunzip to FASTA_FILE) is gone.
    assert 'gunzip -c "$GZ_FILE" > "$FASTA_FILE"' not in content
    # Taxonomy annotation ratio threshold (m6): not just TAX_COUNT > 0.
    assert "TAX_COUNT * 10" in content


def test_download_databases_script_no_destructive_rm():
    """M9: download_databases.sh must not `rm -rf` an existing DB dir; it
    should move it aside to a backup."""
    script = SCRIPTS_DIR / "download_databases.sh"
    content = script.read_text(encoding="utf-8")
    assert 'rm -rf "${BAKTA_DIR}"' not in content
    assert 'rm -rf "${GENOMAD_DIR}"' not in content
    assert "mv" in content
    assert ".bak." in content
