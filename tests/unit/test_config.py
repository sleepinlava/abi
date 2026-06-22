from pathlib import Path

import pytest
import yaml

from abi.autoplasm.config import load_config
from abi.autoplasm.schemas import ConfigError
from abi.config import load_yaml


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


def test_yaml_loader_rejects_python_object_constructors(tmp_path):
    malicious = tmp_path / "malicious.yaml"
    malicious.write_text(
        "payload: !!python/object/apply:os.system ['touch should_not_exist']\n",
        encoding="utf-8",
    )

    with pytest.raises(yaml.YAMLError):
        load_yaml(malicious)

    assert not (tmp_path / "should_not_exist").exists()
