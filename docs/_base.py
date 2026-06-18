"""Sphinx configuration for ABI (Agent-Bioinformatics Interface).

This is the shared base config — language-specific overrides live in
``en/conf.py`` and ``zh/conf.py``.  Do not build from this file directly.
"""

import sys
from pathlib import Path

# -- Project information ----------------------------------------------------
project = "ABI"
copyright = "2026, BingkangGuo"
author = "BingkangGuo"
release = "1.3.3"

# -- Path setup -------------------------------------------------------------
# _base.py lives in docs/; repo root is one level up
_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))

# -- General configuration --------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "myst_parser",
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

# -- HTML output (shared, with paths relative to sub-conf.py) ---------------
html_theme = "furo"
html_static_path = ["../_static"]
html_css_files = ["custom.css", "lang-toggle.css"]
html_js_files = ["lang-toggle.js"]

# Build shared theme options as a plain dict — sub-configs deep-copy and
# customise the announcement, title, etc.
shared_html_theme_options = {
    # ── Logo ───────────────────────────────────────────────────────────
    "light_logo": "logo-light.png",
    "dark_logo": "logo-dark.png",
    "sidebar_hide_name": False,

    # ── Source repository ──────────────────────────────────────────────
    "top_of_page_button": "edit",
    "source_repository": "https://github.com/sleepinlava/abi/",
    "source_branch": "master",
    "source_directory": "docs/",

    # ── Navigation ─────────────────────────────────────────────────────
    "navigation_with_keys": True,

    # ── Footer ─────────────────────────────────────────────────────────
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/sleepinlava/abi",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" '
                'stroke-width="0" viewBox="0 0 16 16">'
                '<path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 '
                "3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 "
                "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94"
                "-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01"
                "-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 "
                "2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89"
                "-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02"
                ".08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2"
                "-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82"
                ".44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 "
                "3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 "
                "1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 "
                '8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>'
                "</svg>"
            ),
            "class": "",
        },
    ],

    # ── Color branding (light mode) ────────────────────────────────────
    "light_css_variables": {
        "color-brand-primary": "#1e6fba",
        "color-brand-content": "#1a5a96",
        "color-admonition-background": "#e8f4fd",
        "color-announcement-background": "#1e6fba",
        "color-announcement-text": "#ffffff",
        "color-sidebar-background": "#f8f9fb",
        "color-sidebar-brand": "#1e6fba",
        "color-sidebar-link--current": "#1e6fba",
        "color-sidebar-item-background--current": "#e8f4fd",
        "color-link": "#1e6fba",
        "color-link--hover": "#155a8a",
        "color-inline-code-background": "#f0f4f8",
    },

    # ── Color branding (dark mode) ─────────────────────────────────────
    "dark_css_variables": {
        "color-brand-primary": "#5ba4e6",
        "color-brand-content": "#7db8e8",
        "color-admonition-background": "#1a2d42",
        "color-announcement-background": "#1a2d42",
        "color-announcement-text": "#c8ddf0",
        "color-sidebar-background": "#1a1d22",
        "color-sidebar-brand": "#5ba4e6",
        "color-sidebar-link--current": "#5ba4e6",
        "color-sidebar-item-background--current": "#1a2d42",
        "color-link": "#5ba4e6",
        "color-link--hover": "#7db8e8",
        "color-inline-code-background": "#252830",
    },
}

# -- Source suffixes --------------------------------------------------------
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Exclude patterns -------------------------------------------------------
exclude_patterns = [
    "_build",
    "en",
    "zh",
]
