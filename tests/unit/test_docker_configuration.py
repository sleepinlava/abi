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


def test_docker_workflow_watches_the_complete_release_surface():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")

    for path in (
        '".github/workflows/ci.yml"',
        '".github/workflows/docker.yml"',
        '".dockerignore"',
        '"docker/**"',
        '"environments.yaml"',
        '"envs/**"',
        '"pyproject.toml"',
        '"plugins/**"',
        '"scripts/**"',
        '"src/**"',
    ):
        assert path in workflow


def test_python_ci_validates_docker_compose_configuration():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "docker compose -f docker/docker-compose.yml config --quiet" in workflow


def test_local_docker_export_disables_registry_attestations():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")

    push_condition = "steps.flags.outputs.push == 'true'"
    assert f"provenance: ${{{{ {push_condition} && 'mode=max' || 'false' }}}}" in workflow
    assert f"sbom: ${{{{ {push_condition} }}}}" in workflow


def test_rnaseq_registry_build_is_amd64_only_until_arm64_is_validated():
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")

    assert "steps.flags.outputs.push == 'true' && matrix.plugin != 'rnaseq'" in workflow
    assert "'linux/amd64,linux/arm64' || 'linux/amd64'" in workflow


def test_sdist_contains_files_forced_into_the_wheel():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sdist_section = pyproject.split("[tool.hatch.build.targets.sdist]", maxsplit=1)[1]
    force_include_header = "[tool.hatch.build.targets.sdist.force-include]"
    sdist_section = sdist_section.split(force_include_header, maxsplit=1)[0]

    assert '"environments.yaml"' in sdist_section


def test_plasmidfinder_adapter_is_in_packaged_plugin_tree():
    registry = yaml.safe_load(
        (ROOT / "plugins" / "metagenomic_plasmid" / "tool_registry.yaml").read_text(
            encoding="utf-8"
        )
    )
    tool = next(item for item in registry["tools"] if item["id"] == "plasmidfinder")

    assert tool["extra_path_dirs"] == ["{project_root}/plugins/metagenomic_plasmid/scripts"]
    assert (ROOT / "plugins" / "metagenomic_plasmid" / "scripts" / "plasmidfinder.py").is_file()


def test_python_script_tools_use_the_canonical_autoplasm_root():
    plugin_root = ROOT / "plugins" / "metagenomic_plasmid"
    registry = yaml.safe_load((plugin_root / "tool_registry.yaml").read_text(encoding="utf-8"))

    for tool_id, relative_path in (
        ("plasme", "PLASMe/PLASMe.py"),
        ("recycler", "Recycler/bin/recycle.py"),
    ):
        tool = next(item for item in registry["tools"] if item["id"] == tool_id)
        expected_script = f"{{autoplasm_root}}/{relative_path}"
        contract = yaml.safe_load(
            (plugin_root / "tool_contracts" / f"{tool_id}.yaml").read_text(encoding="utf-8")
        )

        assert tool["script_path"] == expected_script
        expected_command_path = f"{{resource_root}}/{relative_path}"
        assert expected_command_path in tool["command_template"]
        assert expected_command_path in contract["execution"]["command_template"]


def test_sciplot_tests_are_excluded_from_wheel():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    wheel_section = pyproject.split("[tool.hatch.build.targets.wheel]", maxsplit=1)[1]
    wheel_section = wheel_section.split(
        "[tool.hatch.build.targets.wheel.force-include]", maxsplit=1
    )[0]

    assert 'exclude = ["src/abi/sciplot/tests/"]' in wheel_section


def test_every_dockerfile_copy_source_exists():
    required_sources = (
        "docker/.condarc",
        "pyproject.toml",
        "README.md",
        "environments.yaml",
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


def test_every_dockerfile_copies_the_root_environment_manifest():
    dockerfiles = sorted((ROOT / "docker").glob("Dockerfile.*"))

    assert dockerfiles
    for dockerfile in dockerfiles:
        contents = dockerfile.read_text(encoding="utf-8")
        assert "COPY environments.yaml /app/" in contents, dockerfile.name
        assert "/app/environments.yaml" in contents.split("rm -rf", maxsplit=1)[1], dockerfile.name


def test_ci_and_docker_images_install_cjk_font_for_sciplot():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "apt-get install -y --no-install-recommends fonts-wqy-zenhei" in workflow

    dockerfiles = sorted((ROOT / "docker").glob("Dockerfile.*"))
    assert dockerfiles
    for dockerfile in dockerfiles:
        contents = dockerfile.read_text(encoding="utf-8")
        assert "apt-get install -y --no-install-recommends fonts-wqy-zenhei" in contents, (
            dockerfile.name
        )
