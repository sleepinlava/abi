import json

from abi.autoplasm.result_validation import validate_result_dir
from abi.autoplasm.standard_tables import append_standard_rows, ensure_standard_tables


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


def test_strict_validation_only_requires_active_module_tables(tmp_path):
    result_dir = tmp_path / "result"
    provenance = result_dir / "provenance"
    report = result_dir / "report"
    provenance.mkdir(parents=True)
    report.mkdir()
    categories = [
        "qc",
        "assembly",
        "plasmid_detection",
        "plasmid_consensus",
        "annotation",
        "abundance",
    ]
    (result_dir / "execution_plan.json").write_text(
        json.dumps(
            {
                "steps": [
                    *[{"category": category} for category in categories],
                    {"category": "typing", "skipped": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    (provenance / "run_summary.json").write_text(
        json.dumps({"status": "success"}), encoding="utf-8"
    )
    (provenance / "commands.tsv").write_text("step_id\tstatus\ns1\tsuccess\n", encoding="utf-8")
    (report / "report.md").write_text("# report\n", encoding="utf-8")
    (report / "report.html").write_text("<html></html>\n", encoding="utf-8")
    append_standard_rows(
        result_dir / "tables",
        {
            "qc_summary": [{"sample_id": "S1", "tool": "fastp", "metric": "q30", "value": "95"}],
            "assembly_summary": [
                {"sample_id": "S1", "tool": "spades", "metric": "n50", "value": "1000"}
            ],
            "plasmid_predictions": [{"sample_id": "S1", "contig_id": "p1"}],
            "plasmid_consensus": [{"sample_id": "S1", "contig_id": "p1"}],
            "annotations": [
                {"sample_id": "S1", "contig_id": "p1", "gene": "repA", "tool": "bakta"}
            ],
            "abundance": [
                {
                    "sample_id": "S1",
                    "feature_id": "p1",
                    "contig_id": "p1",
                    "coverage": "12",
                    "tool": "coverm",
                }
            ],
        },
    )

    result = validate_result_dir(result_dir, allow_empty_tables=False)

    assert result["valid"] is True
    assert result["tables"]["network_edges"]["rows"] == 0
