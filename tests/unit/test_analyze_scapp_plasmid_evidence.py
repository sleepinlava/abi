from scripts.analyze_scapp_plasmid_evidence import _summarize, _write_figure_tables


def test_summarize_uses_plasmids_as_denominator():
    rows = [
        {
            "reference_coverage_fraction": 1.0,
            "length_bp": 1000,
            "abundance_coverage": 10,
            "terminal_overlap_bp": 20,
            "annotation_count": 4,
            "amr_hit_count": 1,
            "is_circular": True,
            "reference_hit_present": True,
            "plasmidfinder_positive": True,
            "mob_replicon_positive": True,
            "mob_relaxase_positive": False,
            "mob_orit_positive": False,
            "predicted_mobility": "non-mobilizable",
        },
        {
            "reference_coverage_fraction": 0.5,
            "length_bp": 3000,
            "abundance_coverage": 30,
            "terminal_overlap_bp": 0,
            "annotation_count": 8,
            "amr_hit_count": 0,
            "is_circular": False,
            "reference_hit_present": False,
            "plasmidfinder_positive": False,
            "mob_replicon_positive": False,
            "mob_relaxase_positive": True,
            "mob_orit_positive": True,
            "predicted_mobility": "mobilizable",
        },
    ]

    summary = _summarize(rows)

    assert summary["count"] == 2
    assert summary["median_length_bp"] == 2000
    assert summary["is_circular_rate"] == 0.5
    assert summary["mob_relaxase_positive_rate"] == 0.5
    assert summary["mobility_counts"] == {"non-mobilizable": 1, "mobilizable": 1}


def test_figure_tables_keep_counts_and_denominators(tmp_path):
    grouped = {
        "reference_matched": {
            "count": 25,
            "is_circular_count": 13,
            "plasmidfinder_positive_count": 7,
            "mob_replicon_positive_count": 11,
            "mob_relaxase_positive_count": 6,
            "mob_orit_positive_count": 4,
            "mobility_counts": {"mobilizable": 9, "non-mobilizable": 16},
        },
        "reference_unmatched": {
            "count": 132,
            "is_circular_count": 41,
            "plasmidfinder_positive_count": 2,
            "mob_replicon_positive_count": 3,
            "mob_relaxase_positive_count": 8,
            "mob_orit_positive_count": 4,
            "mobility_counts": {"mobilizable": 11, "non-mobilizable": 121},
        },
    }

    _write_figure_tables(tmp_path, grouped)

    rates = (tmp_path / "figure_evidence_rates.tsv").read_text(encoding="utf-8")
    mobility = (tmp_path / "figure_mobility_composition.tsv").read_text(encoding="utf-8")
    assert "PlasmidFinder\tReference matched (n=25)\t7\t25\t28.0" in rates
    assert "Reference unmatched (n=132)\t11\t121" in mobility


def test_figure_tables_can_use_paper_method_tp_fp_labels(tmp_path):
    grouped = {
        "reference_matched": {
            "count": 2,
            "is_circular_count": 1,
            "plasmidfinder_positive_count": 1,
            "mob_replicon_positive_count": 1,
            "mob_relaxase_positive_count": 0,
            "mob_orit_positive_count": 0,
            "mobility_counts": {"mobilizable": 1, "non-mobilizable": 1},
        },
        "reference_unmatched": {
            "count": 3,
            "is_circular_count": 0,
            "plasmidfinder_positive_count": 0,
            "mob_replicon_positive_count": 0,
            "mob_relaxase_positive_count": 1,
            "mob_orit_positive_count": 1,
            "mobility_counts": {"mobilizable": 1, "non-mobilizable": 2},
        },
    }

    _write_figure_tables(
        tmp_path,
        grouped,
        label_stems={
            "reference_matched": "True-positive prediction",
            "reference_unmatched": "False-positive prediction",
        },
    )

    rates = (tmp_path / "figure_evidence_rates.tsv").read_text(encoding="utf-8")
    assert "True-positive prediction (n=2)" in rates
    assert "False-positive prediction (n=3)" in rates
