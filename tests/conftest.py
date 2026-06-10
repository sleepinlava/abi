"""Shared test fixtures for ABI."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on the path for editable installs
src = Path(__file__).resolve().parents[1] / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))
