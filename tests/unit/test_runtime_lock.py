from __future__ import annotations

from pathlib import Path

import yaml

from abi.plugins import get_plugin
from abi.runtime_lock import generate_runtime_locks, validate_runtime_locks


def test_resolved_mamba_root_prefers_most_populated_parent(monkeypatch, tmp_path: Path) -> None:
    import abi.config as abi_config
    from abi.plugins.metagenomic_plasmid._engine import config as engine_config

    project = tmp_path / "abi"
    project.mkdir()
    (project / ".mamba" / "envs" / "autoplasm-base").mkdir(parents=True)
    parent_envs = tmp_path / ".mamba" / "envs"
    (parent_envs / "rnaseq").mkdir(parents=True)
    (parent_envs / "wgs").mkdir()

    monkeypatch.delenv("ABI_MAMBA_ROOT", raising=False)
    monkeypatch.delenv("AUTOPLASM_MAMBA_ROOT", raising=False)
    monkeypatch.setattr(abi_config, "PROJECT_ROOT", project)
    monkeypatch.setattr(engine_config, "PROJECT_ROOT", project)

    assert abi_config.resolved_mamba_root() == tmp_path / ".mamba"
    assert engine_config.resolved_mamba_root() == tmp_path / ".mamba"


def test_full_database_profile_uses_canonical_autoplasm_paths(tmp_path: Path) -> None:
    resource_root = tmp_path / "resources" / "autoplasm"
    config = get_plugin("metagenomic_plasmid").load_config(
        db_profile="full",
        overrides={"resources": {"root": str(resource_root)}},
    )

    assert config["resources"]["root"] == str(resource_root)
    assert config["resources"]["bakta"]["database"] == "bakta/db"
    assert config["resources"]["kraken2"]["database"] == "kraken2"


