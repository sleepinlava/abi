from __future__ import annotations

import json
from pathlib import Path

import pytest

from abi._shared import (
    _clean,
    _common_overrides,
    _display_command,
    _offline_sample_context,
    _parse_fastp,
    _parse_sample_sheet_tabular,
    _parse_star,
    _plan_dict,
    _read_tsv,
    _resolve_path,
)


def test_tsv_command_plan_and_override_helpers(tmp_path):
    tsv = tmp_path / "rows.tsv"
    tsv.write_text("name\tvalue\na\t1\n", encoding="utf-8")

    class Plan:
        def to_dict(self):
            return {"project_name": "demo"}

    assert _read_tsv(tsv) == [{"name": "a", "value": "1"}]
    assert _read_tsv(tmp_path / "missing.tsv") == []
    assert _display_command(["tool", "a b", ">", Path("out.txt")]) == "tool 'a b' > out.txt"
    assert _plan_dict(Plan(), "wgs_bacteria")["analysis_type"] == "wgs_bacteria"
    overrides = _common_overrides(
        threads=4,
        sample_sheet=tmp_path / "samples.tsv",
        progress=False,
        cpu_override=2,
        container_runtime="docker",
    )
    assert overrides["threads"] == 4
    assert overrides["execution"]["progress"] is False
    assert overrides["execution"]["resources"]["cpu"] == 2
    assert overrides["execution"]["container"]["runtime"] == "docker"


def test_clean_and_offline_context_are_explicit():
    assert _clean("  value  ") == "value"
    assert _clean("  ") is None
    context = _offline_sample_context(group="GROUP_NOT_CONFIGURED")
    assert context.samples[0].sample_id == "SAMPLE_NOT_CONFIGURED"
    assert context.samples[0].group == "GROUP_NOT_CONFIGURED"


def test_resolve_path_rejects_relative_traversal_but_allows_absolute_inputs(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    nested = data / "reads.fastq"
    nested.write_text("@r\nA\n+\n!\n", encoding="utf-8")

    assert _resolve_path("reads.fastq", base_dirs=[data]) == nested
    assert _resolve_path(nested, base_dirs=[data]) == nested
    with pytest.raises(ValueError, match="traversal"):
        _resolve_path("../../etc/passwd", base_dirs=[data])


def test_sample_sheet_checks_only_file_fields(tmp_path):
    read1 = tmp_path / "R1.fastq"
    read2 = tmp_path / "R2.fastq"
    read1.write_text("reads", encoding="utf-8")
    read2.write_text("reads", encoding="utf-8")
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        f"sample_id\tread1\tread2\nS1\t{read1}\t{read2}\n",
        encoding="utf-8",
    )

    rows = _parse_sample_sheet_tabular(sheet)

    assert rows[0]["sample_id"] == "S1"


def test_shared_fastp_and_star_parsers_ignore_malformed_files(tmp_path):
    (tmp_path / "bad.json").write_text("{bad", encoding="utf-8")
    (tmp_path / "good.json").write_text(
        json.dumps(
            {
                "summary": {
                    "before_filtering": {"total_reads": 10},
                    "after_filtering": {"total_reads": 8},
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "S1Log.final.out").write_text(
        "Number of input reads | 10\nmalformed\n",
        encoding="utf-8",
    )

    fastp_rows = _parse_fastp(tmp_path, "S1")
    star_rows = _parse_star(tmp_path, "S1")

    assert {row["metric"] for row in fastp_rows} == {
        "before_filtering.total_reads",
        "after_filtering.total_reads",
    }
    assert star_rows[0]["metric"] == "Number of input reads"


def test_shared_parsers_reject_fuzzed_binary_inputs_without_crashing(tmp_path):
    (tmp_path / "binary.json").write_bytes(bytes(range(256)))
    (tmp_path / "binaryLog.final.out").write_bytes(bytes(reversed(range(256))))

    assert _parse_fastp(tmp_path, "S1") == []
    assert _parse_star(tmp_path, "S1") == []
