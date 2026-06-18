from __future__ import annotations

import json
from types import SimpleNamespace

from abi.executor import GenericABIExecutor, _build_assertion_context, _resolve_actual_outputs


def test_ensure_step_output_dirs_precreates_output_dir(tmp_path):
    """After Route C fix: output_dir is now pre-created so tools like
    fastp/STAR that don't mkdir -p internally work correctly."""
    output_dir = tmp_path / "nested" / "megahit"
    step = SimpleNamespace(
        step_id="S1_assembly_megahit",
        outputs={
            "output_dir": str(output_dir),
            "contigs": str(output_dir / "final.contigs.fa"),
        },
    )

    GenericABIExecutor._ensure_step_output_dirs([step])

    assert output_dir.parent.is_dir()
    assert output_dir.is_dir()  # now pre-created


def test_ensure_step_output_dirs_creates_file_output_parent(tmp_path):
    report = tmp_path / "reports" / "S1.report.tsv"
    step = SimpleNamespace(
        step_id="S1_report",
        outputs={"report": str(report)},
    )

    GenericABIExecutor._ensure_step_output_dirs([step])

    assert report.parent.is_dir()
    assert not report.exists()


def test_resolve_actual_outputs_keeps_read_pairs_in_order(tmp_path):
    output_dir = tmp_path / "fastp"
    output_dir.mkdir()
    read2 = output_dir / "S1_R2.clean.fastq.gz"
    read1 = output_dir / "S1_R1.clean.fastq.gz"
    read2.write_text("@r2\nTGCA\n+\n!!!!\n")
    read1.write_text("@r1\nACGT\n+\n!!!!\n")

    resolved = _resolve_actual_outputs(
        {
            "output_dir": str(output_dir),
            "clean_read1": str(output_dir / "S1.fastp.clean_read1"),
            "clean_read2": str(output_dir / "S1.fastp.clean_read2"),
        },
        {
            "clean_read1": {"type": "file", "format": "fastq.gz"},
            "clean_read2": {"type": "file", "format": "fastq.gz"},
        },
        "S1",
    )

    assert resolved["clean_read1"] == str(read1)
    assert resolved["clean_read2"] == str(read2)


def test_build_assertion_context_flattens_single_json_output(tmp_path):
    report = tmp_path / "S1.fastp.json"
    report.write_text(json.dumps({"summary": {"after_filtering": {"total_reads": 10}}}))

    context = _build_assertion_context(
        SimpleNamespace(outputs={}),
        {"json_report": str(report)},
    )

    assert context["output_files"] == {"json_report": True}
    assert context["output_json"]["summary"]["after_filtering"]["total_reads"] == 10


def test_build_assertion_context_keeps_multiple_json_outputs_keyed(tmp_path):
    report = tmp_path / "report.json"
    metrics = tmp_path / "metrics.json"
    report.write_text(json.dumps({"kind": "report"}))
    metrics.write_text(json.dumps({"kind": "metrics"}))

    context = _build_assertion_context(
        SimpleNamespace(outputs={}),
        {"json_report": str(report), "metrics_json": str(metrics)},
    )

    assert context["output_json"]["json_report"] == {"kind": "report"}
    assert context["output_json"]["metrics_json"] == {"kind": "metrics"}
