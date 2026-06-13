from pathlib import Path

from abi.autoplasm.config import PROJECT_ROOT
from abi.autoplasm.sample_sheet import parse_sample_sheet


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
