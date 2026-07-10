from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_docker_build_inputs_are_not_excluded_from_context():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    active_patterns = {
        line.strip() for line in dockerignore if line.strip() and not line.lstrip().startswith("#")
    }

    assert "docker/" not in active_patterns
    assert "envs/*.yml" not in active_patterns


def test_conda_mirror_maps_defaults_to_existing_repositories():
    condarc = yaml.safe_load((ROOT / "docker" / ".condarc").read_text(encoding="utf-8"))

    assert "defaults" not in condarc["custom_channels"]
    assert condarc["default_channels"] == [
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
        "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r",
    ]


def test_non_push_docker_build_has_the_local_smoke_test_tag():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")

    assert 'if [ "${{ steps.flags.outputs.push }}" == "false" ]; then' in workflow
    assert '"${{ matrix.image-name }}:latest"' in workflow
    assert "docker run --rm ${{ matrix.image-name }}:latest list-types" in workflow


def test_local_docker_export_disables_registry_attestations():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")

    push_condition = "steps.flags.outputs.push == 'true'"
    assert f"provenance: ${{{{ {push_condition} && 'mode=max' || 'false' }}}}" in workflow
    assert f"sbom: ${{{{ {push_condition} }}}}" in workflow


def test_sdist_contains_files_forced_into_the_wheel():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sdist_section = pyproject.split("[tool.hatch.build.targets.sdist]", maxsplit=1)[1]
    force_include_header = "[tool.hatch.build.targets.sdist.force-include]"
    sdist_section = sdist_section.split(force_include_header, maxsplit=1)[0]

    assert '"environments.yaml"' in sdist_section


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
