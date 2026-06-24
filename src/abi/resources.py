"""ABI resource checking and setup orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from abi.errors import ABIError
from abi.interfaces import ABIResourcePlugin
from abi.plugins import get_plugin
from abi.timeouts import DEFAULT_RESOURCE_TIMEOUT_SECONDS, timeout_from_env_or_value

__all__ = ["check_resources", "setup_resources"]

_PLACEHOLDER_MARKERS = ("NOT_CONFIGURED", "TODO", "PLACEHOLDER")


def _resource_timeout(config: Mapping[str, Any]) -> float | None:
    execution = config.get("execution", {})
    configured = (
        execution.get("resource_timeout_seconds") if isinstance(execution, Mapping) else None
    )
    return timeout_from_env_or_value(
        "ABI_RESOURCE_TIMEOUT_SECONDS",
        configured,
        default=DEFAULT_RESOURCE_TIMEOUT_SECONDS,
    )


def check_resources(
    *,
    analysis_type: str,
    config: Mapping[str, Any],
    resource_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Check configured resources for an ABI analysis type."""
    plugin = get_plugin(analysis_type)
    if isinstance(plugin, ABIResourcePlugin):
        return plugin.check_resources(config, resource_ids=resource_ids)
    return _check_generic_resources(analysis_type, config, resource_ids=resource_ids)


def setup_resources(
    *,
    analysis_type: str,
    config: Mapping[str, Any],
    resource_ids: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    mock: bool = False,
) -> List[Dict[str, Any]]:
    """Prepare or plan resources for an ABI analysis type."""
    plugin = get_plugin(analysis_type)
    if isinstance(plugin, ABIResourcePlugin):
        return plugin.setup_resources(
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
            mock=mock,
        )
    if not dry_run and not mock:
        raise ABIError(
            f"Resource setup is not implemented for analysis type {analysis_type!r}. "
            "Use --dry-run to inspect the resource plan or configure paths manually."
        )
    rows = _check_generic_resources(analysis_type, config, resource_ids=resource_ids)
    planned = []
    for row in rows:
        planned_row = dict(row)
        if dry_run:
            planned_row["status"] = "planned"
            planned_row["message"] = "No downloader is registered; configure this path manually."
        elif mock:
            path = Path(str(row["path"]))
            path.mkdir(parents=True, exist_ok=True)
            (path / ".abi_mock_resource").write_text(
                f"{analysis_type}:{row['resource_id']}\n",
                encoding="utf-8",
            )
            planned_row["status"] = "ok"
            planned_row["message"] = "Mock resource directory prepared."
        planned.append(planned_row)
    return planned


