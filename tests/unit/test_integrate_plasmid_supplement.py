import csv
import json
from pathlib import Path

from scripts.integrate_plasmid_supplement import integrate_supplement


def _write_tsv(path: Path, header: list[str], row: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerow(row)


def test_integrate_plasmid_supplement_is_idempotent(tmp_path):
    result = tmp_path / "result"
    tables = result / "tables"
    tables.mkdir(parents=True)
    (result / "execution_plan.json").write_text(
        json.dumps(
            {
                "analysis_type": "metagenomic_plasmid",
                "samples": [{"sample_id": "S1"}],
                "steps": [
                    {"category": "annotation"},
                    {"category": "typing"},
                    {"category": "plasmid_detection"},
                ],
            }
        ),
        encoding="utf-8",
    )
    provenance = result / "provenance"
    provenance.mkdir()
    (provenance / "run_summary.json").write_text(
        json.dumps({"analysis_type": "metagenomic_plasmid", "status": "success"}),
        encoding="utf-8",
    )
    _write_tsv(
        tables / "annotations.tsv",
        [
            "sample_id",
            "contig_id",
            "start",
            "end",
            "strand",
            "gene",
            "product",
            "drug_class",
            "category",
            "tool",
            "evidence",
            "identity",
            "coverage",
            "source_file",
        ],
        ["S1", "old", "", "", "", "old", "old", "", "CDS", "bakta", "", "", "", "old.tsv"],
    )

    supplement = result / "supplementary" / "test"
    raw = supplement / "raw"
    _write_tsv(
        raw / "amrfinderplus" / "S1.tsv",
        ["Contig id", "Element symbol", "Element name", "Type", "Class"],
        ["p1", "blaTEM-116", "TEM-116", "AMR", "BETA-LACTAM"],
    )
    _write_tsv(
        raw / "abricate" / "S1.tsv",
        ["SEQUENCE", "GENE", "DATABASE", "RESISTANCE", "COVERAGE", "%COVERAGE"],
        ["p1", "TEM-116", "card", "beta-lactam", "1-861/861", "100.00"],
    )
    _write_tsv(
        raw / "mob_typer" / "S1.tsv",
        ["sample_id", "rep_type(s)", "predicted_mobility"],
        ["p1 flag=1", "IncF", "mobilizable"],
    )

    first = integrate_supplement(result, supplement, "S1")
    second = integrate_supplement(result, supplement, "S1")

    assert first["merged_rows"] == second["merged_rows"]
    with (tables / "amr_genes.tsv").open(encoding="utf-8") as handle:
        amr_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(amr_rows) == 2
    assert {row["drug_class"] for row in amr_rows} == {"BETA-LACTAM", "beta-lactam"}
    assert {row["coverage"] for row in amr_rows} == {"", "100.00"}
    with (tables / "plasmid_typing.tsv").open(encoding="utf-8") as handle:
        typing_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(typing_rows) == 1
    assert typing_rows[0]["contig_id"] == "p1"
    assert (
        not (tables / "plasmid_predictions.tsv")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()[1:]
    )
