"""Base renderer interface for abi_sciplot."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RenderResult:
    """Output of a successful figure render.

    Contains paths to all generated files and the lint/provenance reports.
    """

    figure_id: str
    output_files: list[Path] = field(default_factory=list)
    lint_report_path: Path | None = None
    provenance_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "error" if self.errors else "ok"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "figure_id": self.figure_id,
            "outputs": [str(p) for p in self.output_files],
            "lint_report": str(self.lint_report_path) if self.lint_report_path else None,
            "provenance": str(self.provenance_path) if self.provenance_path else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class BaseRenderer(ABC):
    """Abstract base for figure renderers.

    Subclasses implement `supports()` and `render()` for specific backends.
    The render method handles the full pipeline: theme application, data
    loading, plot dispatch, export, provenance, and linting.
    """

    @abstractmethod
    def supports(self, figure_type: str) -> bool:
        """Return True if this renderer can handle *figure_type*."""
        ...

    @abstractmethod
    def render(self, spec: Any) -> RenderResult:
        """Render a FigureSpec and return structured results.

        Args:
            spec: A FigureSpec Pydantic model.

        Returns:
            RenderResult with output file paths, lint, and provenance.
        """
        ...
