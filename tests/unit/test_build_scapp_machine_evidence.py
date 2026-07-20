from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "scripts" / "build_scapp_machine_evidence.py"
    spec = importlib.util.spec_from_file_location("build_scapp_machine_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_evidence_freezes_metrics_scope_and_artifact_hashes(tmp_path: Path) -> None:
    module = _module()
    (tmp_path / "truth_summary.json").write_text(
        json.dumps(
            {
                "thresholds": {"identity_strictly_greater_than_percent": 85},
                "counts": {"selected_truth_references": 4},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "score_summary.json").write_text(
        json.dumps(
            {
                "thresholds": {"identity_strictly_greater_than_percent": 80},
                "duplicate_policy": "one TP per signature",
                "counts": {
                    "true_positive_predictions_after_duplicate_penalty": 3,
                    "duplicate_false_positive_predictions": 1,
                    "no_match_false_positive_predictions": 2,
                    "false_negative_truth_references": 1,
                    "total_truth_references": 4,
                    "total_predictions": 6,
                },
                "metrics": {"precision": 0.5, "recall": 0.75, "f1": 0.6},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "run_provenance.tsv").write_text(
        "plsdb_input_records\t14739\n"
        "paper_reported_deduplicated_plsdb_records\t13469\n"
        "database_scope_note\tscope differs\n"
        "abi_git_commit\tabc123\n"
        "abi_git_dirty\ttrue\n"
        "truth_builder_sha256\tdeadbeef\n",
        encoding="utf-8",
    )
    for name in (
        "truth_reference_coverage.tsv",
        "truth_contig_reference_pairs.tsv",
        "prediction_reference_pairs.tsv",
        "prediction_status.tsv",
        "truth_status.tsv",
        "figure_metrics.tsv",
        "figure_directional_recovery.tsv",
        "evidence_match_table.tsv",
    ):
        (tmp_path / name).write_text("field\nvalue\n", encoding="utf-8")

    evidence = module.build_evidence(tmp_path)

    assert evidence["schema_version"] == "abi.scapp.paper_method_evidence.v1"
    assert evidence["evaluation_scope"] == "paper-method reconstruction; not paper-exact"
    assert evidence["confusion_counts"] == {
        "true_positive_predictions": 3,
        "false_positive_predictions": 3,
        "false_negative_truth_references": 1,
        "truth_references": 4,
        "predictions": 6,
    }
    assert evidence["metrics"] == {"precision": 0.5, "recall": 0.75, "f1": 0.6}
    assert evidence["database_scope"]["archive_records"] == 14739
    assert evidence["artifacts"]["score_summary"]["sha256"]
