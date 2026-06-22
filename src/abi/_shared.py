"""Shared utility functions used across ABI core and plugin modules.

These functions were previously duplicated in 2-5 different modules each.
Centralising them here eliminates DRY violations and ensures bug fixes
propagate everywhere.  Modules that previously defined their own copy
now import from this single source of truth.

Previously duplicated locations / 之前重复定义的位置
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``_read_tsv``        — 5 copies: cli, agent, results, engine.result_validation, engine.dashboard
* ``_display_command`` — 4 copies: provenance, executor, engine.logger, engine.pipeline
* ``_plan_dict``       — 2 copies: cli, agent
* ``_common_overrides``— 2 copies: cli, agent  (engine.cli has a different superset)
* ``_parse_fastp``     — 2+ copies: metagenomic_plasmid/_engine/parsers, rnaseq_expression
* ``_parse_sample_sheet``
  — 4 copies: rnaseq_expression, wgs_bacteria, amplicon_16s, metatranscriptomics
* ``_resolve_path``    — 4 copies (same plugins)
* ``_clean``           — 4 copies (same plugins)
"""

from __future__ import annotations

import csv
import json
import shlex
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from abi.config import compact_overrides


def _read_tsv(path: Path) -> list[dict[str, str]]:
    """Read a TSV file into a list of dicts.  Returns ``[]`` when the file is missing.

    Used for reading provenance files (commands.tsv, resolved_inputs.tsv) which
    may not exist yet for fresh or incomplete runs.

    Column order is deterministic — ``csv.DictReader`` returns ``OrderedDict``
    subclasses in Python 3.7+, preserving the TSV header order exactly (B14).
    """
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _display_command(command: Iterable[str]) -> str:
    """Format a shell command token list into a human-readable display string.

    Each token is shell-quoted via ``shlex.quote()`` so that tokens containing
    spaces or special characters render correctly.  The ``">"`` redirection
    token is preserved as-is (not quoted) so the displayed command reads
    naturally::

        tool --input file.fasta > output.txt

    ``str(token)`` is applied to every token before quoting so that non-string
    objects (e.g. ``Path``) are safely coerced.
    """
    return " ".join(">" if token == ">" else shlex.quote(str(token)) for token in command)


def _plan_dict(plan: Any, analysis_type: str) -> Dict[str, Any]:
    """Serialize a plan object to a dict, injecting ``analysis_type`` if absent.

    The analysis_type is stored inside the plan so that downstream consumers
    (report generation, inspection) can identify the plugin without external
    context.
    """
    data = plan.to_dict()
    data.setdefault("analysis_type", analysis_type)
    return data


