"""Deterministic, realistic datasets used by SciPlot end-to-end tests."""

from __future__ import annotations

from typing import TypedDict

from abi.sciplot.schema.figure_spec import MappingSpec

TableData = tuple[list[str], list[tuple[object, ...]]]


class RealWorldBatch(TypedDict):
    """One coherent analysis batch and its source tables."""

    title: str
    requires_cjk: bool
    tables: dict[str, TableData]


PLOT_TABLES: dict[str, tuple[str, MappingSpec]] = {
    "barplot": ("summary", MappingSpec(x="category", y="value")),
    "boxplot_with_points": ("alpha", MappingSpec(x="group", y="shannon_entropy")),
    "violin_with_box": ("alpha", MappingSpec(x="group", y="shannon_entropy")),
    "scatterplot": (
        "ordination",
        MappingSpec(x="PC1", y="PC2", hue="group", label="sample_id"),
    ),
    "ordination_plot": ("ordination", MappingSpec(hue="group", label="sample_id")),
    "stacked_barplot": ("composition", MappingSpec(x="sample_id")),
    "heatmap": ("expression", MappingSpec()),
    "volcano_plot": (
        "differential",
        MappingSpec(x="log2FoldChange", y="padj", label="feature_id"),
    ),
    "lineplot": (
        "timeseries",
        MappingSpec(x="day", y="relative_abundance", hue="group"),
    ),
    "phylum_stacked_bar": ("taxonomy", MappingSpec(x="sample_id", y="abundance")),
    "genus_heatmap": ("taxonomy", MappingSpec()),
    "pcoa_plot": ("distances", MappingSpec()),
    "differential_volcano": (
        "differential",
        MappingSpec(x="log2_fold_change", y="adjusted_pvalue", label="feature_id"),
    ),
    "alpha_stats_boxplot": (
        "alpha",
        MappingSpec(x="sample_id", y="shannon_entropy", hue="group"),
    ),
    "phylogenetic_heatmap": (
        "taxonomy",
        MappingSpec(x="sample_id", y="abundance", label="asv_id"),
    ),
}


