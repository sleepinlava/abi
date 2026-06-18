"""Sphinx configuration for ABI Chinese documentation.

Imports shared settings from ``docs/_base.py`` then overrides
language and Chinese-specific announcements.
"""

import copy
import sys
from pathlib import Path

# Make docs/ importable so we can ``from _base import *``
_docs_dir = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, _docs_dir)

# pylint: disable=wildcard-import,unused-wildcard-import,wrong-import-position
from _base import *  # noqa: E402, F403

# -- Chinese-specific overrides ---------------------------------------------
language = "zh_CN"
html_title = "ABI 文档"

# Build language-aware announcement
html_theme_options = copy.deepcopy(shared_html_theme_options)  # noqa: F821
html_theme_options["announcement"] = (
    "<strong>ABI v1.3.0</strong> &middot; "
    "<a href='/en/'>English</a> &middot; "
    "<a href='https://github.com/sleepinlava/abi/releases'>changelog</a>"
)