def _setup_manual_resource_bundle(
    analysis_type: str,
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]],
    dry_run: bool,
    mock: bool,
) -> List[Dict[str, Any]]:
    """Prepare mock bundles or report explicit manual setup requirements.

    These plugins depend on organism/site-specific databases or an upstream
    multi-environment installation.  Automatically choosing or partially
    downloading such resources would create a misleading runnable state.
    """
    rows = _check_generic_resources(analysis_type, config, resource_ids=resource_ids)
    planned: List[Dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        target = _configured_or_default_resource_path(config, str(current["resource_id"]))
        current["path"] = str(target)
        if current["status"] == "ok":
            current["message"] = "Configured resource exists."
        elif mock:
            target.mkdir(parents=True, exist_ok=True)
            (target / ".abi_mock_resource").write_text(
                f"{analysis_type}:{current['resource_id']}\n",
                encoding="utf-8",
            )
            current["status"] = "ok"
            current["message"] = "Mock resource directory prepared."
        elif dry_run:
            current["status"] = "planned"
            current["message"] = (
                "Would verify this manually provisioned resource; no implicit "
                "database or environment selection is performed."
            )
        else:
            current["status"] = "manual_required"
            current["message"] = (
                "Provision the upstream database/environment bundle, then set "
                f"resources.{current['resource_id']} to its validated path."
            )
        current.setdefault("command", [])
        current.setdefault("ready_check", "non_empty_directory")
        current.setdefault("source_url", "")
        current.setdefault("version", "")
        current.setdefault("checksum", "")
        planned.append(current)
    return planned


def _configured_or_default_resource_path(config: Mapping[str, Any], resource_id: str) -> Path:
    resources = config.get("resources", {})
    value = resources.get(resource_id) if isinstance(resources, Mapping) else None
    if value and not _is_placeholder_resource_value(value):
        return Path(str(value))
    return Path(str(config.get("outdir", "results"))) / "resources" / resource_id


def _is_placeholder_resource_value(value: Any) -> bool:
    text = str(value).strip()
    upper = text.upper()
    if any(marker in upper for marker in _PLACEHOLDER_MARKERS):
        return True
    normalized = text.replace("\\", "/").lower()
    return normalized.startswith(("/path/to/", "path/to/", "/your/path/", "your/path/"))


def _setup_wgs_bacteria(
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]],
    dry_run: bool,
    mock: bool,
) -> List[Dict[str, Any]]:
    """Prepare the AMRFinderPlus database used by the WGS DAG."""
    import subprocess

    if resource_ids and "amrfinder_db" not in resource_ids:
        return []
    target = _configured_or_default_resource_path(config, "amrfinder_db")
    command = ["amrfinder_update", "--database", str(target)]
    if dry_run:
        status = "planned"
        message = "Would download/update the AMRFinderPlus database."
    elif mock:
        target.mkdir(parents=True, exist_ok=True)
        (target / ".abi_mock_resource").write_text("wgs_bacteria:amrfinder_db\n", encoding="utf-8")
        status = "ok"
        message = "Mock AMRFinderPlus database prepared."
    elif target.exists() and any(target.iterdir()):
        status = "ok"
        message = "Existing AMRFinderPlus database found; update skipped."
    else:
        target.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_resource_timeout(config),
            )
            status = "ok" if result.returncode == 0 else "error"
            message = (result.stdout or result.stderr or "").strip()[-500:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            status = "error"
            message = str(exc)
    return [
        {
            "resource_id": "amrfinder_db",
            "tool_id": "amrfinderplus",
            "field": "amrfinder_db",
            "path": str(target),
            "status": status,
            "version": "",
            "source_url": "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/",
            "checksum": "",
            "command": command,
            "ready_check": "non_empty_directory",
            "directory_file_count": _directory_file_count(target),
            "directory_size_bytes": 0,
            "message": message,
        }
    ]


def _setup_reference_resources(
    analysis_type: str,
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]],
    dry_run: bool,
    mock: bool,
) -> List[Dict[str, Any]]:
    """Plan or mock organism-specific reference resources.

    Genome indices and annotations cannot be downloaded correctly without an
    organism/build choice. Real setup therefore reports an actionable
    ``manual_required`` status rather than raising a generic not-implemented
    error or silently choosing the wrong reference.
    """
    selected = set(resource_ids or [])
    rows: List[Dict[str, Any]] = []
    for resource_id in ("genome_index", "annotation_gtf"):
        if selected and resource_id not in selected:
            continue
        target = _configured_or_default_resource_path(config, resource_id)
        if target.exists():
            status = "ok"
            message = "Configured reference resource exists."
        elif dry_run:
            status = "planned"
            message = "Select an organism/genome build and configure this reference path."
        elif mock:
            if resource_id == "genome_index":
                target.mkdir(parents=True, exist_ok=True)
                (target / ".abi_mock_resource").write_text(
                    f"{analysis_type}:{resource_id}\n", encoding="utf-8"
                )
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    'chrMock\tABI\tgene\t1\t4\t.\t+\t.\tgene_id "MOCK1";\n',
                    encoding="utf-8",
                )
            status = "ok"
            message = "Mock reference resource prepared."
        else:
            status = "manual_required"
            message = (
                "Automatic download requires an organism/genome build choice; "
                "configure the reference path explicitly."
            )
        rows.append(
            {
                "resource_id": resource_id,
                "tool_id": "star" if resource_id == "genome_index" else "featurecounts",
                "field": resource_id,
                "path": str(target),
                "status": status,
                "version": "",
                "source_url": "",
                "checksum": "",
                "command": [],
                "ready_check": "path_exists",
                "directory_file_count": _directory_file_count(target),
                "directory_size_bytes": 0,
                "message": message,
            }
        )
    return rows


