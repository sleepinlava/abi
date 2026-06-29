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


def test_download_databases_uses_mob_init_cli_with_directory():
    """download_databases.sh must invoke mob_init via CLI with
    --database_directory so the DB lands in ${MOB_DIR}. The previous
    Python-inline mob_init() call ignored ${MOB_DIR} and wrote to the
    package default, making the subsequent BLAST-index check always fail."""
    script = SCRIPTS_DIR / "download_databases.sh"
    content = script.read_text(encoding="utf-8")
    # CLI invocation passes --database_directory to ${MOB_DIR}.
    assert '--database_directory "${MOB_DIR}"' in content
    # The buggy Python-inline form must be gone.
    assert "mob_suite.mob_init.mob_init()" not in content
    # mob_init is resolved from the annotation env, not system PATH.
    assert "MOB_INIT_BIN" in content
    assert "envs/autoplasm-annotation" in content
    assert "/bin/mob_init" in content


def test_download_databases_checks_env_abs_paths():
    """download_databases.sh must check bakta_db/genomad/mob_init via their
    conda-env absolute paths, not `command -v` on system PATH (the tools live
    in autoplasm-annotation / autoplasm-plasmid-detect envs that may not be
    activated when the script runs)."""
    script = SCRIPTS_DIR / "download_databases.sh"
    content = script.read_text(encoding="utf-8")
    # Env-scoped absolute path variables are defined.
    assert "envs/autoplasm-annotation" in content
    assert "envs/autoplasm-plasmid-detect" in content
    assert "BAKTA_DB_BIN" in content
    assert "GENOMAD_BIN" in content
    # Absolute-path checker is used instead of system-PATH `command -v`.
    assert "check_cmd_abs" in content
    # The old system-PATH check for these tools is gone.
    assert "check_cmd bakta_db" not in content
    assert "check_cmd genomad" not in content


def test_rnaseq_benchmark_has_ncbi_efetch_fallback():
    """setup_rnaseq_benchmark.py must have a tertiary NCBI efetch fallback for
    the GTF (the Ensembl fallback URL previously hardcoded a ".111." version
    segment that 404s once upstream retires that build)."""
    script = SCRIPTS_DIR / "setup_rnaseq_benchmark.py"
    content = script.read_text(encoding="utf-8")
    # Tertiary efetch fallback URL is present.
    assert "eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi" in content
    assert "rettype=gtf" in content
    # The old hardcoded Ensembl ".111." version segment is gone.
    assert "ASM584v2.111.gtf.gz" not in content
    # The GTF download chain references the efetch fallback.
    assert "GTF_EFETCH_URL" in content
