# Plugin Report & Figure Specification System

> **Status**: Implemented (2026-06-18); sciplot integration (2026-06-20, v1.4.0)

## Overview

The ABI report & figure system provides a **declarative, plugin-agnostic** way to generate publication-ready reports and figures from standard tables. Plugins declare *what* to output; the ABI core handles *how* to render.

ABI now has **two figure systems**:

| System | Module | Status | Use |
|--------|--------|--------|-----|
| **abi.sciplot** | `abi.sciplot` | v1.4.0, 15 plot types | **Recommended** for new plugins |
| **FigureEngine** | `abi.figures` | 7 plot types, maintained | Legacy plugins, backward compat |

## Architecture

```text
Plugin declaration (YAML)          ABI Core (Python)
─────────────────────────         ──────────────────
figure_specs.yaml          →      abi.sciplot (primary) / abi.figures.FigureEngine (legacy)
citation_registry.yaml     →      abi.report.citations.CitationRegistry
limitations.yaml           →      abi.report.limitations.load_limitations
standard_tables.yaml       →      abi.tables.StandardTableManager
abi-plugin.yaml            →      abi.workflow.manifest.ResourceManifest
```

## Module Reference

### `abi.sciplot` — Scientific Figure Compiler (Recommended)

```python
from abi.sciplot import render_figure, validate_spec, lint_figure, load_spec

spec = load_spec("plugins/rnaseq/figure_specs.yaml")
validate_spec(spec)
renderings = render_figure(spec, output_dir="figures/")
# Renders to PDF + SVG + PNG + TIFF
lint_result = lint_figure(renderings)
```

**15 supported plot types** (v1.4.0): bar, scatter, volcano, heatmap, boxplot,
stacked_bar, pca, line, histogram, venn, upset, enrichment_dot, ma, density,
qq. Three themes: `abi_nature`, `abi_cell`, `abi_report`. Backends: plotnine
(ggplot2 grammar) + seaborn. Includes SHA256 provenance, 17 lint rules, and
colorblind-safe palettes.

**Requirements**: `plotnine`, `seaborn` (install with `pip install abi-agent[sciplot]`).

### `abi.figures` — Figure Engine (Legacy)

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
| `write_plugin_report()` | Markdown + HTML + JSON summary with sciplot integration |
| `write_full_report()` | Complete report with methods, figures, citations, limitations, resource manifest |
| `write_methods()` | Standalone `methods.md` generator |
| `write_html_report()` | Full styled HTML report renderer |
| `write_generic_report()` | Simple Markdown + HTML + JSON summary (legacy) |

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
        use_sciplot=True,  # Enable sciplot rendering for figures
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
    *.png / *.pdf / *.svg  # Rendered figures (sciplot: PDF+SVG+PNG+TIFF)
  tables/
    *.tsv                  # Standard tables
```

## Figure Spec Format

### sciplot format (recommended)

```yaml
figures:
  - id: qc_read_counts
    type: barplot
    source_table: qc_summary
    x: sample_id
    y: reads_after_filtering
    title: "Reads Retained After QC"
    theme: abi_nature
    required: true        # If true, missing data → error

  - id: volcano_deg
    type: volcano
    source_table: differential_expression
    x: log2_fold_change
    y: padj
    label: gene_id
    top_n: 30             # Label top N significant points
```

### FigureEngine format (legacy)

```yaml
figures:
  - id: qc_read_counts
    type: bar
    source_table: qc_summary
    x: sample_id
    y: reads_after_filtering
    title: "Reads Retained After QC"
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
3. **Lazy imports**: Plotting backends imported only at render time.
4. **Self-contained**: HTML reports use inline CSS, no external dependencies.
5. **Backward compatible**: `write_generic_report()` still works; existing plugins upgraded via `write_full_report()`.
6. **Provenance-tracked**: sciplot figures carry SHA256 checksums and render metadata.
