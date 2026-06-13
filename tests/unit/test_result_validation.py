import json

from abi.autoplasm.result_validation import validate_result_dir
from abi.autoplasm.standard_tables import ensure_standard_tables


def test_validate_result_rejects_failed_run(tmp_path):
    result_dir = tmp_path / "result"
    provenance = result_dir / "provenance"
    report = result_dir / "report"
    provenance.mkdir(parents=True)
    report.mkdir()
    (result_dir / "execution_plan.json").write_text("{}", encoding="utf-8")
    (provenance / "run_summary.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    (provenance / "commands.tsv").write_text(
        "step_id\tstatus\ns1\tfailed\n",
        encoding="utf-8",
    )
    (report / "report.md").write_text("# report\n", encoding="utf-8")
    (report / "report.html").write_text("<html></html>\n", encoding="utf-8")
    ensure_standard_tables(result_dir / "tables")

    result = validate_result_dir(result_dir)

    assert result["valid"] is False
    assert "commands.tsv contains 1 failed step(s)" in result["errors"]


def test_validate_result_accepts_success_with_header_only_tables(tmp_path):
    result_dir = tmp_path / "result"
    provenance = result_dir / "provenance"
    report = result_dir / "report"
    provenance.mkdir(parents=True)
    report.mkdir()
    (result_dir / "execution_plan.json").write_text("{}", encoding="utf-8")
    (provenance / "run_summary.json").write_text(
        json.dumps({"status": "success"}),
        encoding="utf-8",
    )
    (provenance / "commands.tsv").write_text("step_id\tstatus\ns1\tsuccess\n", encoding="utf-8")
    (report / "report.md").write_text("# report\n", encoding="utf-8")
    (report / "report.html").write_text("<html></html>\n", encoding="utf-8")
    ensure_standard_tables(result_dir / "tables")

    result = validate_result_dir(result_dir)

    assert result["valid"] is True
