"""Tests for the amplicon diversity script math functions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Inject scripts/ into path for import
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")
sys.path.insert(0, _SCRIPTS_DIR)
from amplicon_diversity import (  # noqa: E402
    _bray_curtis,
    _chao1,
    _jaccard,
    _observed_features,
    _shannon,
    _simpson,
)


class TestShannon:
    def test_uniform_distribution(self):
        """Shannon entropy of 4 equal-abundance features = ln(4)."""
        import math
        assert _shannon([5, 5, 5, 5]) == pytest.approx(math.log(4), abs=1e-4)

    def test_single_species(self):
        """Shannon entropy of a single species = 0."""
        assert _shannon([100]) == 0.0

    def test_empty(self):
        """Shannon entropy of no reads = 0."""
        assert _shannon([]) == 0.0
        assert _shannon([0, 0, 0]) == 0.0

    def test_skewed_distribution(self):
        """Shannon entropy decreases as dominance increases."""
        h1 = _shannon([90, 10])
        h2 = _shannon([50, 50])
        assert h1 < h2  # more even = higher entropy


class TestSimpson:
    def test_single_species(self):
        """Simpson index of a single species = 0."""
        assert _simpson([100]) == 0.0

    def test_uniform_distribution(self):
        """Simpson index of 2 equal-abundance features = 0.5."""
        assert _simpson([5, 5]) == pytest.approx(0.5, abs=1e-4)

    def test_empty(self):
        """Simpson index of no reads = 0."""
        assert _simpson([]) == 0.0

    def test_high_diversity(self):
        """Simpson index approaches 1 with many equally-abundant species."""
        s = _simpson([1] * 100)
        assert s == pytest.approx(0.99, abs=0.01)


class TestChao1:
    def test_no_singletons(self):
        """Chao1 equals observed when no singletons."""
        counts = [2, 3, 5, 2, 4]
        assert _chao1(counts) == 5.0

    def test_with_singletons(self):
        """Chao1 corrects upward for singletons."""
        # 5 observed + 3 singletons, 1 doubleton
        # S_obs = 5, f1 = 3, f2 = 1
        # chao1 = 5 + 3^2/(2*1) = 5 + 4.5 = 9.5
        counts = [1, 1, 1, 2, 4]
        assert _chao1(counts) == pytest.approx(9.5, abs=0.01)

    def test_singletons_no_doubletons(self):
        """Chao1 with singletons but no doubletons uses bias-corrected formula."""
        counts = [1, 1, 1, 3, 4]
        # f1 = 3, f2 = 0 → S_obs + f1*(f1-1)/2 = 5 + 3*2/2 = 8
        assert _chao1(counts) == pytest.approx(8.0, abs=0.01)

    def test_empty(self):
        assert _chao1([]) == 0.0


class TestObservedFeatures:
    def test_basic(self):
        assert _observed_features([5, 0, 3, 0, 1]) == 3

    def test_all_zero(self):
        assert _observed_features([0, 0, 0]) == 0


class TestBrayCurtis:
    def test_identical(self):
        """Bray-Curtis of identical samples = 0."""
        assert _bray_curtis([10, 5, 3], [10, 5, 3]) == 0.0

    def test_completely_disjoint(self):
        """Bray-Curtis of disjoint samples = 1."""
        assert _bray_curtis([10, 0, 0], [0, 5, 0]) == 1.0

    def test_partial_overlap(self):
        """Bray-Curtis with partial overlap."""
        d = _bray_curtis([10, 10, 0], [0, 10, 10])
        assert 0.0 < d < 1.0

    def test_empty(self):
        assert _bray_curtis([], []) == 0.0


class TestJaccard:
    def test_identical(self):
        """Jaccard of identical presence/absence = 0."""
        assert _jaccard([1, 1, 0], [2, 3, 0]) == 0.0

    def test_completely_disjoint(self):
        """Jaccard of disjoint samples = 1."""
        assert _jaccard([1, 0, 0], [0, 1, 1]) == 1.0

    def test_partial_overlap(self):
        """Jaccard with 1 shared, 1 unique each."""
        # Intersection = 1 (shared), Union = 3 → 1 - 1/3 = 0.6667
        assert _jaccard([1, 1, 0], [0, 1, 1]) == pytest.approx(1.0 - 1 / 3, abs=0.01)

    def test_both_empty(self):
        assert _jaccard([], []) == 1.0


# ── Integration: run the actual script on synthetic data ─────────────────────


class TestDiversityScriptIntegration:
    """End-to-end test of the diversity script with synthetic 16S data."""

    def test_end_to_end_synthetic(self, tmp_path: Path):
        """Run the full script on 2 samples with known ASVs."""
        # Create per-sample ASV FASTA files
        denoise_dir = tmp_path / "04_denoise"
        merge_dir = tmp_path / "02_merge"
        output_dir = tmp_path / "06_diversity"
        for d in [denoise_dir, merge_dir, output_dir]:
            d.mkdir(parents=True)

        asv1 = "ACGTACGTACGTACGTACGT"  # shared ASV
        asv2 = "TGCATGCATGCATGCATGCA"  # unique to S1
        asv3 = "GGGGGGGGGGGGGGGGGGGG"  # unique to S2

        for sample_id, asv_seqs, merged_seqs_list in [
            ("S1", [asv1, asv2], [asv1] * 80 + [asv2] * 20),
            ("S2", [asv1, asv3], [asv1] * 50 + [asv3] * 50),
        ]:
            asv_dir = denoise_dir / sample_id
            asv_dir.mkdir()
            with (asv_dir / "asvs.fasta").open("w") as fh:
                for i, seq in enumerate(asv_seqs):
                    fh.write(f">ASV_{i + 1}\n{seq}\n")

            merge_sample_dir = merge_dir / sample_id
            merge_sample_dir.mkdir()
            with (merge_sample_dir / f"{sample_id}_merged.fasta").open("w") as fh:
                for i, seq in enumerate(merged_seqs_list):
                    fh.write(f">{sample_id}_{i}\n{seq}\n")

        # Run the script
        import subprocess
        result = subprocess.run(
            [
                sys.executable, "-m", "amplicon_diversity",
                "--denoise-dir", str(denoise_dir),
                "--merge-dir", str(merge_dir),
                "--output-dir", str(output_dir),
                "--min-count", "1",
            ],
            capture_output=True, text=True, timeout=30,
            cwd=_SCRIPTS_DIR,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        # Verify outputs
        assert (output_dir / "merged_asv_table.tsv").exists()
        assert (output_dir / "alpha_diversity.tsv").exists()
        assert (output_dir / "beta_diversity.tsv").exists()

        # Verify ASV table
        import csv
        with (output_dir / "merged_asv_table.tsv").open() as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            rows = list(reader)
        assert len(rows) == 3  # ASV1 + ASV2 + ASV3
        asv_ids = {r["asv_id"] for r in rows}
        assert len(asv_ids) == 3

        # Verify alpha diversity
        with (output_dir / "alpha_diversity.tsv").open() as fh:
            alpha = list(csv.DictReader(fh, delimiter="\t"))
        assert len(alpha) == 2
        s1 = next(r for r in alpha if r["sample_id"] == "S1")
        s2 = next(r for r in alpha if r["sample_id"] == "S2")
        # S1 has 2 ASVs (ASV1, ASV2)
        assert int(s1["observed_features"]) == 2
        # S2 has 2 ASVs (ASV1, ASV3)
        assert int(s2["observed_features"]) == 2
        # Shannon should be positive for both
        assert float(s1["shannon_entropy"]) > 0
        assert float(s2["shannon_entropy"]) > 0
        # S2 (50/50) should have higher Shannon than S1 (80/20)
        assert float(s2["shannon_entropy"]) > float(s1["shannon_entropy"])

        # Verify beta diversity
        with (output_dir / "beta_diversity.tsv").open() as fh:
            beta = list(csv.DictReader(fh, delimiter="\t"))
        assert len(beta) >= 2  # bray_curtis + jaccard
        metrics = {r["distance_metric"] for r in beta}
        assert "bray_curtis" in metrics
        assert "jaccard" in metrics
