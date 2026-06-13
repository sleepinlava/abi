from pathlib import Path

import pytest

from abi.autoplasm.config import load_config
from abi.autoplasm.schemas import ConfigError


def test_load_config_merges_defaults_and_profile():
    config = load_config("examples/config_minimal.yaml", profile="dry_run")
    assert config["project_name"] == "autoplasm_project"
    assert config["threads"] == 2
    assert config["mock_tools"] is True
    assert config["plasmid_detection"]["tools"] == ["genomad"]
    assert Path(config["input"]["sample_sheet"]).exists()


def test_load_config_resolves_bundled_relative_paths_outside_project_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = load_config("examples/config_minimal.yaml", profile="dry_run")

    assert Path(config["input"]["sample_sheet"]).exists()


def test_execution_config_accepts_parallel_and_dashboard_overrides():
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={
            "execution": {
                "parallel": True,
                "workers": 3,
                "progress": True,
                "dashboard": {
                    "enable": True,
                    "host": "127.0.0.1",
                    "port": 18791,
                    "open_browser": False,
                },
            }
        },
    )

    assert config["execution"]["parallel"] is True
    assert config["execution"]["workers"] == 3
    assert config["execution"]["dashboard"]["enable"] is True


def test_execution_workers_must_be_positive():
    with pytest.raises(ConfigError, match="execution.workers"):
        load_config(
            "examples/config_minimal.yaml",
            profile="dry_run",
            overrides={"execution": {"workers": 0}},
        )
