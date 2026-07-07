from pathlib import Path


def test_release_check_script_is_documented() -> None:
    assert Path("scripts/release_check.sh").is_file()
    assert "scripts/release_check.sh" in Path("docs/en/release.md").read_text()
    assert "scripts/release_check.sh" in Path("docs/zh/release.md").read_text()
