from __future__ import annotations

from abi.tools import ToolRegistry


def test_rnaseq_featurecounts_command_retries_without_paired_flag() -> None:
    registry = ToolRegistry.from_path("plugins/rnaseq_expression/tool_registry.yaml")
    command = registry.create("featurecounts", mock_tools=True).build_command(
        {
            "threads": 8,
            "annotation_gtf": "resources/star_index/genes.gtf",
            "counts": "results/rnaseq/03_expression/S1/S1.featureCounts.txt",
            "bam": "results/rnaseq/02_alignment/S1/S1.bam",
        }
    )

    command_text = " ".join(command)
    assert command[:2] == ["sh", "-c"]
    assert "No paired-end reads were detected" in command_text
    assert 'featureCounts -T "$1" -p' in command_text
    assert 'featureCounts -T "$1" -a' in command_text


def test_metatranscriptomics_featurecounts_command_retries_without_paired_flag() -> None:
    registry = ToolRegistry.from_path("plugins/metatranscriptomics/tool_registry.yaml")
    command = registry.create("featurecounts", mock_tools=True).build_command(
        {
            "threads": 8,
            "annotation_gtf": "resources/star_index/genes.gtf",
            "counts": "results/meta/03_expression/S1/S1.featureCounts.txt",
            "bam": "results/meta/02_alignment/S1/S1.bam",
        }
    )

    command_text = " ".join(command)
    assert command[:2] == ["sh", "-c"]
    assert "No paired-end reads were detected" in command_text
    assert 'featureCounts -T "$1" -p' in command_text
    assert 'featureCounts -T "$1" -a' in command_text
