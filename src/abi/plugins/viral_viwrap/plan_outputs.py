"""Shared lookup for named outputs in the canonical ViWrap plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def find_plan_output(plan: Any, name: str) -> Path | None:
    for step in plan.steps:
        if name in step.outputs:
            return Path(str(step.outputs[name]))
    return None
