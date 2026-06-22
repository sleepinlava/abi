from abi.autoplasm.schemas import ExecutionPlan, SampleContext, SampleInput
from abi.autoplasm.standard_tables import append_standard_rows
from abi.autoplasm.statistics import (
    compute_diversity_and_differential,
    compute_host_plasmid_coabundance,
    compute_network_fallback,
)


def test_multi_sample_statistics_from_abundance_table(tmp_path):
    tables = tmp_path / "tables"
    append_standard_rows(
        tables,
        {
            "abundance": [
                {"sample_id": "S1", "feature_id": "contig_1", "tpm": "10"},
                {"sample_id": "S1", "feature_id": "contig_2", "tpm": "0"},
                {"sample_id": "S2", "feature_id": "contig_1", "tpm": "5"},
                {"sample_id": "S2", "feature_id": "contig_2", "tpm": "5"},
                {"sample_id": "S3", "feature_id": "contig_1", "tpm": "0"},
                {"sample_id": "S3", "feature_id": "contig_2", "tpm": "10"},
            ]
        },
    )
    plan = _plan()

    rows = compute_diversity_and_differential(plan, tables)

    assert any(row["metric"] == "shannon" for row in rows["sample_diversity"])
    assert any(row["metric"] == "bray_curtis" for row in rows["sample_diversity"])
    assert rows["differential_abundance"]
    assert rows["differential_abundance"][0]["method"] == "internal_effect_size"


def test_network_fallback_from_abundance_table(tmp_path):
    tables = tmp_path / "tables"
    append_standard_rows(
        tables,
        {
            "abundance": [
                {"sample_id": "S1", "feature_id": "contig_1", "tpm": "10"},
                {"sample_id": "S1", "feature_id": "contig_2", "tpm": "0"},
                {"sample_id": "S2", "feature_id": "contig_1", "tpm": "5"},
                {"sample_id": "S2", "feature_id": "contig_2", "tpm": "5"},
                {"sample_id": "S3", "feature_id": "contig_1", "tpm": "0"},
                {"sample_id": "S3", "feature_id": "contig_2", "tpm": "10"},
            ]
        },
    )

    rows = compute_network_fallback(_plan(), tables)

    assert rows["network_edges"][0]["method"] == "spearman_fallback"
    assert rows["network_nodes"][0]["degree"] >= 0


def test_host_plasmid_coabundance_is_marked_as_prediction(tmp_path):
    tables = tmp_path / "tables"
    append_standard_rows(
        tables,
        {
            "abundance": [
                {"sample_id": "S1", "feature_id": "p1", "tpm": "1"},
                {"sample_id": "S2", "feature_id": "p1", "tpm": "2"},
                {"sample_id": "S3", "feature_id": "p1", "tpm": "3"},
            ],
            "host_predictions": [
                {
                    "sample_id": "S1",
                    "contig_id": "",
                    "host_taxon": "Escherichia coli",
                    "confidence": "10",
                },
                {
                    "sample_id": "S2",
                    "contig_id": "",
                    "host_taxon": "Escherichia coli",
                    "confidence": "20",
                },
                {
                    "sample_id": "S3",
                    "contig_id": "",
                    "host_taxon": "Escherichia coli",
                    "confidence": "30",
                },
            ],
        },
    )

    rows = compute_host_plasmid_coabundance(_plan(), tables)

    assert rows[0]["plasmid_id"] == "p1"
    assert rows[0]["score"] == "1"
    assert rows[0]["is_prediction"] == "true"


def _plan() -> ExecutionPlan:
    samples = [
        SampleInput(sample_id="S1", group="case", platform="illumina", read1="R1", read2="R2"),
        SampleInput(sample_id="S2", group="case", platform="illumina", read1="R1", read2="R2"),
        SampleInput(
            sample_id="S3",
            group="control",
            platform="illumina",
            read1="R1",
            read2="R2",
        ),
    ]
    context = SampleContext(
        samples=samples,
        multi_sample=True,
        has_groups=True,
        enable_sample_analysis=True,
        enable_differential_abundance=True,
    )
    return ExecutionPlan(
        project_name="stats_test",
        mode="auto",
        threads=1,
        outdir="results/stats_test",
        log_dir="results/stats_test/log",
        samples=samples,
        steps=[],
        sample_context=context,
        selected_tools=[],
    )
