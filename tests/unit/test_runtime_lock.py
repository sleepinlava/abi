from __future__ import annotations

from pathlib import Path

import yaml

from abi.runtime_lock import generate_runtime_locks


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
                        "required": True,
                        "extra_path_dirs": ["{resource_root}/demo"],
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    mamba_root = tmp_path / ".mamba"
    (mamba_root / "envs" / "demo-env" / "bin").mkdir(parents=True)
    resource_root = project / "resources" / "autoplasm"
    tool_dir = resource_root / "demo"
    tool_dir.mkdir(parents=True)
    executable = tool_dir / "demo-tool"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

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
    assert tools_lock["summary"]["blocking_missing_tools"] == 0
