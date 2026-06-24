from pathlib import Path

import pytest

from abi.autoplasm.config import PROJECT_ROOT
from abi.autoplasm.sample_sheet import SampleSheetError, parse_sample_sheet


def test_parse_sample_sheet_detects_multi_sample_and_groups():
    context = parse_sample_sheet("examples/sample_sheet.tsv")
    assert len(context.samples) == 2
    assert context.multi_sample is True
    assert context.has_groups is True
    assert context.enable_differential_abundance is True
    assert Path(context.samples[1].assembly).exists()
    assert context.samples[1].assembly.endswith("examples/fixtures/tiny_contigs.fasta")
    assert context.samples[1].long_reads is None


def test_parse_sample_sheet_resolves_bundled_paths_outside_project_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    context = parse_sample_sheet(PROJECT_ROOT / "examples/sample_sheet.tsv")

    assert Path(context.samples[0].read1).exists()
    assert Path(context.samples[0].read2).exists()
    assert Path(context.samples[1].assembly).exists()


def test_parse_sample_sheet_accepts_ont_pod5_and_hifi_bam(tmp_path):
    pod5 = tmp_path / "reads.pod5"
    bam = tmp_path / "reads.bam"
    pod5.write_bytes(b"pod5")
    bam.write_bytes(b"bam")
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        f"sample_id\tplatform\tpod5\tbam\nONT1\tont\t{pod5}\t\nHIFI1\tpacbio_hifi\t\t{bam}\n",
        encoding="utf-8",
    )

    context = parse_sample_sheet(sheet)

    assert context.samples[0].pod5 == str(pod5)
    assert context.samples[1].bam == str(bam)


def test_parse_sample_sheet_rejects_duplicate_sample_ids(tmp_path):
    assembly = tmp_path / "contigs.fasta"
    assembly.write_text(">c1\nACGT\n", encoding="utf-8")
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        f"sample_id\tplatform\tassembly\nS1\tassembly\t{assembly}\nS1\tassembly\t{assembly}\n",
        encoding="utf-8",
    )

    with pytest.raises(SampleSheetError, match="Duplicate sample_id"):
        parse_sample_sheet(sheet)
