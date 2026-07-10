"""Regression tests for standalone visualization command adapters."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from abi.errors import InputPolicyError

SCRIPTS = Path("plugins/metagenomic_plasmid/scripts")


def _load_script(name: str) -> ModuleType:
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"abi_test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pycirclize_uses_fasta_lengths_and_creates_output_dir(tmp_path, monkeypatch):
    saved: dict[str, object] = {}

    class FakeCircos:
        def __init__(self, sectors):
            saved["sectors"] = sectors

        def savefig(self, path):
            saved["path"] = path

    monkeypatch.setitem(sys.modules, "pycirclize", SimpleNamespace(Circos=FakeCircos))
    contigs = tmp_path / "contigs.fasta"
    contigs.write_text(">p1\nACGT\n>p2\nAACCGG\n", encoding="utf-8")
    annotations = tmp_path / "annotations.tsv"
    typing = tmp_path / "typing.tsv"
    annotations.write_text("feature\n", encoding="utf-8")
    typing.write_text("type\n", encoding="utf-8")
    outdir = tmp_path / "nested" / "figures"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pycirclize_viz.py",
            "--annotations",
            str(annotations),
            "--typing",
            str(typing),
            "--contigs",
            str(contigs),
            "--sample",
            "S1",
            "--outdir",
            str(outdir),
        ],
    )

    _load_script("pycirclize_viz").main()

    assert outdir.is_dir()
    assert saved["sectors"] == {"p1": 4, "p2": 6}
    assert saved["path"] == str(outdir / "S1.circular_map.png")


def test_pyvis_creates_output_dir_and_writes_expected_graph(tmp_path, monkeypatch):
    saved: dict[str, object] = {"nodes": [], "edges": []}

    class FakeNetwork:
        def __init__(self, **kwargs):
            saved["options"] = kwargs

        def add_node(self, node, **kwargs):
            saved["nodes"].append((node, kwargs))

        def add_edge(self, source, target, **kwargs):
            saved["edges"].append((source, target, kwargs))

        def show_buttons(self):
            saved["buttons"] = True

        def save_graph(self, path):
            saved["path"] = path

    pyvis = ModuleType("pyvis")
    network = ModuleType("pyvis.network")
    network.Network = FakeNetwork
    monkeypatch.setitem(sys.modules, "pyvis", pyvis)
    monkeypatch.setitem(sys.modules, "pyvis.network", network)
    links = tmp_path / "links.tsv"
    pd.DataFrame([{"host": "H1", "plasmid": "P1", "weight": 2}]).to_csv(
        links, sep="\t", index=False
    )
    outdir = tmp_path / "nested" / "figures"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pyvis_viz.py",
            "--links",
            str(links),
            "--sample",
            "S1",
            "--outdir",
            str(outdir),
        ],
    )

    _load_script("pyvis_viz").main()

    assert outdir.is_dir()
    assert saved["edges"] == [("H1", "P1", {"value": 2.0})]
    assert saved["path"] == str(outdir / "S1.host_plasmid_network.html")


def test_dna_features_passes_sequence_text_and_creates_output_dir(tmp_path, monkeypatch):
    saved: dict[str, object] = {}

    class FakeGraphicRecord:
        def __init__(self, *, sequence, features):
            saved["sequence"] = sequence
            saved["features"] = features

        def plot(self, **kwargs):
            saved["plot"] = kwargs

    bio = ModuleType("Bio")
    bio.SeqIO = SimpleNamespace(read=lambda *_args: SimpleNamespace(seq="ACGT"))
    viewer = ModuleType("dna_features_viewer")
    viewer.BiopythonTranslator = object
    viewer.GraphicRecord = FakeGraphicRecord
    monkeypatch.setitem(sys.modules, "Bio", bio)
    monkeypatch.setitem(sys.modules, "dna_features_viewer", viewer)
    contigs = tmp_path / "contigs.fasta"
    contigs.write_text(">p1\nACGT\n", encoding="utf-8")
    outdir = tmp_path / "nested" / "figures"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dna_features_viz.py",
            "--contigs",
            str(contigs),
            "--sample",
            "S1",
            "--outdir",
            str(outdir),
        ],
    )

    _load_script("dna_features_viz").main()

    assert outdir.is_dir()
    assert saved["sequence"] == "ACGT"
    assert saved["plot"] == {
        "figure_width": 10,
        "output": str(outdir / "S1.features.png"),
    }


@pytest.mark.parametrize(
    ("script_name", "required_args"),
    [
        (
            "pycirclize_viz",
            ["--annotations", "a.tsv", "--typing", "t.tsv", "--contigs", "c.fa"],
        ),
        ("pyvis_viz", ["--links", "links.tsv"]),
        ("dna_features_viz", ["--contigs", "c.fa"]),
    ],
)
def test_visualization_scripts_reject_unsafe_sample_before_writing(
    tmp_path, monkeypatch, script_name, required_args
):
    outdir = tmp_path / "figures"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            f"{script_name}.py",
            *required_args,
            "--sample",
            "../escape",
            "--outdir",
            str(outdir),
        ],
    )

    with pytest.raises(InputPolicyError):
        _load_script(script_name).main()

    assert not outdir.exists()
