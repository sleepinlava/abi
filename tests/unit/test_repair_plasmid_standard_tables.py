from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from abi.plugins.metagenomic_plasmid._engine.standard_tables import (
    ensure_standard_tables,
    read_standard_table,
    write_standard_table,
)


def _load_repair_module():
    script = Path(__file__).parents[2] / "scripts" / "repair_plasmid_standard_tables.py"
    spec = importlib.util.spec_from_file_location("repair_plasmid_standard_tables", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_backfills_public_tables_structure_and_provenance(tmp_path):
    module = _load_repair_module()
    result = tmp_path / "result"
    tables = result / "tables"
    provenance = result / "provenance"
    detection = result / "04_plasmid_detection" / "S1"
    provenance.mkdir(parents=True)
    detection.mkdir(parents=True)
    ensure_standard_tables(tables)
    (result / "execution_plan.json").write_text(
        json.dumps(
            {
                "analysis_type": "metagenomic_plasmid",
                "samples": [{"sample_id": "S1"}],
                "steps": [
                    {"category": "plasmid_detection"},
                    {"category": "annotation"},
                    {"category": "abundance"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (provenance / "run_summary.json").write_text(
        json.dumps({"analysis_type": "metagenomic_plasmid", "status": "success"}),
        encoding="utf-8",
    )
    (detection / "plasmid_contigs.fasta").write_text(
        ">p1\n" + "A" * 25 + "CGTACGTA" + "A" * 25 + "\n",
        encoding="utf-8",
    )
    write_standard_table(
        tables,
        "annotations",
        [{"sample_id": "S1", "contig_id": "p1", "gene": "repA", "tool": "bakta"}],
    )
    write_standard_table(
        tables,
        "abundance",
        [{"sample_id": "S1", "feature_id": "p1", "coverage": "12", "tool": "coverm"}],
    )

    record = module.repair_result(result)

    assert len(read_standard_table(tables, "plasmid_annotation")) == 1
    assert len(read_standard_table(tables, "plasmid_abundance")) == 1
    assert read_standard_table(tables, "plasmid_structure")[0]["terminal_overlap_bp"] == "25"
    statuses = {
        row["module"]: row["status"] for row in read_standard_table(tables, "analysis_status")
    }
    assert statuses["annotation"] == "completed_with_rows"
    assert statuses["network"] == "not_enabled"
    assert record["written_rows"]["plasmid_structure"] == 1
    assert (provenance / "repairs.jsonl").is_file()
