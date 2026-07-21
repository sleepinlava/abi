#!/usr/bin/env python3
"""Create final SciPlot FigureSpecs from frozen SCAPP paper-method evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

TABLE_REQUIREMENTS = {
    "figure_metrics.tsv": ["metric", "percent", "numerator", "denominator", "definition"],
    "figure_directional_recovery.tsv": ["direction", "Matched", "Unmatched"],
    "figure_evidence_rates.tsv": ["evidence", "group", "count", "denominator", "percent"],
    "evidence_by_plasmid.tsv": [
        "plasmid_id",
        "log10_abundance_coverage",
        "log10_length_bp",
        "reference_matched",
        "prediction_status",
    ],
    "figure_mobility_composition.tsv": ["group", "Mobilizable", "Non-mobilizable"],
}


def _relative(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Figure artifact must be inside repository root: {path}") from exc


def _check_table(path: Path, required: list[str]) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, [])
        first_row = next(reader, None)
    missing = [column for column in required if column not in header]
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")
    if first_row is None:
        raise ValueError(f"Figure table has no data rows: {path}")


def _spec(
    *,
    figure_id: str,
    figure_type: str,
    table: str,
    required_columns: list[str],
    mapping: dict[str, str],
    title: str,
    x_label: str,
    y_label: str,
    legend_title: str | None,
    width_mm: int,
    height_mm: int,
    rendered_dir: str,
    input_data_role: str,
) -> dict[str, Any]:
    labels = {"title": title, "x_label": x_label, "y_label": y_label}
    if legend_title:
        labels["legend_title"] = legend_title
    return {
        "figure_id": figure_id,
        "figure_type": figure_type,
        "data": {"table": table, "format": "tsv", "required_columns": required_columns},
        "mapping": mapping,
        "style": {
            "theme": "abi_nature",
            "palette": "colorblind_safe_8",
            "width_mm": width_mm,
            "height_mm": height_mm,
            "dpi": 300,
        },
        "labels": labels,
        "export": {
            "output_dir": rendered_dir,
            "basename": figure_id,
            "formats": ["png", "pdf", "svg"],
        },
        "provenance": {
            "workflow_name": "metagenomic_plasmid",
            "input_data_role": input_data_role,
        },
    }


def create_specs(
    repository_root: Path,
    data_dir: Path,
    figure_dir: Path,
    rendered_dir: Path,
) -> list[Path]:
    machine_evidence_path = data_dir / "machine_readable_evidence.json"
    machine_evidence = json.loads(machine_evidence_path.read_text(encoding="utf-8"))
    if machine_evidence.get("schema_version") != "abi.scapp.paper_method_evidence.v1":
        raise ValueError("Unsupported or missing SCAPP machine evidence schema")
    if machine_evidence.get("status") != "complete":
        raise ValueError("SCAPP machine evidence is not complete")
    if machine_evidence.get("evaluation_scope") != "paper-method reconstruction; not paper-exact":
        raise ValueError("SCAPP evaluation scope is not explicit")

    for name, columns in TABLE_REQUIREMENTS.items():
        _check_table(data_dir / name, columns)

    figure_dir.mkdir(parents=True, exist_ok=True)
    table_paths = {name: _relative(data_dir / name, repository_root) for name in TABLE_REQUIREMENTS}
    rendered_path = _relative(rendered_dir, repository_root)
    common_role = (
        "SCAPP supplementary-method reconstruction for SRR11038083; official 14,739-record "
        "PLSDB archive; not paper-exact because the paper-specific deduplication list is absent"
    )
    specs = [
        _spec(
            figure_id="scapp_paper_method_metrics",
            figure_type="barplot",
            table=table_paths["figure_metrics.tsv"],
            required_columns=TABLE_REQUIREMENTS["figure_metrics.tsv"],
            mapping={"x": "metric", "y": "percent"},
            title="ABI plasmid prediction metrics against reconstructed SCAPP truth",
            x_label="Metric (paper-method reconstruction)",
            y_label="Percent (%)",
            legend_title=None,
            width_mm=130,
            height_mm=85,
            rendered_dir=rendered_path,
            input_data_role=f"Precision, recall and F1; {common_role}",
        ),
        _spec(
            figure_id="scapp_paper_method_directional_recovery",
            figure_type="stacked_barplot",
            table=table_paths["figure_directional_recovery.tsv"],
            required_columns=TABLE_REQUIREMENTS["figure_directional_recovery.tsv"],
            mapping={"x": "direction"},
            title="Directional recovery under SCAPP paper-method reconstruction",
            x_label="Evaluation direction",
            y_label="Sequences (%)",
            legend_title="Classification",
            width_mm=140,
            height_mm=88,
            rendered_dir=rendered_path,
            input_data_role=f"Truth recall and prediction precision composition; {common_role}",
        ),
        _spec(
            figure_id="scapp_paper_method_evidence_rates",
            figure_type="barplot",
            table=table_paths["figure_evidence_rates.tsv"],
            required_columns=TABLE_REQUIREMENTS["figure_evidence_rates.tsv"],
            mapping={"x": "evidence", "y": "percent", "hue": "group"},
            title="Auxiliary plasmid evidence by paper-method prediction status",
            x_label="Auxiliary plasmid evidence",
            y_label="Predictions positive (%)",
            legend_title="Prediction status",
            width_mm=155,
            height_mm=92,
            rendered_dir=rendered_path,
            input_data_role=(
                f"Auxiliary evidence stratified by TP/FP prediction status; {common_role}"
            ),
        ),
        _spec(
            figure_id="scapp_paper_method_abundance_length",
            figure_type="scatterplot",
            table=table_paths["evidence_by_plasmid.tsv"],
            required_columns=TABLE_REQUIREMENTS["evidence_by_plasmid.tsv"],
            mapping={
                "x": "log10_abundance_coverage",
                "y": "log10_length_bp",
                "hue": "prediction_status",
            },
            title="ABI plasmid predictions by abundance and length",
            x_label="log10 CoverM coverage",
            y_label="log10 length (bp)",
            legend_title="Paper-method prediction status",
            width_mm=140,
            height_mm=92,
            rendered_dir=rendered_path,
            input_data_role=f"Per-prediction abundance, length and TP/FP status; {common_role}",
        ),
        _spec(
            figure_id="scapp_paper_method_mobility_composition",
            figure_type="stacked_barplot",
            table=table_paths["figure_mobility_composition.tsv"],
            required_columns=TABLE_REQUIREMENTS["figure_mobility_composition.tsv"],
            mapping={"x": "group"},
            title="Predicted mobility by paper-method prediction status",
            x_label="Prediction status",
            y_label="Predictions (%)",
            legend_title="MOB-typer classification",
            width_mm=140,
            height_mm=90,
            rendered_dir=rendered_path,
            input_data_role=f"MOB-typer composition stratified by TP/FP status; {common_role}",
        ),
    ]

    destinations: list[Path] = []
    for spec in specs:
        destination = figure_dir / f"{spec['figure_id']}.figure.yaml"
        destination.write_text(
            yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        destinations.append(destination)
    return destinations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--figure-dir", type=Path, required=True)
    parser.add_argument("--rendered-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in create_specs(
        args.repository_root, args.data_dir, args.figure_dir, args.rendered_dir
    ):
        print(path)


if __name__ == "__main__":
    main()
