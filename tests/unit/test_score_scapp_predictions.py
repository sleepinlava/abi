from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "scripts" / "score_scapp_predictions.py"
    spec = importlib.util.spec_from_file_location("score_scapp_predictions", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scoring_penalizes_duplicate_reference_signature_and_recalls_multiple_truths(
    tmp_path: Path,
) -> None:
    module = _module()
    blast = tmp_path / "hits.tsv"
    rows = []
    for prediction in ("pred1", "pred2"):
        for reference in ("ref1", "ref2"):
            rows.append(f"{prediction}\t100\t{reference}\t100\t95\t100\t1\t100\t1\t100\t200")
    blast.write_text("\n".join(rows) + "\n", encoding="utf-8")

    _pairs, predictions, references, summary = module.score_predictions(
        blast,
        {"pred1": 100, "pred2": 100, "pred3": 100},
        {"ref1": 100, "ref2": 100},
        min_identity=80,
        min_coverage=0.90,
    )

    assert summary["counts"] == {
        "total_predictions": 3,
        "raw_predictions_with_match": 2,
        "true_positive_predictions_after_duplicate_penalty": 1,
        "duplicate_false_positive_predictions": 1,
        "no_match_false_positive_predictions": 1,
        "total_truth_references": 2,
        "recalled_truth_references": 2,
        "false_negative_truth_references": 0,
    }
    assert summary["metrics"]["precision"] == 1 / 3
    assert summary["metrics"]["recall"] == 1
    statuses = {row["status"] for row in predictions}
    assert statuses == {
        "true_positive",
        "false_positive_duplicate_match_signature",
        "false_positive_no_match",
    }
    assert all(row["recalled"] == "true" for row in references)
    metric_rows, directional_rows, evidence_rows = module.derived_tables(predictions, summary)
    assert metric_rows[0]["numerator"] == 1
    assert metric_rows[1]["numerator"] == 2
    assert directional_rows == [
        {"direction": "Truth references (n=2)", "Matched": 2, "Unmatched": 0},
        {"direction": "ABI predictions (n=3)", "Matched": 1, "Unmatched": 2},
    ]
    assert sum(row["selected"] == "true" for row in evidence_rows) == 1
    assert {row["prediction_status"] for row in evidence_rows} == {
        "true_positive",
        "false_positive_duplicate_match_signature",
        "false_positive_no_match",
    }


def test_scoring_uses_strict_identity_and_bidirectional_coverage_thresholds(
    tmp_path: Path,
) -> None:
    module = _module()
    blast = tmp_path / "hits.tsv"
    blast.write_text(
        # Identity exactly 80 fails.
        "pred1\t100\tref1\t100\t80\t100\t1\t100\t1\t100\t200\n"
        # Prediction coverage exactly 90% fails.
        "pred2\t100\tref1\t100\t95\t90\t1\t90\t1\t100\t200\n"
        # Reference coverage exactly 90% fails.
        "pred3\t100\tref1\t100\t95\t90\t1\t100\t1\t90\t200\n",
        encoding="utf-8",
    )

    _pairs, predictions, references, summary = module.score_predictions(
        blast,
        {"pred1": 100, "pred2": 100, "pred3": 100},
        {"ref1": 100},
        min_identity=80,
        min_coverage=0.90,
    )

    assert summary["counts"]["true_positive_predictions_after_duplicate_penalty"] == 0
    assert all(row["status"] == "false_positive_no_match" for row in predictions)
    assert references[0]["recalled"] == "false"
