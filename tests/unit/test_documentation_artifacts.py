import re
from pathlib import Path


def test_release_check_script_is_documented() -> None:
    assert Path("scripts/release_check.sh").is_file()
    assert "scripts/release_check.sh" in Path("docs/en/release.md").read_text()
    assert "scripts/release_check.sh" in Path("docs/zh/release.md").read_text()


def test_release_check_uses_stable_coverage_gate() -> None:
    script = Path("scripts/release_check.sh").read_text()

    assert "python -m pytest tests/ src/abi/sciplot/tests/" in script
    assert "--strict-markers" in script
    assert '-m "not requires_tools"' in script
    assert "--capture=no" in script
    assert "--cov-fail-under=75" in script


def test_release_check_uses_posix_tempdir_for_permission_sensitive_tests() -> None:
    script = Path("scripts/release_check.sh").read_text()

    assert 'release_tmp_root="${ABI_RELEASE_TMP_ROOT:-/tmp}"' in script
    assert 'export TMPDIR="$ABI_RELEASE_TMPDIR"' in script
    assert 'export TMP="$ABI_RELEASE_TMPDIR"' in script
    assert 'export TEMP="$ABI_RELEASE_TMPDIR"' in script


def test_release_gate_does_not_execute_known_broken_dry_run_xfails() -> None:
    dry_run_tests = Path("tests/integration/test_dry_run.py").read_text()

    runnable_known_broken_marker = (
        '@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")'
    )
    assert runnable_known_broken_marker not in dry_run_tests


def test_changelog_has_current_release_section() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert version_match is not None

    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert f"## [{version_match.group(1)}]" in changelog


def test_opencode_workflow_reads_api_key_from_github_secret() -> None:
    workflow = Path(".github/workflows/opencode.yml").read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}" in workflow
    assert "DEEPSEEK_API_KEY: ${{sk-" not in workflow