def test_generate_runtime_locks_resolves_extra_path_dirs(tmp_path: Path) -> None:
    project = tmp_path / "abi"
    plugin_dir = project / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    (project / "environments.yaml").write_text(
        yaml.safe_dump(
            {
                "environments": {"demo-env": {"dependencies": ["python=3.10"]}},
                "tool_assignments": {"demo": {"demo_tool": "demo-env"}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (plugin_dir / "tool_registry.yaml").write_text(
        yaml.safe_dump(
            {
                "tools": [
                    {
                        "id": "demo_tool",
                        "name": "Demo Tool",
                        "category": "test",
                        "executable": "demo-tool",
                        "script_path": "{autoplasm_root}/demo/driver.py",
                        "required": True,
                        "extra_path_dirs": ["{autoplasm_root}/demo"],
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    mamba_root = tmp_path / ".mamba"
    (mamba_root / "envs" / "demo-env" / "bin").mkdir(parents=True)
    resource_root = project / "resources"
    tool_dir = resource_root / "autoplasm" / "demo"
    tool_dir.mkdir(parents=True)
    executable = tool_dir / "demo-tool"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    script_path = tool_dir / "driver.py"
    script_path.write_text("print('demo')\n", encoding="utf-8")

    paths = generate_runtime_locks(
        output_dir=project / "locks",
        prefix="test",
        project_root=project,
        mamba_root=mamba_root,
        resource_root=resource_root,
        include_conda_packages=False,
        analysis_types=(),
    )

    tools_lock = yaml.safe_load(Path(paths["tools"]).read_text(encoding="utf-8"))
    tool = tools_lock["tools"][0]
    assert tool["status"] == "ok"
    assert tool["resolved_path"] == str(executable)
    assert tool["script_path"] == str(script_path)
    assert tool["script_present"] is True
    assert tools_lock["summary"]["blocking_missing_tools"] == 0


def test_generate_runtime_locks_resolves_mixed_resource_layout(tmp_path: Path) -> None:
    project = tmp_path / "abi"
    project.mkdir()
    (project / "environments.yaml").write_text(
        yaml.safe_dump({"environments": {}, "tool_assignments": {}}, sort_keys=False),
        encoding="utf-8",
    )

    resource_root = project / "resources"
    autoplasm_root = resource_root / "autoplasm"
    taxonomy_db = autoplasm_root / "amplicon_taxonomy" / "rdp_sintax.fa"
    taxonomy_db.parent.mkdir(parents=True)
    taxonomy_db.write_text(">ref;tax=d:Bacteria,p:Example;\nACGT\n", encoding="utf-8")
    for relative_path in (
        "kneaddata_host",
        "kraken2",
        "humann/chocophlan",
        "humann/uniref",
        "metaphlan",
        "amrfinderplus",
    ):
        (autoplasm_root / relative_path).mkdir(parents=True)

    star_index = resource_root / "star_index"
    star_index.mkdir(parents=True)
    annotation_gtf = resource_root / "NC_000913.3.gtf"
    annotation_gtf.write_text('chr1\tABI\tgene\t1\t4\t.\t+\t.\tgene_id "g1";\n', encoding="utf-8")

    paths = generate_runtime_locks(
        output_dir=project / "locks",
        prefix="test",
        project_root=project,
        mamba_root=tmp_path / ".mamba",
        resource_root=resource_root,
        include_conda_packages=False,
        db_profile="full",
        analysis_types=(
            "amplicon_16s",
            "easymetagenome",
            "rnaseq_expression",
            "wgs_bacteria",
        ),
    )

    resources_lock = yaml.safe_load(Path(paths["resources"]).read_text(encoding="utf-8"))
    assert resources_lock["db_profile"] == "full"
    runtime_lock = yaml.safe_load(Path(paths["runtime"]).read_text(encoding="utf-8"))
    assert runtime_lock["project"]["version"]
    amplicon_rows = resources_lock["analyses"]["amplicon_16s"]["resources"]
    taxonomy_row = next(row for row in amplicon_rows if row["resource_id"] == "taxonomy_db")
    assert taxonomy_row["path"] == str(taxonomy_db)
    assert taxonomy_row["status"] == "ok"

    easymeta_rows = resources_lock["analyses"]["easymetagenome"]["resources"]
    easymeta_paths = {row["resource_id"]: row["path"] for row in easymeta_rows}
    assert easymeta_paths["host_db"] == str(autoplasm_root / "kneaddata_host")
    assert easymeta_paths["kraken2_db"] == str(autoplasm_root / "kraken2")
    assert easymeta_paths["metaphlan_db"] == str(autoplasm_root / "metaphlan")

    rnaseq_rows = resources_lock["analyses"]["rnaseq_expression"]["resources"]
    rnaseq_paths = {row["resource_id"]: row["path"] for row in rnaseq_rows}
    assert rnaseq_paths["genome_index"] == str(star_index)
    assert rnaseq_paths["annotation_gtf"] == str(annotation_gtf)

    wgs_rows = resources_lock["analyses"]["wgs_bacteria"]["resources"]
    amrfinder_row = next(row for row in wgs_rows if row["resource_id"] == "amrfinder_db")
    assert amrfinder_row["path"] == str(autoplasm_root / "amrfinderplus")


def test_validate_runtime_locks_rejects_reproducibility_gaps(tmp_path: Path) -> None:
    lock_payloads = {
        "conda": {
            "kind": "abi-conda-lock",
            "packages_included": True,
            "summary": {
                "missing_envs": ["missing-env"],
                "extra_envs": ["extra-env"],
            },
            "environments": {
                "broken-env": {"package_error": "conda list failed"},
            },
        },
        "tools": {
            "kind": "abi-tools-lock",
            "summary": {"missing_tools": 1, "blocking_missing_tools": 1},
            "tools": [
                {
                    "plugin": "demo",
                    "tool_id": "missing-tool",
                    "status": "missing",
                    "blocking": True,
                },
            ],
        },
        "resources": {
            "kind": "abi-resources-lock",
            "analyses": {
                "demo": {
                    "error": "",
                    "resources": [
                        {
                            "resource_id": "demo-db",
                            "status": "not_configured",
                            "path": "DEMO_DB_NOT_CONFIGURED",
                        }
                    ],
                }
            },
        },
        "runtime": {
            "kind": "abi-runtime-lock",
            "project": {"version": "", "git_commit": "abc123", "git_dirty": True},
            "summary": {},
        },
    }
    paths = {}
    for name, payload in lock_payloads.items():
        path = tmp_path / f"test.{name}.lock.yaml"
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        paths[name] = str(path)

    issues = validate_runtime_locks(paths)

    assert issues == [
        "Conda environments missing from runtime: missing-env",
        "Undeclared Conda environments present: extra-env",
        "Conda package snapshot failed for broken-env: conda list failed",
        "Registered tool is unresolved: demo/missing-tool",
        "Resource is not ready: demo/demo-db (not_configured): DEMO_DB_NOT_CONFIGURED",
        "ABI package version is missing from runtime lock",
        "Project worktree is dirty at abc123; release locks require a clean commit",
    ]

    lock_payloads["conda"]["summary"] = {"missing_envs": [], "extra_envs": []}
    lock_payloads["conda"]["environments"] = {}
    lock_payloads["tools"]["tools"][0]["blocking"] = False
    lock_payloads["tools"]["tools"].append(
        {
            "plugin": "unselected",
            "tool_id": "required-tool",
            "status": "missing",
            "blocking": True,
        }
    )
    lock_payloads["resources"]["analyses"]["demo"]["resources"][0]["tool_id"] = "missing-tool"
    lock_payloads["resources"]["analyses"]["demo"]["resources"][0]["release_required"] = False
    lock_payloads["runtime"]["project"]["version"] = "1.5.5"
    lock_payloads["runtime"]["project"]["git_dirty"] = False
    for name, payload in lock_payloads.items():
        Path(paths[name]).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert validate_runtime_locks(paths) == []
    assert validate_runtime_locks(paths, require_all_tools=True) == [
        "Registered tool is unresolved: demo/missing-tool",
        "Resource is not ready: demo/demo-db (not_configured): DEMO_DB_NOT_CONFIGURED",
    ]

    runtime_project = lock_payloads["runtime"]["project"]
    runtime_project["git_commit"] = ""
    runtime_project["git_error"] = "fatal: not a git repository"
    Path(paths["runtime"]).write_text(
        yaml.safe_dump(lock_payloads["runtime"], sort_keys=False), encoding="utf-8"
    )
    assert validate_runtime_locks(paths) == [
        "Git identity audit failed: fatal: not a git repository",
        "Git commit is missing from runtime lock",
    ]