def _check_generic_resources(
    analysis_type: str,
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]],
) -> List[Dict[str, Any]]:
    get_plugin(analysis_type)
    resources = config.get("resources", {})
    if not isinstance(resources, Mapping):
        return []
    selected = set(resource_ids or [])
    rows = []
    for key, value in sorted(resources.items()):
        if key == "root":
            continue
        if selected and key not in selected:
            continue
        if isinstance(value, Mapping):
            path_value = value.get("path") or value.get("database") or value.get("directory")
        else:
            path_value = value
        path = Path(str(path_value or ""))
        status = _generic_resource_status(path_value)
        rows.append(
            {
                "resource_id": str(key),
                "tool_id": "",
                "field": str(key),
                "path": str(path),
                "status": status,
                "version": "",
                "source_url": "",
                "checksum": "",
                "command": [],
                "ready_check": "path_exists",
                "directory_file_count": (_directory_file_count(path) if status == "ok" else 0),
                "directory_size_bytes": 0,
                "message": _generic_resource_message(status),
            }
        )
    return rows


def _generic_resource_status(value: Any) -> str:
    if value is None or value == "":
        return "not_configured"
    text = str(value)
    if any(marker in text for marker in _PLACEHOLDER_MARKERS):
        return "not_configured"
    path = Path(text)
    return "ok" if path.exists() else "missing"


def _generic_resource_message(status: str) -> str:
    if status == "ok":
        return "Configured resource path exists."
    if status == "missing":
        return "Configured resource path does not exist."
    return "Resource path is not configured."


def _directory_file_count(path: Path) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    return sum(1 for child in path.rglob("*") if child.is_file())


def _check_rnaseq_expression(
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Check rnaseq_expression resources including DESeq2 installation."""
    import os
    import subprocess

    rows = _check_generic_resources("rnaseq_expression", config, resource_ids=resource_ids)
    selected = set(resource_ids or [])
    if selected and "deseq2_package" not in selected:
        return rows

    # Check DESeq2 availability via Rscript
    deseq2_status = "not_installed"
    deseq2_version = ""
    rscript = os.environ.get("ABI_RSCRIPT_PATH", "Rscript")

    try:
        result = subprocess.run(
            [
                rscript,
                "--no-save",
                "-e",
                'if (requireNamespace("DESeq2", quietly=TRUE)) '
                'cat("OK:", as.character(packageVersion("DESeq2")))',
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if "OK:" in (result.stdout or ""):
            deseq2_status = "ok"
            deseq2_version = result.stdout.strip().split(":", 1)[-1].strip()
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        deseq2_status = "not_installed"

    rows.append(
        {
            "resource_id": "deseq2_package",
            "tool_id": "deseq2",
            "field": "r_package",
            "path": rscript,
            "status": deseq2_status,
            "version": deseq2_version,
            "source_url": "https://bioconductor.org/packages/DESeq2/",
            "checksum": "",
            "command": [rscript, "-e", "library(DESeq2)"],
            "ready_check": "r_package_loaded",
            "directory_file_count": 0,
            "directory_size_bytes": 0,
            "message": (
                f"DESeq2 {deseq2_version} found."
                if deseq2_status == "ok"
                else "DESeq2 is not installed. Run: abi setup-resources --type rnaseq_expression"
            ),
        }
    )
    return rows


def _setup_rnaseq_expression(
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]] = None,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Set up the rnaseq_expression conda environment and R packages.

    Runs ``scripts/setup_rnaseq_env.sh`` which creates the ``rnaseq`` conda
    environment with fastp, STAR, featureCounts, and R, then installs DESeq2
    from Bioconductor.
    """
    import os
    import subprocess

    from abi.config import PROJECT_ROOT

    selected = set(resource_ids or [])
    if selected and "rnaseq_environment" not in selected:
        return _check_generic_resources("rnaseq_expression", config, resource_ids=resource_ids)

    setup_script = PROJECT_ROOT / "scripts" / "setup_rnaseq_env.sh"
    if not setup_script.exists():
        raise ABIError(
            "setup_rnaseq_env.sh not found. "
            "Reinstall ABI or create the rnaseq environment manually."
        )

    mamba_root = str(
        config.get("mamba_root") or os.environ.get("MAMBA_ROOT") or str(PROJECT_ROOT / ".mamba")
    )

    cmd = ["bash", str(setup_script), "--mamba-root", mamba_root]
    if dry_run:
        cmd.append("--dry-run")

    rows: List[Dict[str, Any]] = []
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        status = "ok" if result.returncode == 0 else "error"
        message = result.stdout.strip()[-500:] if result.stdout else ""
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "")[-500:]
    except OSError as exc:
        status = "error"
        message = str(exc)

    # Check for the marker file written by install_deseq2.R
    rnaseq_env = Path(mamba_root) / "envs" / "rnaseq"
    r_lib = rnaseq_env / "lib" / "R" / "library"
    marker = r_lib / ".abi_deseq2_installed"
    deseq2_installed = marker.exists()

    # Also check system R library as fallback
    if not deseq2_installed:
        for lib_path in (".R", "R"):  # common system R library dirs
            sys_lib = Path.home() / lib_path
            for marker_candidate in sys_lib.glob("**/.abi_deseq2_installed"):
                if marker_candidate.exists():
                    deseq2_installed = True
                    break

    rows.append(
        {
            "resource_id": "rnaseq_environment",
            "tool_id": "deseq2",
            "field": "env_setup",
            "path": str(setup_script),
            "status": status if not dry_run else "planned",
            "version": "",
            "source_url": "https://bioconductor.org/packages/DESeq2/",
            "checksum": "",
            "command": cmd,
            "ready_check": "deseq2_package_installed",
            "directory_file_count": 0,
            "directory_size_bytes": 0,
            "message": (f"DESeq2 installed: {deseq2_installed}. Env path: {rnaseq_env}. {message}"),
        }
    )

    # Also run generic resource checks for genomes, annotations, etc.
    generic_rows = _check_generic_resources("rnaseq_expression", config, resource_ids=resource_ids)
    for gr in generic_rows:
        if gr["resource_id"] != "rnaseq_environment":
            rows.append(gr)

    return rows


