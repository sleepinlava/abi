"""Workflow validation helpers for ABI.

# Purpose / 目的
Provides helpers that plugins and the ABI core use to validate workflow
completeness: do all required artifacts exist?  Are resource manifests
complete?  Do figure specs reference valid tables?

These checks are designed to be run as part of ``abi contract-lint``
and CI pipelines, not during agent runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "WorkflowValidator",
    "check_required_artifacts",
]


class WorkflowValidator:
    """Collects and runs workflow-level validation checks.

    # Usage / 用法
        validator = WorkflowValidator(result_dir)
        validator.check_provenance()
        validator.check_tables(table_schemas)
        validator.check_report()
        if validator.errors:
            for err in validator.errors:
                print(f"FAIL: {err}")
    """

    def __init__(self, result_dir: str | Path) -> None:
        self.result_dir = Path(result_dir)
        self._errors: List[str] = []
        self._warnings: List[str] = []

    @property
    def errors(self) -> List[str]:
        return list(self._errors)

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    @property
    def is_valid(self) -> bool:
        return len(self._errors) == 0

    # ── Checks / 检查 ──

    def check_provenance(self) -> None:
        """Verify provenance artifacts exist."""
        prov = self.result_dir / "provenance"
        required = [
            "commands.tsv",
            "resolved_inputs.tsv",
            "tool_versions.tsv",
            "run_summary.json",
            "checksums.json",
            "progress.jsonl",
        ]
        if not prov.is_dir():
            self._errors.append("provenance/ directory missing")
            return
        for filename in required:
            if not (prov / filename).exists():
                self._errors.append(f"provenance/{filename} missing")

    def check_tables(
        self,
        table_schemas: Mapping[str, Sequence[str]],
    ) -> None:
        """Verify standard tables exist and have headers."""
        tables_dir = self.result_dir / "tables"
        if not tables_dir.is_dir():
            self._errors.append("tables/ directory missing")
            return
        for table_name, columns in table_schemas.items():
            tsv = tables_dir / f"{table_name}.tsv"
            if not tsv.exists():
                self._errors.append(f"tables/{table_name}.tsv missing")
                continue
            try:
                header = tsv.read_text(encoding="utf-8").split("\n", 1)[0]
                observed = set(header.split("\t"))
                expected = set(columns)
                missing = expected - observed
                if missing:
                    self._errors.append(
                        f"tables/{table_name}.tsv missing columns: {sorted(missing)}"
                    )
            except Exception as exc:
                self._errors.append(f"tables/{table_name}.tsv: {exc}")

    def check_report(self) -> None:
        """Verify report artifacts exist."""
        report_dir = self.result_dir / "report"
        if not report_dir.is_dir():
            self._warnings.append("report/ directory missing (optional)")
            return
        for filename in ("report.md", "report.html"):
            if not (report_dir / filename).exists():
                self._warnings.append(f"report/{filename} missing")

    def check_resource_manifest(self) -> None:
        """Verify resource manifest exists and is valid JSON."""
        manifest_path = self.result_dir / "provenance" / "resource_manifest.json"
        if not manifest_path.exists():
            self._warnings.append(
                "provenance/resource_manifest.json missing (required for reproducibility claims)"
            )
            return
        try:
            import json

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                self._errors.append("resource_manifest.json is not a JSON object")
            resources = data.get("resources", [])
            if not isinstance(resources, list):
                self._errors.append("resource_manifest.json 'resources' is not a list")
            for i, r in enumerate(resources):
                if not isinstance(r, dict):
                    self._errors.append(f"resource_manifest.json resource[{i}] is not an object")
                    continue
                if not r.get("id"):
                    self._errors.append(f"resource_manifest.json resource[{i}] missing 'id'")
        except Exception as exc:
            self._errors.append(f"resource_manifest.json: {exc}")

    def check_figures(self, expected_ids: Sequence[str]) -> None:
        """Verify expected figure files exist."""
        figures_dir = self.result_dir / "figures"
        if not figures_dir.is_dir():
            self._warnings.append("figures/ directory missing (optional)")
            return
        for fig_id in expected_ids:
            png = figures_dir / f"{fig_id}.png"
            if not png.exists():
                self._errors.append(f"figures/{fig_id}.png missing")


def check_required_artifacts(
    result_dir: str | Path,
    *,
    table_schemas: Optional[Mapping[str, Sequence[str]]] = None,
    expected_figures: Optional[Sequence[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Quick one-shot check of required pipeline artifacts.

    Returns ``(errors, warnings)``.  Errors indicate missing required
    artifacts; warnings indicate missing optional but recommended artifacts.
    """
    validator = WorkflowValidator(result_dir)
    validator.check_provenance()
    if table_schemas:
        validator.check_tables(table_schemas)
    validator.check_report()
    validator.check_resource_manifest()
    if expected_figures:
        validator.check_figures(expected_figures)
    return validator.errors, validator.warnings
