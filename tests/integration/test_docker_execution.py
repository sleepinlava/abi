from __future__ import annotations

import shutil
import subprocess

import pytest


@pytest.mark.smoke
def test_local_docker_can_execute_a_container():
    """Opt-in real container boundary test using an already-cached image."""
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI is not installed")
    image = "busybox:latest"
    inspect = subprocess.run(
        [docker, "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if inspect.returncode != 0:
        pytest.skip(f"{image} is not cached locally; integration test does not pull images")

    result = subprocess.run(
        [docker, "run", "--rm", image, "sh", "-c", "printf ABI_CONTAINER_OK"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ABI_CONTAINER_OK"
