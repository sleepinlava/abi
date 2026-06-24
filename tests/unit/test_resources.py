from pathlib import Path

from abi.autoplasm.resources import (
    check_resources,
    fetch_example_dataset,
    required_resource_issues,
    setup_resources,
    sha256_path,
)
from abi.resources import check_resources as check_abi_resources
from abi.resources import setup_resources as setup_abi_resources


def test_setup_resources_mock_writes_manifest(tmp_path):
    config = {"resources": {"root": str(tmp_path / "resources")}}

    rows = setup_resources(config, resource_ids=["genomad", "bakta"], mock=True)

    assert {row["resource_id"] for row in rows} == {"genomad", "bakta"}
    assert all(row["status"] == "ok" for row in rows)
    assert (tmp_path / "resources" / "resources.json").exists()
    genomad = check_resources(config, resource_ids=["genomad"])[0]
    assert genomad["status"] == "ok"
    assert genomad["ready_check"] == "ready sentinel found"
    assert genomad["directory_file_count"] >= 1
    assert "directory_size_bytes" in genomad


def test_wgs_mock_resource_uses_safe_outdir_for_placeholder_path(tmp_path):
    config = {
        "outdir": str(tmp_path / "results"),
        "resources": {"amrfinder_db": "/path/to/amrfinderplus/database"},
    }

    rows = setup_abi_resources(
        analysis_type="wgs_bacteria",
        config=config,
        resource_ids=["amrfinder_db"],
        mock=True,
    )

    target = tmp_path / "results" / "resources" / "amrfinder_db"
    assert rows[0]["path"] == str(target)
    assert (target / ".abi_mock_resource").is_file()


def test_rnaseq_resource_filter_is_exact():
    config = {
        "resources": {
            "annotation_gtf": "ANNOTATION_GTF_NOT_CONFIGURED",
            "genome_index": "GENOME_INDEX_NOT_CONFIGURED",
        }
    }

    rows = check_abi_resources(
        analysis_type="rnaseq_expression",
        config=config,
        resource_ids=["annotation_gtf"],
    )

    assert [row["resource_id"] for row in rows] == ["annotation_gtf"]


def test_setup_resources_reports_progress(tmp_path):
    config = {"resources": {"root": str(tmp_path / "resources")}}
    events = []

    setup_resources(
        config,
        resource_ids=["genomad"],
        mock=True,
        progress_callback=lambda event, resource_id, message: events.append(
            (event, resource_id, message)
        ),
    )

    assert events[0] == ("start", "genomad", "preparing")
    assert events[-1] == ("finish", "genomad", "ok")


