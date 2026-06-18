"""Sphinx configuration for ABI (Agent-Bioinformatics Interface)."""

import sys
from pathlib import Path

# -- Project information ----------------------------------------------------
project = "ABI"
copyright = "2026, BingkangGuo"
author = "BingkangGuo"
release = "1.2.0"

# -- Path setup -------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# -- General configuration --------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",         # auto-document from docstrings
    "sphinx.ext.autosummary",     # summary tables for modules/classes
    "sphinx.ext.viewcode",        # link to source code
    "sphinx.ext.intersphinx",     # link to external docs
    "sphinx.ext.napoleon",        # Google/NumPy style docstrings
    "myst_parser",                # Markdown support
]

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"
autosummary_generate = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3.10", None),
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

# -- HTML output ------------------------------------------------------------
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
}
html_static_path = []
html_title = "ABI Documentation"

# -- Source suffixes --------------------------------------------------------
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Exclude patterns -------------------------------------------------------
exclude_patterns = [
    "_build",
    "*_zh.md",          # Chinese translations — read directly on GitHub
]
