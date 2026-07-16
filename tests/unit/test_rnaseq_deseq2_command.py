from __future__ import annotations

from abi.tools import ToolRegistry


def test_deseq2_command_passes_configured_design_formula() -> None:
    registry = ToolRegistry.from_path("plugins/rnaseq_expression/tool_registry.yaml")
    command = registry.create("deseq2", mock_tools=True).build_command(
        {
            "deseq2_script": "plugins/rnaseq_expression/scripts/run_deseq2.R",
            "count_matrix": "results/count_matrix.tsv",
            "sample_metadata": "results/sample_metadata.tsv",
            "output_dir": "results/de",
            "comparison": "dex_vs_untreated",
            "design": "~ donor + condition",
            "alpha": 0.05,
        }
    )

    assert command[0] == "Rscript"
    assert command[command.index("--design") + 1] == "~ donor + condition"