REAL_WORLD_BATCHES: dict[str, RealWorldBatch] = {
    "antibiotic_cohort": {
        "title": "Antibiotic intervention microbiome cohort",
        "requires_cjk": False,
        "tables": {
            "summary": (
                ["category", "value"],
                [
                    ("Baseline", 42.6),
                    ("Day 7", 31.8),
                    ("Day 28", 38.9),
                    ("Healthy reference", 45.2),
                ],
            ),
            "alpha": (
                ["sample_id", "group", "shannon_entropy", "observed_features"],
                [
                    ("CTR_01", "Control", 4.21, 318),
                    ("CTR_02", "Control", 4.05, 301),
                    ("ABX_01", "Antibiotic", 2.14, 142),
                    ("ABX_02", "Antibiotic", 2.47, 159),
                    ("REC_01", "Recovery", 3.38, 241),
                    ("REC_02", "Recovery", 3.61, 267),
                ],
            ),
            "ordination": (
                ["sample_id", "PC1", "PC2", "group"],
                [
                    ("CTR_01", -0.31, 0.12, "Control"),
                    ("CTR_02", -0.27, 0.08, "Control"),
                    ("ABX_01", 0.42, -0.18, "Antibiotic"),
                    ("ABX_02", 0.37, -0.24, "Antibiotic"),
                    ("REC_01", 0.02, 0.19, "Recovery"),
                    ("REC_02", 0.08, 0.14, "Recovery"),
                ],
            ),
            "composition": (
                ["sample_id", "Firmicutes", "Bacteroidota", "Proteobacteria", "Other"],
                [
                    ("CTR_01", 45.2, 38.1, 7.4, 9.3),
                    ("CTR_02", 42.8, 40.5, 6.2, 10.5),
                    ("ABX_01", 18.3, 12.4, 59.7, 9.6),
                    ("ABX_02", 21.1, 14.8, 54.2, 9.9),
                    ("REC_01", 35.6, 31.4, 20.1, 12.9),
                    ("REC_02", 38.9, 33.2, 15.8, 12.1),
                ],
            ),
            "expression": (
                ["feature_id", "CTR_01", "CTR_02", "ABX_01", "ABX_02", "REC_01", "REC_02"],
                [
                    ("butA", 124.0, 118.0, 22.0, 19.0, 73.0, 81.0),
                    ("baiE", 48.0, 52.0, 3.0, 5.0, 21.0, 27.0),
                    ("tetW", 7.0, 9.0, 86.0, 93.0, 34.0, 29.0),
                    ("acrB", 18.0, 16.0, 71.0, 66.0, 37.0, 33.0),
                    ("mcrA", 61.0, 58.0, 8.0, 6.0, 32.0, 39.0),
                ],
            ),
            "differential": (
                [
                    "feature_id",
                    "log2FoldChange",
                    "padj",
                    "log2_fold_change",
                    "adjusted_pvalue",
                ],
                [
                    ("Escherichia", 3.84, 0.000002, 3.84, 0.000002),
                    ("Enterococcus", 2.31, 0.0008, 2.31, 0.0008),
                    ("Faecalibacterium", -2.76, 0.00004, -2.76, 0.00004),
                    ("Bifidobacterium", -1.43, 0.018, -1.43, 0.018),
                    ("Blautia", -0.28, 0.74, -0.28, 0.74),
                    ("Akkermansia", 0.63, 0.21, 0.63, 0.21),
                ],
            ),
            "timeseries": (
                ["day", "relative_abundance", "group"],
                [
                    (0, 7.1, "Control"),
                    (7, 6.8, "Control"),
                    (28, 7.3, "Control"),
                    (0, 7.4, "Antibiotic"),
                    (7, 58.6, "Antibiotic"),
                    (28, 18.2, "Antibiotic"),
                ],
            ),
            "taxonomy": (
                ["sample_id", "phylum", "genus", "asv_id", "abundance"],
                [
                    ("CTR_01", "Firmicutes", "Faecalibacterium", "ASV_001", 28.4),
                    ("CTR_01", "Bacteroidota", "Bacteroides", "ASV_002", 31.7),
                    ("CTR_02", "Firmicutes", "Faecalibacterium", "ASV_001", 25.9),
                    ("CTR_02", "Bacteroidota", "Bacteroides", "ASV_002", 34.1),
                    ("ABX_01", "Proteobacteria", "Escherichia", "ASV_003", 59.7),
                    ("ABX_01", "Firmicutes", "Enterococcus", "ASV_004", 13.2),
                    ("ABX_02", "Proteobacteria", "Escherichia", "ASV_003", 54.2),
                    ("ABX_02", "Firmicutes", "Enterococcus", "ASV_004", 15.6),
                    ("REC_01", "Firmicutes", "Faecalibacterium", "ASV_001", 19.8),
                    ("REC_01", "Bacteroidota", "Bacteroides", "ASV_002", 27.4),
                    ("REC_02", "Firmicutes", "Faecalibacterium", "ASV_001", 22.1),
                    ("REC_02", "Bacteroidota", "Bacteroides", "ASV_002", 29.7),
                ],
            ),
            "distances": (
                ["sample_a", "sample_b", "distance"],
                [
                    ("CTR_01", "CTR_02", 0.12),
                    ("CTR_01", "ABX_01", 0.68),
                    ("CTR_01", "REC_01", 0.34),
                    ("CTR_02", "ABX_01", 0.64),
                    ("CTR_02", "REC_01", 0.31),
                    ("ABX_01", "REC_01", 0.49),
                ],
            ),
        },
    },
    "multilingual_lake_cohort": {
        "title": "湖泊微生物群落监测：丰水期与枯水期",
        "requires_cjk": True,
        "tables": {
            "summary": (
                ["category", "value"],
                [("上游", 36.4), ("湖心", 51.7), ("下游", 43.2), ("沉积物", 68.9)],
            ),
            "alpha": (
                ["sample_id", "group", "shannon_entropy", "observed_features"],
                [
                    ("湖心-丰水-01", "丰水期", 5.12, 486),
                    ("湖心-丰水-02", "丰水期", 4.88, 451),
                    ("湖心-枯水-01", "枯水期", 3.74, 332),
                    ("湖心-枯水-02", "枯水期", 3.91, 347),
                    ("沉积物-01", "沉积物", 6.03, 612),
                    ("沉积物-02", "沉积物", 5.87, 589),
                ],
            ),
            "ordination": (
                ["sample_id", "PC1", "PC2", "group"],
                [
                    ("湖心-丰水-01", -0.44, 0.19, "丰水期"),
                    ("湖心-丰水-02", -0.39, 0.14, "丰水期"),
                    ("湖心-枯水-01", 0.21, -0.31, "枯水期"),
                    ("湖心-枯水-02", 0.28, -0.27, "枯水期"),
                    ("沉积物-01", 0.53, 0.36, "沉积物"),
                    ("沉积物-02", 0.48, 0.31, "沉积物"),
                ],
            ),
            "composition": (
                ["sample_id", "Proteobacteria", "Cyanobacteria", "Actinobacteriota", "Other"],
                [
                    ("湖心-丰水-01", 31.5, 42.8, 18.2, 7.5),
                    ("湖心-丰水-02", 29.7, 45.1, 17.6, 7.6),
                    ("湖心-枯水-01", 46.9, 12.4, 30.1, 10.6),
                    ("湖心-枯水-02", 44.3, 14.2, 29.8, 11.7),
                    ("沉积物-01", 52.1, 0.0, 21.7, 26.2),
                    ("沉积物-02", 49.8, 0.2, 23.4, 26.6),
                ],
            ),
            "expression": (
                ["feature_id", "丰水01", "丰水02", "枯水01", "枯水02", "沉积物01", "沉积物02"],
                [
                    ("amoA", 18.0, 21.0, 94.0, 88.0, 141.0, 133.0),
                    ("nirS", 42.0, 39.0, 71.0, 76.0, 218.0, 203.0),
                    ("mcyE", 126.0, 139.0, 7.0, 4.0, 0.0, 0.0),
                    ("pmoA", 5.0, 8.0, 17.0, 14.0, 96.0, 103.0),
                    ("dsrB", 0.0, 1.0, 3.0, 2.0, 184.0, 176.0),
                ],
            ),
            "differential": (
                [
                    "feature_id",
                    "log2FoldChange",
                    "padj",
                    "log2_fold_change",
                    "adjusted_pvalue",
                ],
                [
                    ("Microcystis", 5.62, 0.00000003, 5.62, 0.00000003),
                    ("Synechococcus", 2.48, 0.00012, 2.48, 0.00012),
                    ("Nitrospira", -3.71, 0.000004, -3.71, 0.000004),
                    ("Geobacter", -2.19, 0.0031, -2.19, 0.0031),
                    ("Limnohabitans", 0.06, 0.99, 0.06, 0.99),
                    ("Methylomonas", -0.83, 0.18, -0.83, 0.18),
                ],
            ),
            "timeseries": (
                ["day", "relative_abundance", "group"],
                [
                    (1, 8.2, "上游"),
                    (15, 17.4, "上游"),
                    (30, 11.1, "上游"),
                    (1, 21.7, "湖心"),
                    (15, 46.3, "湖心"),
                    (30, 28.5, "湖心"),
                ],
            ),
            "taxonomy": (
                ["sample_id", "phylum", "genus", "asv_id", "abundance"],
                [
                    ("湖心-丰水-01", "Cyanobacteria", "Microcystis", "ASV_蓝藻01", 42.8),
                    ("湖心-丰水-01", "Proteobacteria", "Limnohabitans", "ASV_变形01", 19.7),
                    ("湖心-丰水-02", "Cyanobacteria", "Microcystis", "ASV_蓝藻01", 45.1),
                    ("湖心-丰水-02", "Proteobacteria", "Limnohabitans", "ASV_变形01", 18.9),
                    ("湖心-枯水-01", "Actinobacteriota", "Aquiluna", "ASV_放线01", 30.1),
                    ("湖心-枯水-01", "Proteobacteria", "Nitrospira", "ASV_硝化01", 24.6),
                    ("湖心-枯水-02", "Actinobacteriota", "Aquiluna", "ASV_放线01", 29.8),
                    ("湖心-枯水-02", "Proteobacteria", "Nitrospira", "ASV_硝化01", 22.9),
                    ("沉积物-01", "Proteobacteria", "Geobacter", "ASV_沉积01", 31.4),
                    ("沉积物-01", "Desulfobacterota", "Desulfobulbus", "ASV_沉积02", 20.7),
                    ("沉积物-02", "Proteobacteria", "Geobacter", "ASV_沉积01", 29.8),
                    ("沉积物-02", "Desulfobacterota", "Desulfobulbus", "ASV_沉积02", 22.3),
                ],
            ),
            "distances": (
                ["sample_a", "sample_b", "distance"],
                [
                    ("丰水01", "丰水02", 0.09),
                    ("丰水01", "枯水01", 0.57),
                    ("丰水01", "沉积物01", 0.81),
                    ("丰水02", "枯水01", 0.54),
                    ("丰水02", "沉积物01", 0.79),
                    ("枯水01", "沉积物01", 0.66),
                ],
            ),
        },
    },
}
