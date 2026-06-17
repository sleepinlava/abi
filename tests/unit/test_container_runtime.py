"""Unit tests for container image resolution and command wrapping (Phase 2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))


from abi.tools import (
    _resolve_container_runtime,
    _wrap_container_command,
    resolve_container_image,
)


class TestResolveContainerImage:
    """Layered container image resolution."""

    def test_returns_none_when_nothing_set(self):
        img = resolve_container_image("fastp", {})
        assert img is None

    def test_flat_metadata_container_image(self):
        img = resolve_container_image("fastp", {"container_image": "docker://test:v1"})
        assert img == "docker://test:v1"

    def test_execution_block_container_image(self):
        img = resolve_container_image(
            "fastp",
            {"execution": {"container_image": "docker://biocontainers/fastp:v0.23"}},
        )
        assert img == "docker://biocontainers/fastp:v0.23"

    def test_config_default_image_overrides_contract(self):
        img = resolve_container_image(
            "fastp",
            {"container_image": "docker://old:v1"},
            config={"execution": {"container": {"default_image": "docker://new:v2"}}},
        )
        assert img == "docker://new:v2"

    def test_config_per_tool_image_overrides_default(self):
        img = resolve_container_image(
            "spades",
            {"container_image": "docker://old:v1"},
            config={
                "execution": {
                    "container": {
                        "default_image": "docker://default:v2",
                        "tool_images": {"spades": "docker://spades:v4"},
                    }
                }
            },
        )
        assert img == "docker://spades:v4"

    def test_cli_image_highest_priority(self):
        img = resolve_container_image(
            "fastp",
            {"container_image": "docker://old:v1"},
            config={"execution": {"container": {"default_image": "docker://cfg:v2"}}},
            cli_image="docker://cli:v3",
        )
        assert img == "docker://cli:v3"

    def test_cli_none_uses_config(self):
        img = resolve_container_image(
            "fastp",
            {},
            config={"execution": {"container": {"default_image": "docker://cfg:v2"}}},
            cli_image=None,
        )
        assert img == "docker://cfg:v2"


class TestContainerCommandWrapping:
    """Container command wrapping for docker/singularity."""

    def test_docker_wrap_basic(self):
        cmd = _wrap_container_command(
            ["fastp", "-i", "input.fq"],
            image="docker://biocontainers/fastp:v1",
            runtime="docker",
        )
        assert "docker" == cmd[0]
        assert "run" in cmd
        assert "docker://biocontainers/fastp:v1" in cmd
        assert "fastp" in cmd

    def test_docker_includes_cpu_memory(self):
        cmd = _wrap_container_command(
            ["fastp"],
            image="img:v1",
            runtime="docker",
            cpu=4,
            memory="8GB",
        )
        assert "--cpus" in cmd
        assert "4" in cmd
        assert "--memory" in cmd
        assert "8GB" in cmd

    def test_singularity_wrap_basic(self):
        cmd = _wrap_container_command(
            ["fastp", "-i", "input.fq"],
            image="docker://biocontainers/fastp:v1",
            runtime="singularity",
        )
        assert "singularity" == cmd[0]
        assert "exec" in cmd
        assert "--bind" in cmd
        assert "docker://biocontainers/fastp:v1" in cmd

    def test_apptainer_is_same_as_singularity(self):
        cmd = _wrap_container_command(
            ["fastp"],
            image="img:v1",
            runtime="apptainer",
        )
        assert cmd[0] == "apptainer"
        assert "exec" in cmd

    def test_bind_mounts_work_dir(self):
        cmd = _wrap_container_command(
            ["fastp"],
            image="img:v1",
            work_dir="/data/results",
            runtime="singularity",
        )
        assert "/data/results:/data/results" in " ".join(cmd)

    def test_docker_volume_mount(self):
        cmd = _wrap_container_command(
            ["fastp"],
            image="img:v1",
            work_dir="/data/results",
            runtime="docker",
        )
        assert "-v" in cmd
        assert "/data/results:/data/results" in " ".join(cmd)


class TestResolveContainerRuntime:
    """Container runtime resolution from env/config/auto-detect."""

    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("ABI_CONTAINER_RUNTIME", "singularity")
        assert _resolve_container_runtime() == "singularity"

    def test_falls_back_to_docker(self, monkeypatch):
        monkeypatch.delenv("ABI_CONTAINER_RUNTIME", raising=False)
        runtime = _resolve_container_runtime({})
        assert runtime in ("docker", "podman", "singularity", "apptainer")