def _check_amplicon_16s(
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Check amplicon_16s resources including taxonomy database."""
    rows = _check_generic_resources("amplicon_16s", config, resource_ids=resource_ids)
    selected = set(resource_ids or [])
    if selected and "taxonomy_db" not in selected:
        return rows

    # Check taxonomy DB
    taxonomy_db = config.get("resources", {}).get("taxonomy_db", "TAXONOMY_DB_NOT_CONFIGURED")
    tax_path = Path(str(taxonomy_db))
    tax_status = "missing"
    tax_entries = 0
    if tax_path.exists():
        try:
            with tax_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith(">") and ";tax=" in line:
                        tax_entries += 1
            tax_status = "ok" if tax_entries > 0 else "invalid"
        except (OSError, UnicodeDecodeError):
            tax_status = "invalid"

    rows.append(
        {
            "resource_id": "taxonomy_db",
            "tool_id": "vsearch_taxonomy",
            "field": "taxonomy_db",
            "path": str(tax_path),
            "status": tax_status,
            "version": "",
            "source_url": "https://www.drive5.com/sintax/",
            "checksum": "",
            "command": [],
            "ready_check": "sintax_fasta_valid",
            "directory_file_count": 0,
            "directory_size_bytes": tax_path.stat().st_size if tax_path.exists() else 0,
            "message": (
                f"Taxonomy DB ready: {tax_entries} SINTAX-annotated sequences."
                if tax_status == "ok"
                else "Taxonomy DB missing. Run: abi setup-resources --type amplicon_16s"
                if tax_status == "missing"
                else "Taxonomy DB exists but contains no valid SINTAX-annotated sequences."
            ),
        }
    )

    # Filter out generic taxonomy_db row (it was a NOT_CONFIGURED placeholder)
    rows = [r for r in rows if r.get("resource_id") != "taxonomy_db" or r.get("tool_id")]
    return rows


def _setup_amplicon_16s(
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    mock: bool = False,
) -> List[Dict[str, Any]]:
    """Set up amplicon_16s resources: taxonomy database for SINTAX classification.

    Strategy:
    1. --mock: generate a tiny synthetic DB instantly (for testing)
    2. Default: download RDP 16S training set (~50 MB) from drive5.com
    3. Fallback: if download fails, generate synthetic DB
    """
    import subprocess

    from abi.config import PROJECT_ROOT

    if resource_ids and "taxonomy_db" not in resource_ids:
        return []

    resources = config.get("resources", {})
    if not isinstance(resources, Mapping):
        resources = {}

    outdir = Path(str(config.get("outdir", str(PROJECT_ROOT / "data" / "taxonomy"))))
    if "taxonomy" not in outdir.parts:
        outdir = outdir / "taxonomy"
    if not dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    if mock:
        generate_script = PROJECT_ROOT / "scripts" / "generate_synthetic_taxonomy.py"
        tax_fasta = outdir / "synthetic_sintax.fa"
        if not dry_run:
            subprocess.run(
                ["python", str(generate_script), "--output", str(tax_fasta), "--entries", "50"],
                capture_output=True,
                text=True,
                check=False,
            )
        return [
            {
                "resource_id": "taxonomy_db",
                "tool_id": "vsearch_taxonomy",
                "field": "taxonomy_db",
                "path": str(tax_fasta),
                "status": "planned" if dry_run else ("ok" if tax_fasta.exists() else "error"),
                "version": "synthetic_test_only",
                "source_url": "generated by scripts/generate_synthetic_taxonomy.py",
                "checksum": "",
                "command": ["python", str(generate_script)],
                "ready_check": "sintax_fasta_valid",
                "directory_file_count": 0,
                "directory_size_bytes": 0,
                "message": (
                    "Would generate a synthetic taxonomy DB for testing."
                    if dry_run
                    else "Synthetic taxonomy DB generated for TESTING only. "
                    "For real analysis, run without --mock to download the RDP training set."
                ),
            }
        ]

    # Primary: download RDP training set
    download_script = PROJECT_ROOT / "scripts" / "download_rdp_sintax.sh"
    tax_fasta = outdir / "rdp_16s_v16.fa"

    if tax_fasta.exists():
        status = "ok"
        message = f"RDP taxonomy DB already exists: {tax_fasta}"
    elif dry_run:
        status = "planned"
        message = "Would download RDP 16S training set from drive5.com (~50 MB)"
    elif download_script.exists():
        cmd = ["bash", str(download_script), "--output", str(outdir)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=_resource_timeout(config),
            )
            if result.returncode == 0 and tax_fasta.exists():
                status = "ok"
                message = "RDP 16S training set downloaded successfully."
            else:
                status = "fallback"
                message = "RDP download failed; generating synthetic fallback."
                _generate_synthetic_fallback(outdir)
        except (subprocess.TimeoutExpired, OSError):
            status = "fallback"
            message = "RDP download timed out; generated synthetic fallback."
            _generate_synthetic_fallback(outdir)
    else:
        status = "error"
        message = f"Download script not found: {download_script}"

    return [
        {
            "resource_id": "taxonomy_db",
            "tool_id": "vsearch_taxonomy",
            "field": "taxonomy_db",
            "path": str(tax_fasta),
            "status": status,
            "version": "",
            "source_url": "https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz",
            "checksum": "",
            "command": ["bash", str(download_script)] if download_script.exists() else [],
            "ready_check": "sintax_fasta_valid",
            "directory_file_count": 0,
            "directory_size_bytes": 0,
            "message": message,
        }
    ]


def _generate_synthetic_fallback(outdir: Path) -> None:
    """Generate a synthetic taxonomy DB when RDP download fails."""
    import subprocess

    from abi.config import PROJECT_ROOT

    generate_script = PROJECT_ROOT / "scripts" / "generate_synthetic_taxonomy.py"
    if generate_script.exists():
        subprocess.run(
            [
                "python",
                str(generate_script),
                "--output",
                str(outdir / "synthetic_sintax.fa"),
                "--entries",
                "100",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
