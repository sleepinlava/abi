# Plugin Report & Figure Specification System

> **Status**: Implemented (2026-06-18)
> **Canonical reference**: `docs/next_development_plan.md` §4

## Overview

The ABI report & figure system provides a **declarative, plugin-agnostic** way to generate publication-ready reports and figures from standard tables. Plugins declare *what* to output; the ABI core handles *how* to render.

## Architecture

```text
Plugin declaration (YAML)          ABI Core (Python)
─────────────────────────         ──────────────────
figure_specs.yaml          →      abi.figures.FigureEngine
citation_registry.yaml     →      abi.report.citations.CitationRegistry
limitations.yaml           →      abi.report.limitations.load_limitations
standard_tables.yaml       →      abi.tables.StandardTableManager
abi-plugin.yaml            →      abi.workflow.manifest.ResourceManifest
```

## Module Reference

### `abi.figures` — Figure Engine

```python
from abi.figures import FigureEngine, FigureSpec

engine = FigureEngine(table_schemas, tables_dir, figures_dir)
engine.load_specs("plugins/rnaseq/figure_specs.yaml")
rendered = engine.render_all()
# → {"qc_read_counts": Path("figures/qc_read_counts.png"), ...}
```

**Supported figure types**: `bar`, `scatter`, `volcano`, `heatmap`, `boxplot`, `stacked_bar`, `pca`.

**Requirements**: `matplotlib` (install with `pip install abi-agent[report]`).

### `abi.report` — Report Generation

| Function | Purpose |
| --- | --- |
| `write_generic_report()` | Simple Markdown + HTML + JSON summary (legacy) |
| `write_full_report()` | Complete report with methods, figures, citations, limitations, resource manifest |
| `write_methods()` | Standalone `methods.md` generator |
| `write_html_report()` | Full styled HTML report renderer |

**Submodules**:

| Module | Purpose |
| --- | --- |
| `abi.report.citations` | `CitationRegistry`, `load_citations()`, formatters |
| `abi.report.limitations` | `load_limitations()`, formatters |
| `abi.report.methods` | `write_methods()` |
| `abi.report.html` | `write_html_report()` |
| `abi.report.generic_report` | `write_generic_report()`, `write_full_report()` |

### `abi.workflow` — Workflow Support

| Module | Purpose |
| --- | --- |
| `abi.workflow.manifest` | `ResourceManifest`, `generate_resource_manifest()`, `checksum_file()` |
| `abi.workflow.validation` | `WorkflowValidator`, `check_required_artifacts()` |
| `abi.workflow.figure_specs` | `load_figure_specs()`, `validate_figure_specs()` |

## Plugin Integration

### Required Files

Each plugin should ship these YAML files:

```text
plugins/<plugin>/
  figure_specs.yaml        # Declare what figures to generate
  citation_registry.yaml   # Literature citations per tool
  limitations.yaml         # Known scientific/technical limitations
```

### Plugin write_report() Pattern

```python
def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
    from abi.report import write_full_report
    from abi.report.citations import load_citations
    from abi.report.limitations import load_limitations

    table_manager = StandardTableManager(self.table_schemas())
    summary = table_manager.summarize(Path(result_dir) / "tables")

    root = self.root
    citations = load_citations(root / "citation_registry.yaml") if (root / "citation_registry.yaml").exists() else []
    limitations = load_limitations(root / "limitations.yaml") if (root / "limitations.yaml").exists() else []

    return write_full_report(
        plan, result_dir,
        table_summary=summary,
        title=self.report_title,
        citations=citations,
        limitations=limitations,
    )
```

## Output Structure

After a successful run with `write_full_report()`:

```text
results/<analysis_type>/<run_id>/
  report/
    report.md              # Executive summary + table overview
    report.html            # Full styled HTML report
    report_summary.json    # Machine-readable summary
    methods.md             # Standalone methods section
  provenance/
    resource_manifest.json # Resource inventory with checksums
  figures/
    *.png                  # Rendered figures
  tables/
    *.tsv                  # Standard tables
```

## Figure Spec Format

```yaml
figures:
  - id: qc_read_counts
    type: bar
    source_table: qc_summary
    x: sample_id
    y: reads_after_filtering
    title: "Reads Retained After QC"
    required: true        # If true, missing data → error

  - id: volcano_deg
    type: volcano
    source_table: differential_expression
    x: log2_fold_change
    y: padj
    label: gene_id
    top_n: 30             # Label top N significant points
```

## Citation Format

```yaml
citations:
  - tool: fastp
    stage: qc
    citation: "Chen et al. 2018, Bioinformatics, doi:10.1093/bioinformatics/bty560"
```

## Limitations Format

```yaml
limitations:
  - "RNA-seq measures steady-state transcript abundance, not protein levels."
  - "Alignment rates depend on reference genome completeness."
```

## Design Principles

1. **Declarative**: Plugins declare what to output; core handles rendering.
2. **Schema-validated**: Figure specs validated against standard table schemas before rendering.
3. **Lazy imports**: matplotlib imported only at render time.
4. **Self-contained**: HTML reports use inline CSS, no external dependencies.
5. **Backward compatible**: `write_generic_report()` still works; existing plugins upgraded via `write_full_report()`.