def test_setup_resources_uses_env_path_for_resource_dependencies(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "autoplasm-annotation" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    bakta_db = env_bin / "bakta_db"
    bakta_db.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                "command -v amrfinder >/dev/null",
                "out=''",
                'while [ "$#" -gt 0 ]; do',
                '  case "$1" in',
                '    --output) shift; out="$1" ;;',
                "  esac",
                "  shift || true",
                "done",
                'mkdir -p "$out"',
                "printf 'ok\\n' > \"$out/bakta.db\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    bakta_db.chmod(0o755)
    amrfinder = env_bin / "amrfinder"
    amrfinder.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    amrfinder.chmod(0o755)

    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = setup_resources(config, resource_ids=["bakta"])

    assert rows[0]["status"] == "ok"
    assert (tmp_path / "resources" / "bakta" / "bakta.db").exists()


def test_setup_resources_reports_command_timeout(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "autoplasm-plasmid-detect" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    executable = env_bin / "genomad"
    executable.write_text("#!/usr/bin/env sh\nsleep 2\n", encoding="utf-8")
    executable.chmod(0o755)

    config = {
        "resources": {"root": str(tmp_path / "resources")},
        "execution": {"resource_timeout_seconds": 0.01},
    }
    rows = setup_resources(config, resource_ids=["genomad"])

    assert rows[0]["status"] == "failed"
    assert "timed out" in rows[0]["message"]


def test_setup_resources_skips_existing_ready_database(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "autoplasm-plasmid-detect" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    executable = env_bin / "genomad"
    executable.write_text("#!/usr/bin/env sh\nexit 9\n", encoding="utf-8")
    executable.chmod(0o755)

    resource_root = tmp_path / "resources"
    (resource_root / "genomad" / "genomad_db").mkdir(parents=True)
    config = {"resources": {"root": str(resource_root)}}

    rows = setup_resources(config, resource_ids=["genomad"])

    assert rows[0]["status"] == "ok"
    assert rows[0]["message"] == "Existing database found; download skipped."
    assert rows[0]["ready_check"] == "genomad_db directory found"


def test_setup_resources_downloads_when_target_is_empty_directory(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "autoplasm-plasmid-detect" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    executable = env_bin / "genomad"
    executable.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                'mkdir -p "$2/genomad_db"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    resource_root = tmp_path / "resources"
    (resource_root / "genomad").mkdir(parents=True)
    config = {"resources": {"root": str(resource_root)}}

    rows = setup_resources(config, resource_ids=["genomad"])

    assert rows[0]["status"] == "ok"
    assert (resource_root / "genomad" / "genomad_db").exists()


def test_setup_resources_does_not_overwrite_incomplete_database(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "autoplasm-plasmid-detect" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    executable = env_bin / "genomad"
    executable.write_text("#!/usr/bin/env sh\nexit 9\n", encoding="utf-8")
    executable.chmod(0o755)

    resource_root = tmp_path / "resources"
    incomplete = resource_root / "genomad"
    incomplete.mkdir(parents=True)
    (incomplete / "partial.tmp").write_text("partial\n", encoding="utf-8")
    config = {"resources": {"root": str(resource_root)}}

    rows = setup_resources(config, resource_ids=["genomad"])

    assert rows[0]["status"] == "incomplete"
    assert "download skipped" in rows[0]["message"]
    assert (incomplete / "partial.tmp").exists()


def test_plasmidfinder_install_uses_absolute_install_path(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "autoplasm-annotation" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    python = env_bin / "python"
    marker = tmp_path / "python_args.txt"
    python.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                'printf "%s\\n" "$1" > "' + str(marker) + '"',
                'test -f "$1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    kma_index = env_bin / "kma_index"
    kma_index.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    kma_index.chmod(0o755)

    db_path = Path("relative_plasmidfinder_db")
    absolute_db_path = tmp_path / db_path
    absolute_db_path.mkdir(parents=True)
    (absolute_db_path / "INSTALL.py").write_text("print('install')\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    config = {}

    from abi.autoplasm.resources import _run_plasmidfinder_install

    _run_plasmidfinder_install(config, db_path)

    install_arg = marker.read_text(encoding="utf-8").strip()
    assert install_arg == str((absolute_db_path / "INSTALL.py").resolve())


def test_plasmidfinder_uses_current_database_url(tmp_path):
    config = {"resources": {"root": str(tmp_path / "resources")}}

    rows = setup_resources(config, resource_ids=["plasmidfinder"], dry_run=True)

    assert "https://bitbucket.org/genomicepidemiology/plasmidfinder_db.git" in rows[0]["command"]
    assert rows[0]["source_url"].endswith("plasmidfinder_db.git")


def test_required_resource_issues_for_selected_tools(tmp_path):
    config = {"resources": {"root": str(tmp_path / "resources")}}

    issues = required_resource_issues(config, ["genomad", "bakta"])

    assert len(issues) == 2
    assert "genomad.database" in issues[0]


def test_metaphlan_resource_is_required_when_selected(tmp_path):
    config = {"resources": {"root": str(tmp_path / "resources")}}

    issues = required_resource_issues(config, ["metaphlan"])

    assert len(issues) == 1
    assert "metaphlan.database" in issues[0]


def test_metaphlan_resource_is_included_in_default_setup(tmp_path):
    config = {"resources": {"root": str(tmp_path / "resources")}}

    rows = setup_resources(config, dry_run=True)

    assert "metaphlan" in {row["resource_id"] for row in rows}


def test_fetch_example_dataset_mock(tmp_path):
    outputs = fetch_example_dataset("plasmid_refseq_smoke", tmp_path, mock=True)

    sample_sheet = Path(outputs["sample_sheet"])
    assert sample_sheet.exists()
    assert "NC_002127_1" in sample_sheet.read_text(encoding="utf-8")
    fasta = tmp_path / "NC_002127.1.fasta"
    assert sha256_path(fasta)


def test_wgs_resource_setup_has_real_dry_run_and_mock_paths(tmp_path):
    config = {
        "outdir": str(tmp_path / "wgs"),
        "resources": {"amrfinder_db": "AMRFINDER_DB_NOT_CONFIGURED"},
    }

    planned = setup_abi_resources(analysis_type="wgs_bacteria", config=config, dry_run=True)
    mocked = setup_abi_resources(analysis_type="wgs_bacteria", config=config, mock=True)

    assert planned[0]["status"] == "planned"
    assert planned[0]["command"][0] == "amrfinder_update"
    assert mocked[0]["status"] == "ok"
    assert Path(mocked[0]["path"]).is_dir()


def test_metatranscriptomics_resource_setup_is_actionable_without_build_choice(tmp_path):
    config = {
        "outdir": str(tmp_path / "meta"),
        "resources": {
            "genome_index": "GENOME_INDEX_NOT_CONFIGURED",
            "annotation_gtf": "ANNOTATION_GTF_NOT_CONFIGURED",
        },
    }

    rows = setup_abi_resources(analysis_type="metatranscriptomics", config=config)

    assert {row["resource_id"] for row in rows} == {"genome_index", "annotation_gtf"}
    assert {row["status"] for row in rows} == {"manual_required"}


def test_metatranscriptomics_mock_resources_create_expected_shapes(tmp_path):
    config = {
        "outdir": str(tmp_path / "meta"),
        "resources": {
            "genome_index": "GENOME_INDEX_NOT_CONFIGURED",
            "annotation_gtf": "ANNOTATION_GTF_NOT_CONFIGURED",
        },
    }

    rows = setup_abi_resources(analysis_type="metatranscriptomics", config=config, mock=True)
    paths = {row["resource_id"]: Path(row["path"]) for row in rows}

    assert paths["genome_index"].is_dir()
    assert paths["annotation_gtf"].is_file()


def test_large_plugin_resource_bundles_report_manual_and_support_mock(tmp_path):
    for analysis_type, resource_id in (
        ("easymetagenome", "kraken2_db"),
        ("viral_viwrap", "db_dir"),
    ):
        config = {
            "outdir": str(tmp_path / analysis_type),
            "resources": {resource_id: f"{resource_id.upper()}_NOT_CONFIGURED"},
        }
        manual = setup_abi_resources(analysis_type=analysis_type, config=config)
        mocked = setup_abi_resources(analysis_type=analysis_type, config=config, mock=True)

        assert manual[0]["status"] == "manual_required"
        assert mocked[0]["status"] == "ok"
        assert Path(mocked[0]["path"]).is_dir()


def test_core_resource_orchestrator_delegates_to_plugin_capability(monkeypatch):
    calls = []

    class ResourcePlugin:
        def check_resources(self, config, *, resource_ids=None):
            calls.append(("check", config, resource_ids))
            return [{"status": "checked"}]

        def setup_resources(self, config, *, resource_ids=None, dry_run=False, mock=False):
            calls.append(("setup", config, resource_ids, dry_run, mock))
            return [{"status": "planned"}]

    monkeypatch.setattr("abi.resources.get_plugin", lambda analysis_type: ResourcePlugin())

    assert check_abi_resources(
        analysis_type="external", config={"value": 1}, resource_ids=["db"]
    ) == [{"status": "checked"}]
    assert setup_abi_resources(
        analysis_type="external",
        config={"value": 2},
        resource_ids=["db"],
        dry_run=True,
        mock=True,
    ) == [{"status": "planned"}]
    assert calls == [
        ("check", {"value": 1}, ["db"]),
        ("setup", {"value": 2}, ["db"], True, True),
    ]


def test_core_resource_orchestrator_has_generic_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("abi.resources.get_plugin", lambda analysis_type: object())
    database = tmp_path / "db"
    database.mkdir()
    config = {"outdir": str(tmp_path), "resources": {"database": str(database)}}

    checked = check_abi_resources(analysis_type="external", config=config)
    planned = setup_abi_resources(analysis_type="external", config=config, dry_run=True)

    assert checked[0]["status"] == "ok"
    assert planned[0]["status"] == "planned"


# ---- New tests for Level 1 + Level 2 resources (2026-06-20) ----


def test_level1_resources_included_in_default_setup(tmp_path):
    """All Level 1 (auto_setup=True) resources appear in default dry-run."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = setup_resources(config, dry_run=True)
    ids = {row["resource_id"] for row in rows}

    assert "genomad" in ids
    assert "bakta" in ids
    assert "mob_suite" in ids
    assert "plasmidfinder" in ids
    assert "metaphlan" in ids
    assert "amrfinderplus" in ids
    assert "kraken2" in ids
    assert "gtdbtk" in ids
    assert "checkm2" in ids
    # Level 1 = 9 databases + 4 auto-install tools = 13
    assert len(rows) == 14


def test_level2_resources_excluded_from_default_setup(tmp_path):
    """Level 2 (auto_setup=False) resources are skipped in default setup."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = setup_resources(config, dry_run=True)
    ids = {row["resource_id"] for row in rows}

    assert "plasme" not in ids
    assert "plasx_annotations" not in ids
    assert "plasx_model" not in ids
    assert "copla_refgraph" not in ids
    assert "copla_reflist" not in ids
    assert "blast" not in ids
    assert "plasmidhostfinder" not in ids
    # Level 2 tool specs also excluded
    assert "plasmaag_tool" not in ids
    assert "gplas2_tool" not in ids
    assert "scapp_tool" not in ids
    assert "recycler_tool" not in ids
    assert "copla_tool" not in ids
    assert "plasmidhostfinder_tool" not in ids
    assert "conjscan_tool" not in ids


def test_level2_resources_appear_in_check_resources(tmp_path):
    """Level 2 resources are reported by check_resources with missing status."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = check_resources(config)
    ids = {row["resource_id"] for row in rows}

    assert "plasme" in ids
    assert "plasx_annotations" in ids
    assert "plasx_model" in ids
    assert "copla_refgraph" in ids
    assert "copla_reflist" in ids
    assert "blast" in ids
    assert "plasmidhostfinder" in ids


def test_level2_resources_report_missing_status(tmp_path):
    """Level 2 resources with no path configured report 'missing' status."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = check_resources(config)

    for row in rows:
        if row["resource_id"] == "plasme":
            assert row["status"] == "missing"
            assert "PLASMe" in row.get("source_url", "")


def test_level2_resource_can_be_explicitly_selected(tmp_path):
    """An auto_setup=False resource is included when explicitly selected."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = setup_resources(config, resource_ids=["plasme"], dry_run=True)
    ids = {row["resource_id"] for row in rows}

    assert "plasme" in ids
    assert len(rows) == 1


def test_amrfinderplus_required_resource_issues(tmp_path):
    """required_resource_issues detects missing amrfinderplus database."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    issues = required_resource_issues(config, ["amrfinderplus"])

    assert len(issues) >= 1
    assert any("amrfinderplus.database" in i for i in issues)


def test_gtdbtk_env_var_injection(tmp_path):
    """GTDB-Tk download sets GTDBTK_DATA_PATH in runtime environment."""
    from abi.plugins.metagenomic_plasmid._engine.resources import (
        ResourceSpec,
        _resource_runtime_env,
    )

    root = tmp_path / "resources"
    config = {"resources": {"root": str(root)}}
    spec = ResourceSpec(
        resource_id="gtdbtk",
        tool_id="gtdbtk",
        field="database",
        env_name="autoplasm-stats",
        executable="gtdbtk",
        default_subdir="gtdbtk",
        source_url="https://example.com",
        command_template=["gtdbtk", "db", "download"],
    )

    env = _resource_runtime_env(config, "autoplasm-stats", spec)
    assert "GTDBTK_DATA_PATH" in env
    assert env["GTDBTK_DATA_PATH"] == str(root / "gtdbtk")


def test_checkm2_env_var_injection(tmp_path):
    """CheckM2 download sets CHECKM2DB when path is configured."""
    from abi.plugins.metagenomic_plasmid._engine.resources import (
        ResourceSpec,
        _resource_runtime_env,
    )

    db_path = tmp_path / "checkm2_custom"
    config = {
        "resources": {
            "root": str(tmp_path / "resources"),
            "checkm2": {"database": str(db_path)},
        }
    }
    spec = ResourceSpec(
        resource_id="checkm2",
        tool_id="checkm2",
        field="database",
        env_name="autoplasm-stats",
        executable="checkm2",
        default_subdir="checkm2",
        source_url="https://example.com",
        command_template=["checkm2", "download"],
    )

    env = _resource_runtime_env(config, "autoplasm-stats", spec)
    assert "CHECKM2DB" in env
    assert env["CHECKM2DB"] == str(db_path)


def test_all_resources_in_check_resources(tmp_path):
    """check_resources returns every registered database and tool resource."""
    config = {"resources": {"root": str(tmp_path / "resources")}}
    rows = check_resources(config)
    ids = {row["resource_id"] for row in rows}

    assert len(ids) == 30
    expected_db = {
        "genomad",
        "bakta",
        "mob_suite",
        "plasmidfinder",
        "metaphlan",
        "amrfinderplus",
        "card",
        "kraken2",
        "gtdbtk",
        "checkm2",
        "eggnog_mapper",
        "abricate",
        "plasme",
        "plasx_annotations",
        "plasx_model",
        "copla_refgraph",
        "copla_reflist",
        "blast",
        "plasmidhostfinder",
    }
    expected_tools = {
        "plasme_tool",
        "plasx_tool",
        "platon_tool",
        "macsyfinder_tool",
        "plasmaag_tool",
        "gplas2_tool",
        "scapp_tool",
        "recycler_tool",
        "copla_tool",
        "plasmidhostfinder_tool",
        "conjscan_tool",
    }
    assert ids == expected_db | expected_tools
