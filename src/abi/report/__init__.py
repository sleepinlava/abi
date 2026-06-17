"""ABI report generation — generic, plugin-agnostic report writing.

# Usage / 用法
    from abi.report import (
        write_generic_report,     # Markdown + HTML + JSON summary (simple)
        write_full_report,        # Complete report with methods, figures, citations
        write_methods,            # methods.md generator
        write_html_report,        # Full HTML report renderer
        load_limitations,         # YAML limitations loader
        load_citations,           # YAML citations loader
        CitationRegistry,         # Structured citation holder
    )

# Architecture / 架构
The report module has two layers:
1. **Low-level formatters** (``methods.py``, ``limitations.py``, ``citations.py``):
   Load data from YAML or structured inputs, produce Markdown or HTML strings.
2. **High-level writers** (``generic_report.py``, ``html.py``):
   Compose sections into complete report files.

Plugins call ``abi.report.write_full_report()`` as their final step; the
individual formatters are available for plugins that need more control.
"""
from abi.report.citations import (
    CitationRegistry,
    format_citations_html,
    format_citations_markdown,
    load_citations,
)
from abi.report.generic_report import write_full_report, write_generic_report
from abi.report.html import write_html_report
from abi.report.limitations import (
    format_limitations_html,
    format_limitations_markdown,
    load_limitations,
)
from abi.report.methods import write_methods

__all__ = [
    "CitationRegistry",
    "format_citations_html",
    "format_citations_markdown",
    "format_limitations_html",
    "format_limitations_markdown",
    "load_citations",
    "load_limitations",
    "write_full_report",
    "write_generic_report",
    "write_html_report",
    "write_methods",
]
