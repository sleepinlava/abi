from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from abi import config as core_config
from abi import resources
from abi.errors import ABIError


def test_public_generic_setup_requires_explicit_mode_and_supports_dry_run_and_mock(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(resources, "get_plugin", lambda analysis_type: object())
    config = {"resources": {"database": str(tmp_path / "database")}}

    checked = resources.check_resources(analysis_type="custom", config=config)
    assert checked[0]["status"] == "missing"
    with pytest.raises(ABIError, match="not implemented"):
        resources.setup_resources(analysis_type="custom", config=config)

    planned = resources.setup_resources(analysis_type="custom", config=config, dry_run=True)[0]
    mocked = resources.setup_resources(analysis_type="custom", config=config, mock=True)[0]
    assert planned["status"] == "planned"
    assert planned["mock"] is False
    assert mocked["status"] == "ok"
    assert mocked["mock"] is True
    assert (tmp_path / "database" / ".abi_mock_resource").is_file()


def test_generic_resource_check_handles_nested_values_filters_and_statuses(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "index").write_text("ready", encoding="utf-8")
    config = {
        "resources": {
            "root": str(tmp_path),
            "empty": "",
            "placeholder": "DB_NOT_CONFIGURED",
            "missing": {"database": str(tmp_path / "missing")},
            "existing": {"path": str(existing)},
        }
    }

    rows = resources._check_generic_resources(
        "metatranscriptomics",
        config,
        resource_ids=["empty", "placeholder", "missing", "existing"],
    )

    assert {row["resource_id"]: row["status"] for row in rows} == {
        "empty": "not_configured",
        "existing": "ok",
        "missing": "missing",
        "placeholder": "not_configured",
    }
    assert (
        next(row for row in rows if row["resource_id"] == "existing")["directory_file_count"] == 1
    )
    assert (
        resources._check_generic_resources(
            "metatranscriptomics", {"resources": []}, resource_ids=None
        )
        == []
    )


def test_manual_bundle_distinguishes_existing_mock_dry_run_and_manual(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    base = {
        "outdir": str(tmp_path / "out"),
        "resources": {
            "ready": str(existing),
            "mocked": "MOCKED_NOT_CONFIGURED",
            "planned": str(tmp_path / "planned"),
            "manual": str(tmp_path / "manual"),
        },
    }

    ready = resources._setup_manual_resource_bundle(
        "viral_viwrap", base, resource_ids=["ready"], dry_run=False, mock=False
    )[0]
    mocked = resources._setup_manual_resource_bundle(
        "viral_viwrap", base, resource_ids=["mocked"], dry_run=False, mock=True
    )[0]
    planned = resources._setup_manual_resource_bundle(
        "viral_viwrap", base, resource_ids=["planned"], dry_run=True, mock=False
    )[0]
    manual = resources._setup_manual_resource_bundle(
        "viral_viwrap", base, resource_ids=["manual"], dry_run=False, mock=False
    )[0]

    assert ready["status"] == "ok"
    assert mocked["status"] == "ok"
    assert mocked["mock"] is True
    assert Path(mocked["path"], ".abi_mock_resource").is_file()
    assert planned["status"] == "planned"
    assert planned["mock"] is False
    assert manual["status"] == "manual_required"


def test_reference_setup_covers_existing_mock_planned_manual_and_selection(tmp_path: Path) -> None:
    existing_gtf = tmp_path / "genes.gtf"
    existing_gtf.write_text("gene", encoding="utf-8")
    config = {
        "outdir": str(tmp_path / "out"),
        "resources": {"annotation_gtf": str(existing_gtf)},
    }

    assert (
        resources._setup_reference_resources(
            "rnaseq_expression",
            config,
            resource_ids=["annotation_gtf"],
            dry_run=False,
            mock=False,
        )[0]["status"]
        == "ok"
    )
    mocked = resources._setup_reference_resources(
        "rnaseq_expression",
        config,
        resource_ids=["genome_index"],
        dry_run=False,
        mock=True,
    )[0]
    planned = resources._setup_reference_resources(
        "rnaseq_expression",
        {**config, "outdir": str(tmp_path / "planned-out")},
        resource_ids=["genome_index"],
        dry_run=True,
        mock=False,
    )[0]
    manual = resources._setup_reference_resources(
        "rnaseq_expression",
        {**config, "outdir": str(tmp_path / "manual-out")},
        resource_ids=["genome_index"],
        dry_run=False,
        mock=False,
    )[0]

    assert Path(mocked["path"], ".abi_mock_resource").is_file()
    assert mocked["mock"] is True
    assert planned["status"] == "planned"
    assert planned["mock"] is False
    assert manual["status"] == "manual_required"


@pytest.mark.parametrize(
    "mode,expected",
    [("dry_run", "planned"), ("mock", "ok"), ("existing", "ok")],
)
def test_wgs_resource_setup_safe_non_network_paths(
    tmp_path: Path, mode: str, expected: str
) -> None:
    target = tmp_path / "amrfinder"
    if mode == "existing":
        target.mkdir()
        (target / "database_format_version.txt").write_text("1", encoding="utf-8")
        # A prior successful install writes the ready sentinel; without it a
        # non-empty dir is now correctly reported as "incomplete" (M6 fix).
        (target / ".abi_ready").write_text("amrfinderplus\n", encoding="utf-8")
    row = resources._setup_wgs_bacteria(
        {"resources": {"amrfinder_db": str(target)}},
        resource_ids=["amrfinder_db"],
        dry_run=mode == "dry_run",
        mock=mode == "mock",
    )[0]

    assert row["status"] == expected
    assert resources._setup_wgs_bacteria({}, resource_ids=["other"], dry_run=True, mock=False) == []


def test_wgs_resource_setup_reports_process_failure_and_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "amrfinder"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout="", stderr="bad db"),
    )
    failed = resources._setup_wgs_bacteria(
        {"resources": {"amrfinder_db": str(target)}},
        resource_ids=None,
        dry_run=False,
        mock=False,
    )[0]
    assert (failed["status"], failed["message"]) == ("error", "bad db")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("cmd", 1)),
    )
    timed_out = resources._setup_wgs_bacteria(
        {"resources": {"amrfinder_db": str(tmp_path / "timeout")}},
        resource_ids=None,
        dry_run=False,
        mock=False,
    )[0]
    assert timed_out["status"] == "error"