def _common_overrides(
    *,
    mode: Optional[str] = None,
    threads: Optional[int] = None,
    outdir: Optional[str] = None,
    log_dir: Optional[str] = None,
    sample_sheet: Optional[Union[str, Path]] = None,
    dry_run: Optional[bool] = None,
    progress: Optional[bool] = None,
    resource_profile: Optional[str] = None,
    cpu_override: Optional[int] = None,
    memory_override: Optional[str] = None,
    walltime_override: Optional[str] = None,
    accelerator_override: Optional[str] = None,
    container_image: Optional[str] = None,
    container_runtime: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a compact overrides dict from common CLI flags.

    Maps CLI flags into the nested override structure expected by plugin
    config loading.  ``compact_overrides`` removes ``None`` values so only
    explicitly set flags affect the config.
    """
    overrides: Dict[str, Any] = {
        "mode": mode,
        "threads": threads,
        "outdir": outdir,
        "log_dir": log_dir,
        "dry_run": dry_run,
    }
    if sample_sheet:
        overrides["input"] = {"sample_sheet": str(sample_sheet)}
    if progress is not None:
        overrides["execution"] = {"progress": progress}
    # Resource overrides flow into execution.resources in config
    resource_overrides: Dict[str, Any] = {}
    if resource_profile:
        resource_overrides["resource_profile"] = resource_profile
    if cpu_override is not None:
        resource_overrides["cpu"] = cpu_override
    if memory_override:
        resource_overrides["memory"] = memory_override
    if walltime_override:
        resource_overrides["walltime"] = walltime_override
    if accelerator_override:
        resource_overrides["accelerator"] = accelerator_override
    if resource_overrides:
        overrides["execution"] = {
            **overrides.get("execution", {}),
            "resources": resource_overrides,
        }
    # Container overrides
    if container_image or container_runtime:
        container_overrides: Dict[str, Any] = {}
        if container_image:
            container_overrides["default_image"] = container_image
        if container_runtime:
            container_overrides["runtime"] = container_runtime
        overrides["execution"] = {
            **overrides.get("execution", {}),
            "container": container_overrides,
        }
    return compact_overrides(overrides)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared plugin utilities — previously duplicated across 4 inline plugins.
# ═══════════════════════════════════════════════════════════════════════════════


def _clean(value: Any) -> Optional[str]:
    """Strip whitespace and return *None* for empty strings.

    Used by sample sheet parsers in every inline plugin.
    """
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _resolve_path(
    value: str | Path,
    *,
    base_dirs: Iterable[Path],
) -> Path:
    """Resolve *value* against *base_dirs*, rejecting paths that escape.

    Absolute input paths are accepted because datasets commonly live outside
    the project. Relative paths are constrained to *base_dirs* and lexical
    ``..`` traversal is rejected.
    """
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    if ".." in path.parts:
        raise ValueError(f"Relative path traversal is not allowed: {value}")
    bases = [base_dir.resolve() for base_dir in base_dirs]
    if not bases:
        raise ValueError("At least one base directory is required for relative paths")
    for base_dir in bases:
        candidate = (base_dir / path).resolve()
        try:
            candidate.relative_to(base_dir)
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    # Return a deterministic, contained path for deferred/offline validation.
    candidate = (bases[0] / path).resolve()
    try:
        candidate.relative_to(bases[0])
    except ValueError as exc:
        raise ValueError(f"Relative path escapes its base directory: {value}") from exc
    return candidate


def _offline_sample_context(
    *,
    platform: str = "illumina",
    condition: str | None = None,
    group: str | None = None,
) -> Any:
    """Return an explicit unresolved sample for offline planning.

    ``check_files=False`` permits plan inspection without a sample sheet.  The
    sentinel values are machine-recognisable and cannot be mistaken for real
    sample data; this avoids leaking fixed test samples and ``/tmp`` paths into
    runtime plans.
    """
    from abi.schemas import ABISample, ABISampleContext

    return ABISampleContext(
        samples=[
            ABISample(
                sample_id="SAMPLE_NOT_CONFIGURED",
                platform=platform,
                read1="READ1_NOT_CONFIGURED",
                read2="READ2_NOT_CONFIGURED",
                condition=condition,
                group=group,
            )
        ],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )


def _execute_generic_dry_run(plugin: Any, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
    """Run the shared mock executor for an inline plugin dry-run hook."""
    from abi.executor import GenericABIExecutor
    from abi.internal import plugin_internal_handlers
    from abi.provenance import RunLogger
    from abi.tables import StandardTableManager

    executor = GenericABIExecutor(
        plugin.registry(),
        RunLogger(str(config["log_dir"])),
        table_manager=StandardTableManager(plugin.table_schemas()),
        parse_outputs=plugin.parse_outputs,
        report_title=plugin.report_title,
        mock_tools=True,
        internal_handlers=plugin_internal_handlers(plugin),
    )
    return executor.dry_run(plan, config)


def _parse_fastp(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse fastp JSON output → qc_summary rows.

    Reads the fastp JSON report, extracts ``summary.before_filtering`` and
    ``summary.after_filtering`` blocks, and flattens each metric into a
    key-value row.  Shared by all plugins that use fastp for read QC.
    """
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        summary = data.get("summary", {})
        if not isinstance(summary, dict):
            continue
        before = summary.get("before_filtering", {})
        after = summary.get("after_filtering", {})
        for prefix, block in [
            ("before_filtering", before),
            ("after_filtering", after),
        ]:
            if not isinstance(block, dict):
                continue
            for metric, value in block.items():
                rows.append(
                    {
                        "sample_id": sample_id,
                        "tool": "fastp",
                        "metric": f"{prefix}.{metric}",
                        "value": value,
                        "unit": "",
                        "source_file": str(path),
                    }
                )
    return rows


def _parse_star(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse STAR ``Log.final.out`` → alignment_summary rows.

    STAR writes a pipe-delimited key-value log.  Each line is split on ``|``
    and both sides are stripped.  All metrics are emitted as key-value rows.
    Shared by rnaseq_expression and metatranscriptomics plugins.
    """
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("*Log.final.out")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or "|" not in line:
                        continue
                    parts = line.split("|", 1)
                    if len(parts) != 2:
                        continue
                    metric = parts[0].strip()
                    value = parts[1].strip()
                    if not metric:
                        continue
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "tool": "star",
                            "metric": metric,
                            "value": value,
                            "unit": "",
                            "source_file": str(path),
                        }
                    )
        except (OSError, UnicodeDecodeError):
            continue
    return rows


def _parse_sample_sheet_tabular(
    path: str | Path,
    *,
    required_columns: Iterable[str] = ("sample_id", "read1", "read2"),
    check_files: bool = True,
    extra_fields: Iterable[str] = ("group", "condition", "platform"),
    file_fields: Iterable[str] = ("read1", "read2", "long_reads", "assembly"),
    base_dirs: Iterable[Path] = (),
) -> List[Dict[str, Any]]:
    """Parse a tab-separated sample sheet into a list of row dicts.

    Validates that *required_columns* are present.  Optionally checks that
    file paths in *check_fields* exist.  Skips empty rows.  Row numbers in
    error messages are 2-based (header = row 1).

    Returns rows as plain dicts keyed by the TSV header names (lowercase,
    whitespace stripped).  Callers wrap with their own typed objects
    (e.g. ``ABISample``).
    """
    del extra_fields  # Accepted for backward compatibility; all TSV columns are retained.
    sample_sheet = Path(path)
    if not sample_sheet.exists():
        raise ValueError(f"Sample sheet does not exist: {sample_sheet}")
    with sample_sheet.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Sample sheet is empty: {sample_sheet}")
        columns = set(reader.fieldnames)
        missing = set(required_columns) - columns
        if missing:
            raise ValueError(f"Sample sheet missing required columns: {sorted(missing)}")
        rows: List[Dict[str, Any]] = []
        for index, row in enumerate(reader, start=2):
            cleaned: Dict[str, Any] = {}
            for key, val in row.items():
                cleaned[key.strip().lower()] = _clean(val)
            # Skip completely empty rows
            if not any(cleaned.values()):
                continue
            # Validate required columns
            for col in required_columns:
                if not cleaned.get(col):
                    raise ValueError(f"Row {index}: {col} is required")
            for field in file_fields:
                value = cleaned.get(field)
                if value:
                    cleaned[field] = str(
                        _resolve_path(
                            value,
                            base_dirs=[sample_sheet.parent, *base_dirs],
                        )
                    )
            rows.append(cleaned)
    if not rows:
        raise ValueError("Sample sheet contains no sample rows")
    if check_files:
        missing_files = []
        for row in rows:
            for field in file_fields:
                val = row.get(field)
                if val and not Path(str(val)).exists():
                    missing_files.append(f"{row.get('sample_id', '?')}:{field}={val}")
        if missing_files:
            raise ValueError("Input files do not exist: " + "; ".join(missing_files))
    return rows
