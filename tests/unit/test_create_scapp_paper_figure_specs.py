from __future__ import annotations

import csv
import json
from pathlib import Path

from abi.sciplot.api import load_spec, render_figure, validate_spec
from scripts.create_scapp_paper_figure_specs import TABLE_REQUIREMENTS, create_specs


def _write_table(path: Path, columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerow({column: "1" for column in columns})


def test_create_specs_produces_five_valid_paper_method_figures(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "docs" / "zh" / "figures" / "data" / "paper_method"
    figure_dir = tmp_path / "docs" / "zh" / "figures"
    rendered_dir = figure_dir / "rendered"
    data_dir.mkdir(parents=True)
    (data_dir / "machine_readable_evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "abi.scapp.paper_method_evidence.v1",
                "status": "complete",
                "evaluation_scope": "paper-method reconstruction; not paper-exact",
            }
        ),
        encoding="utf-8",
    )
    for name, columns in TABLE_REQUIREMENTS.items():
        _write_table(data_dir / name, columns)

    paths = create_specs(tmp_path, data_dir, figure_dir, rendered_dir)

    assert len(paths) == 5
    specs = [load_spec(path) for path in paths]
    assert all(validate_spec(spec)["status"] == "ok" for spec in specs)
    evidence_spec = next(spec for spec in specs if spec.figure_id.endswith("evidence_rates"))
    assert evidence_spec.figure_type == "barplot"
    assert evidence_spec.mapping.hue == "group"
    assert all("not paper-exact" in (spec.provenance.input_data_role or "") for spec in specs)
    render_results = [render_figure(spec) for spec in specs]
    assert all(not result.errors for result in render_results)
    assert sum(len(result.output_files) for result in render_results) == 15
    assert all(
        result.provenance_path and result.provenance_path.is_file() for result in render_results
    )