def test_rnaseq_special_resource_filter_and_deseq2_detection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ABI_RSCRIPT_PATH", "/opt/Rscript")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="OK: 1.42.0", stderr=""),
    )
    rows = resources._check_rnaseq_expression(
        {"resources": {"genome_index": str(tmp_path)}},
        resource_ids=["deseq2_package"],
    )
    assert len(rows) == 1
    assert rows[-1]["status"] == "ok"
    assert rows[-1]["version"] == "1.42.0"
    assert (
        resources._check_rnaseq_expression(
            {"resources": {"genome_index": str(tmp_path)}},
            resource_ids=["genome_index"],
        )[0]["resource_id"]
        == "genome_index"
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("Rscript")),
    )
    missing = resources._check_rnaseq_expression({}, resource_ids=["deseq2_package"])
    assert missing[-1]["status"] == "not_installed"


def test_rnaseq_setup_missing_script_and_selected_generic_resource(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(core_config, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ABIError, match="setup_rnaseq_env.sh not found"):
        resources._setup_rnaseq_expression({}, resource_ids=None)

    genome = tmp_path / "genome"
    genome.mkdir()
    rows = resources._setup_rnaseq_expression(
        {"resources": {"genome_index": str(genome)}},
        resource_ids=["genome_index"],
    )
    assert [(row["resource_id"], row["status"]) for row in rows] == [("genome_index", "ok")]
    assert rows[0]["mock"] is False

    mock_preview = resources._setup_rnaseq_expression(
        {"resources": {"genome_index": str(genome)}},
        resource_ids=["genome_index"],
        dry_run=True,
        mock=True,
    )
    assert mock_preview[0]["mock"] is True


def test_rnaseq_setup_records_environment_marker_and_generic_resources(
    tmp_path: Path, monkeypatch
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "setup_rnaseq_env.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    mamba_root = tmp_path / "mamba"
    marker = mamba_root / "envs" / "rnaseq" / "lib" / "R" / "library"
    marker.mkdir(parents=True)
    (marker / ".abi_deseq2_installed").write_text("ok", encoding="utf-8")
    genome = tmp_path / "genome"
    genome.mkdir()
    monkeypatch.setattr(core_config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="installed", stderr=""),
    )

    rows = resources._setup_rnaseq_expression(
        {
            "mamba_root": str(mamba_root),
            "resources": {"genome_index": str(genome)},
        },
        resource_ids=None,
        dry_run=False,
    )

    assert rows[0]["status"] == "ok"
    assert "DESeq2 installed: True" in rows[0]["message"]
    assert any(row["resource_id"] == "genome_index" for row in rows)


@pytest.mark.parametrize(
    "content,expected",
    [(">seq;tax=d:Bacteria,p:Firmicutes\nACGT\n", "ok"), (">seq\nACGT\n", "invalid")],
)
def test_amplicon_taxonomy_validation_and_resource_filter(
    tmp_path: Path, content: str, expected: str
) -> None:
    database = tmp_path / "taxonomy.fa"
    database.write_text(content, encoding="utf-8")
    rows = resources._check_amplicon_16s(
        {"resources": {"taxonomy_db": str(database)}}, resource_ids=["taxonomy_db"]
    )
    assert len(rows) == 1
    assert rows[0]["status"] == expected
    assert (
        resources._check_amplicon_16s(
            {"resources": {"taxonomy_db": str(database)}}, resource_ids=["other"]
        )
        == []
    )


def test_amplicon_mock_dry_run_is_planned_and_does_not_execute(tmp_path: Path, monkeypatch) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "generate_synthetic_taxonomy.py").write_text("# test", encoding="utf-8")
    monkeypatch.setattr(core_config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: pytest.fail("dry-run executed subprocess")
    )

    rows = resources._setup_amplicon_16s(
        {"outdir": str(tmp_path / "output")},
        resource_ids=["taxonomy_db"],
        dry_run=True,
        mock=True,
    )

    assert rows[0]["status"] == "planned"
    assert rows[0]["mock"] is True
    assert "Would generate" in rows[0]["message"]
    assert not (tmp_path / "output" / "taxonomy").exists()
    assert resources._setup_amplicon_16s({}, resource_ids=["other"], dry_run=True, mock=True) == []


