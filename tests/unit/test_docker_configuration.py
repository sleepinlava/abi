from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docker_build_inputs_are_not_excluded_from_context():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    active_patterns = {
        line.strip() for line in dockerignore if line.strip() and not line.lstrip().startswith("#")
    }

    assert "docker/" not in active_patterns
    assert "envs/*.yml" not in active_patterns


def test_non_push_docker_build_has_the_local_smoke_test_tag():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")

    assert 'if [ "${{ steps.flags.outputs.push }}" == "false" ]; then' in workflow
    assert '"${{ matrix.image-name }}:latest"' in workflow
    assert "docker run --rm ${{ matrix.image-name }}:latest list-types" in workflow


def test_every_dockerfile_copy_source_exists():
    required_sources = (
        "docker/.condarc",
        "pyproject.toml",
        "README.md",
        "src",
        "plugins",
        "config",
        "scripts",
        "data",
        "envs",
        "examples",
        "golden_traces",
    )

    for source in required_sources:
        assert (ROOT / source).exists(), f"Docker build input is missing: {source}"
