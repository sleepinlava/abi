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
"""

from __future__ import annotations

import csv
import shlex
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

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


def _sorted_columns(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return rows with columns sorted alphabetically for deterministic output (B14).

    Use this when writing golden files or comparing standard table output
    where column order must be stable across Python versions and platforms.
    """
    if not rows:
        return rows
    sorted_keys = sorted(rows[0].keys())
    return [{k: row[k] for k in sorted_keys} for row in rows]


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
    return compact_overrides(overrides)


def _fetch_url_safe(url: str, *, timeout: float = 10.0) -> str:
    """Fetch a URL with timeout and graceful fallback (B9/B22 fix).

    Returns the response body as a string on success, or ``""`` on any
    failure (timeout, DNS error, HTTP error).  Never raises — callers
    should check for an empty return value and handle the fallback.

    Use this for non-critical external resources (CrossRef API, database
    source URLs) where the pipeline should not abort on network issues.
    """
    import urllib.error as _error
    import urllib.request as _request

    try:
        req = _request.Request(url, headers={"User-Agent": "ABI/1.0"})
        with _request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (_error.URLError, _error.HTTPError, OSError, ValueError, TimeoutError):
        return ""