@pytest.mark.parametrize(
    ("analysis_type", "resource_id"),
    [
        ("amplicon_16s", "taxonomy_db"),
        ("easymetagenome", "kraken2_db"),
        ("metagenomic_plasmid", "genomad"),
        ("metatranscriptomics", "genome_index"),
        ("rnaseq_expression", "genome_index"),
        ("viral_viwrap", "db_dir"),
        ("wgs_bacteria", "amrfinder_db"),
    ],
)
def test_every_plugin_marks_mock_dry_run_without_writing(
    tmp_path: Path, analysis_type: str, resource_id: str
) -> None:
    target = tmp_path / analysis_type / resource_id
    config = {
        "outdir": str(tmp_path / analysis_type),
        "resources": {"root": str(tmp_path / analysis_type), resource_id: str(target)},
    }

    rows = resources.setup_resources(
        analysis_type=analysis_type,
        config=config,
        resource_ids=[resource_id],
        dry_run=True,
        mock=True,
    )

    assert rows
    assert all(row["mock"] is True for row in rows)
    assert not target.exists()


def test_amplicon_download_failure_uses_synthetic_fallback(tmp_path: Path, monkeypatch) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "download_rdp_sintax.sh").write_text("# test", encoding="utf-8")
    monkeypatch.setattr(core_config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="offline"),
    )
    called = []

    def _fake_fallback(path: Path) -> bool:
        called.append(path)
        (path / "synthetic_sintax.fa").write_text(">seq1;tax=Bacteria\nACGT\n", encoding="utf-8")
        return True

    monkeypatch.setattr(resources, "_generate_synthetic_fallback", _fake_fallback)

    row = resources._setup_amplicon_16s(
        {"outdir": str(tmp_path / "output")},
        resource_ids=None,
        dry_run=False,
        mock=False,
    )[0]

    assert row["status"] == "fallback"
    assert called == [tmp_path / "output" / "taxonomy"]
    # M7 fix: the returned path must point to the synthetic file that actually
    # exists, not the missing RDP FASTA path.
    assert Path(row["path"]).exists()
    assert row["path"].endswith("synthetic_sintax.fa")
