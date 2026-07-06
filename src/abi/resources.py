"""ABI resource checking and setup orchestration."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from abi import resource_downloader as _resource_downloader
from abi.errors import ABIError
from abi.interfaces import ABIResourcePlugin
from abi.plugins import get_plugin
from abi.resource_downloader import DownloadResult, DownloadSpec, ResourceDownloader
from abi.timeouts import DEFAULT_RESOURCE_TIMEOUT_SECONDS, timeout_from_env_or_value

# Compatibility for the Phase 1 plan's public import path while this module
# remains a single file instead of a package.
__path__ = []  # type: ignore[var-annotated]
sys.modules.setdefault(__name__ + ".downloader", _resource_downloader)

__all__ = ["check_resources", "setup_resources", "apply_resource_overrides"]

_PLACEHOLDER_MARKERS = ("NOT_CONFIGURED", "TODO", "PLACEHOLDER")
_AMRFINDERPLUS_PROTEIN_INDEX_SUFFIXES = (".phr", ".pin", ".psq")
_AMRFINDERPLUS_SOURCE_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/"
    "AMRFinderPlus/database/"
)


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
        rows = plugin.setup_resources(
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
            mock=mock,
        )
        return _mark_mock_mode(rows, mock=mock)
    if not dry_run and not mock:
        raise ABIError(
            f"Resource setup is not implemented for analysis type {analysis_type!r}. "
            "Use --dry-run to inspect the resource plan or configure paths manually."
        )
    rows = _check_generic_resources(analysis_type, config, resource_ids=resource_ids)
    planned = []
    for row in rows:
        planned_row = dict(row)
        planned_row["mock"] = mock
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


def _mark_mock_mode(rows: Sequence[Mapping[str, Any]], *, mock: bool) -> List[Dict[str, Any]]:
    """Return resource setup rows with an explicit mock-mode marker."""
    return [dict(row, mock=mock) for row in rows]


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
    multi-environment installation. Automatically choosing or partially
    downloading such resources would create a misleading runnable state.
    """
    rows = _check_generic_resources(analysis_type, config, resource_ids=resource_ids)
    downloader = ResourceDownloader(Path(), dry_run=dry_run, mock=mock)
    planned: List[Dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        current["mock"] = mock
        target = _configured_or_default_resource_path(config, str(current["resource_id"]))
        current["path"] = str(target)
        if dry_run:
            current["status"] = "planned"
            current["message"] = (
                "Would prepare a mock resource directory for smoke testing."
                if mock
                else "Would verify this manually provisioned resource; no implicit "
                "database or environment selection is performed."
            )
        elif current["status"] == "ok":
            current["message"] = "Configured resource exists."
        elif mock:
            downloader._mock_resource(
                DownloadSpec(resource_id=str(current["resource_id"])), target
            )
            current["status"] = "ok"
            current["message"] = "Mock resource directory prepared."
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
    if isinstance(value, Mapping):
        value = value.get("path")
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


def _amrfinderplus_has_protein_index(path: Path) -> bool:
    return all(
        (path / f"AMRProt.fa{suffix}").exists()
        for suffix in _AMRFINDERPLUS_PROTEIN_INDEX_SUFFIXES
    )


def _amrfinderplus_runtime_dir(path: Path) -> Path:
    """Return the AMRFinderPlus version directory used at runtime.

    ``amrfinder_update`` stores files under a versioned directory and maintains
    ``latest``. AMRFinderPlus expects ``--database`` to point at that version
    directory, not the parent that contains the ready sentinel.
    """
    if _amrfinderplus_has_protein_index(path):
        return path
    latest = path / "latest"
    if latest.exists() and _amrfinderplus_has_protein_index(latest):
        return latest
    return path


def _amrfinderplus_row(
    result: DownloadResult,
    *,
    mock: bool,
) -> Dict[str, Any]:
    return _download_result_to_row(
        result,
        tool_id="amrfinderplus",
        field="amrfinder_db",
        source_url=_AMRFINDERPLUS_SOURCE_URL,
        ready_check="amrfinderplus_blast_index",
        mock=mock,
    )


def _setup_wgs_bacteria(
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]],
    dry_run: bool,
    mock: bool,
) -> List[Dict[str, Any]]:
    """Prepare the AMRFinderPlus database used by the WGS DAG.

    Uses ResourceDownloader for atomic, idempotent resource management.
    """
    if resource_ids and "amrfinder_db" not in resource_ids:
        return []
    target = _configured_or_default_resource_path(config, "amrfinder_db")
    runtime_target = _amrfinderplus_runtime_dir(target)
    command = ["amrfinder_update", "--database", str(target)]
    timeout = _resource_timeout(config)

    # Existing AMRFinderPlus databases are only usable when both the ready sentinel
    # and the runtime protein BLAST index are present.  amrfinder_update stores the
    # index under a versioned/latest subdirectory, while the sentinel lives on the
    # configured parent directory.
    legacy_sentinel = target / ".abi_ready"
    if not dry_run and not mock and target.exists() and any(target.iterdir()):
        sentinel = target / ResourceDownloader.SENTINEL
        has_sentinel = sentinel.exists() or legacy_sentinel.exists()
        if has_sentinel and _amrfinderplus_has_protein_index(runtime_target):
            return [
                _amrfinderplus_row(
                    DownloadResult(
                        resource_id="amrfinder_db",
                        path=runtime_target,
                        status="ok",
                        command=command,
                        message="AMRFinderPlus protein BLAST index found.",
                    ),
                    mock=mock,
                )
            ]
        message = (
            "Existing AMRFinderPlus directory has a ready sentinel but lacks "
            "AMRProt.fa BLAST index files (.phr, .pin, .psq); rerun setup."
            if has_sentinel
            else "Existing AMRFinderPlus directory is non-empty but lacks the ready "
            "sentinel; a prior update may have failed. Remove it or rerun setup."
        )
        return [
            _amrfinderplus_row(
                DownloadResult(
                    resource_id="amrfinder_db",
                    path=target,
                    status="incomplete",
                    command=command,
                    message=message,
                ),
                mock=mock,
            )
        ]

    spec = DownloadSpec(
        resource_id="amrfinder_db",
        tool_id="amrfinderplus",
        command=command,
        atomic=False,
        destination=target,
        display_name="AMRFinderPlus database",
        timeout_seconds=timeout or 3600.0,
    )
    downloader = ResourceDownloader(Path(), dry_run=dry_run, mock=mock)
    result = downloader.ensure(spec)
    if not dry_run and not mock and result.status == "ok":
        runtime_target = _amrfinderplus_runtime_dir(target)
        if _amrfinderplus_has_protein_index(runtime_target):
            result = DownloadResult(
                resource_id=result.resource_id,
                path=runtime_target,
                status="ok",
                version=result.version,
                checksum=result.checksum,
                downloaded_at=result.downloaded_at,
                command=result.command,
                message=result.message,
            )
        else:
            result = DownloadResult(
                resource_id=result.resource_id,
                path=target,
                status="incomplete",
                version=result.version,
                checksum=result.checksum,
                command=result.command,
                message=(
                    "AMRFinderPlus setup completed but AMRProt.fa BLAST index files "
                    "(.phr, .pin, .psq) were not found; rerun setup."
                ),
            )

    return [_amrfinderplus_row(result, mock=mock)]


def _setup_reference_resources(
    analysis_type: str,
    config: Mapping[str, Any],
    *,
    resource_ids: Optional[Sequence[str]],
    dry_run: bool,
    mock: bool,
) -> List[Dict[str, Any]]:
    """Plan or mock organism-specific reference resources.

    Genome indices and annotations cannot be downloaded automatically ---
    the user must pick an organism/genome build. Mock mode uses
    ResourceDownloader for consistent mock resource creation.
    """
    selected = set(resource_ids or [])
    downloader = ResourceDownloader(Path(), dry_run=dry_run, mock=mock)
    rows: List[Dict[str, Any]] = []
    for resource_id in ("genome_index", "annotation_gtf"):
        if selected and resource_id not in selected:
            continue
        target = _configured_or_default_resource_path(config, resource_id)
        if dry_run:
            status = "planned"
            message = (
                "Would prepare a mock reference resource for smoke testing."
                if mock
                else "Select an organism/genome build and configure this reference path."
            )
        elif mock:
            if resource_id == "genome_index":
                downloader._mock_resource(DownloadSpec(resource_id=resource_id), target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    'chrMock\tABI\tgene\t1\t4\t.\t+\t.\tgene_id "MOCK1";\n',
                    encoding="utf-8",
                )
            status = "ok"
            message = "Mock reference resource prepared."
        elif target.exists():
            status = "ok"
            message = "Configured reference resource exists."
        else:
            status = "manual_required"
            message = (
                "Automatic download requires an organism/genome build choice; "
                "configure the reference path explicitly."
            )
        rows.append({
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
            "mock": mock,
        })
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
    if not path.exists():
        return "missing"
    if path.is_dir() and not any(path.iterdir()):
        return "incomplete"
    return "ok"


def _generic_resource_message(status: str) -> str:
    if status == "ok":
        return "Configured resource path exists."
    if status == "missing":
        return "Configured resource path does not exist."
    if status == "incomplete":
        return "Configured resource directory is empty; database setup may be incomplete."
    return "Resource path is not configured."


def _directory_file_count(path: Path) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    return sum(1 for child in path.rglob("*") if child.is_file())


def _download_result_to_row(
    result: DownloadResult,
    *,
    tool_id: str = "",
    field: str = "",
    source_url: str = "",
    ready_check: str = "sentinel",
    mock: bool = False,
) -> dict[str, Any]:
    """Convert a DownloadResult to the resource row dict format."""
    file_count = result.file_count or (
        sum(1 for _ in result.path.rglob("*") if _.is_file()) if result.path.is_dir() else 0
    )
    size_bytes = result.size_bytes or (
        sum(f.stat().st_size for f in result.path.rglob("*") if f.is_file())
        if result.path.is_dir()
        else 0
    )
    return {
        "resource_id": result.resource_id,
        "tool_id": tool_id,
        "field": field or result.resource_id,
        "path": str(result.path),
        "status": result.status,
        "version": result.version,
        "source_url": source_url,
        "checksum": result.checksum,
        "command": list(result.command),
        "ready_check": ready_check,
        "directory_file_count": file_count,
        "directory_size_bytes": size_bytes,
        "message": result.message,
        "mock": mock,
    }


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

    # Check DESeq2 availability via Rscript. Prefer ABI's rnaseq env so checks
    # match the environment used by the registered rnaseq_expression tools.
    from abi.config import resolved_mamba_root

    deseq2_status = "not_installed"
    deseq2_version = ""
    configured_rscript = os.environ.get("ABI_RSCRIPT_PATH")
    env_rscript = resolved_mamba_root() / "envs" / "rnaseq" / "bin" / "Rscript"
    rscript = configured_rscript or (str(env_rscript) if env_rscript.exists() else "Rscript")

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
    mock: bool = False,
) -> List[Dict[str, Any]]:
    """Set up the rnaseq_expression conda environment and R packages.

    Runs ``scripts/setup_rnaseq_env.sh`` which creates the ``rnaseq`` conda
    environment with fastp, STAR, featureCounts, and R, then installs DESeq2
    from Bioconductor.
    """
    import os
    import subprocess

    from abi.config import PROJECT_ROOT, resolved_mamba_root

    selected = set(resource_ids or [])
    if selected and "rnaseq_environment" not in selected:
        return _mark_mock_mode(
            _check_generic_resources("rnaseq_expression", config, resource_ids=resource_ids),
            mock=mock,
        )

    setup_script = PROJECT_ROOT / "scripts" / "setup_rnaseq_env.sh"
    if not setup_script.exists():
        raise ABIError(
            "setup_rnaseq_env.sh not found. "
            "Reinstall ABI or create the rnaseq environment manually."
        )

    mamba_root = str(
        config.get("mamba_root")
        or os.environ.get("ABI_MAMBA_ROOT")
        or os.environ.get("AUTOPLASM_MAMBA_ROOT")
        or os.environ.get("MAMBA_ROOT")
        or resolved_mamba_root()
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
            "mock": mock,
        }
    )

    # Also run generic resource checks for genomes, annotations, etc.
    generic_rows = _check_generic_resources("rnaseq_expression", config, resource_ids=resource_ids)
    for gr in generic_rows:
        if gr["resource_id"] != "rnaseq_environment":
            rows.append(dict(gr, mock=mock))

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
    resources = config.get("resources", {})
    taxonomy_db = (
        resources.get("taxonomy_db", "TAXONOMY_DB_NOT_CONFIGURED")
        if isinstance(resources, Mapping)
        else "TAXONOMY_DB_NOT_CONFIGURED"
    )
    if isinstance(taxonomy_db, Mapping):
        taxonomy_db = taxonomy_db.get("path", "TAXONOMY_DB_NOT_CONFIGURED")
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

    Uses ResourceDownloader for mock mode; subprocess for real download
    (the RDP download script writes to a specific output path).
    Falls back to synthetic taxonomy if RDP download fails.
    """
    from abi.config import PROJECT_ROOT

    if resource_ids and "taxonomy_db" not in resource_ids:
        return []

    outdir = Path(str(config.get("outdir", str(PROJECT_ROOT / "data" / "taxonomy"))))
    if "taxonomy" not in outdir.parts:
        outdir = outdir / "taxonomy"
    if not dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

    download_script = PROJECT_ROOT / "scripts" / "download_rdp_sintax.sh"
    tax_fasta = outdir / "rdp_16s_v16.fa"
    synthetic_fasta = outdir / "synthetic_sintax.fa"
    timeout = _resource_timeout(config)

    # Mock mode creates a tiny valid SINTAX FASTA and a unified resource sentinel.
    if mock:
        command = [
            "python",
            str(PROJECT_ROOT / "scripts" / "generate_synthetic_taxonomy.py"),
            "--output",
            str(tax_fasta),
            "--entries",
            "1",
        ]
        if dry_run:
            result = DownloadResult(
                resource_id="taxonomy_db",
                path=tax_fasta,
                status="planned",
                version="synthetic_test_only",
                command=command,
                message="Would generate a synthetic taxonomy DB for testing.",
            )
        else:
            import shutil

            if tax_fasta.exists() and tax_fasta.is_dir():
                shutil.rmtree(tax_fasta)
            tax_fasta.parent.mkdir(parents=True, exist_ok=True)
            tax_fasta.write_text(
                ">mock_taxon_1;tax=d:Bacteria,p:Firmicutes,c:Bacilli\n"
                "ACGTACGTACGTACGTACGTACGTACGTACGT\n",
                encoding="utf-8",
            )
            ResourceDownloader(Path(), mock=True).ensure(
                DownloadSpec(
                    resource_id="taxonomy_db",
                    tool_id="vsearch_taxonomy",
                    destination=outdir,
                    version="synthetic_test_only",
                )
            )
            result = DownloadResult(
                resource_id="taxonomy_db",
                path=tax_fasta,
                status="ok",
                version="synthetic_test_only",
                file_count=1,
                size_bytes=tax_fasta.stat().st_size,
                command=command,
                message=(
                    "Synthetic taxonomy DB generated for TESTING only. "
                    "For real analysis, run without --mock to download the RDP training set."
                ),
            )
        return [
            _download_result_to_row(
                result,
                tool_id="vsearch_taxonomy",
                field="taxonomy_db",
                source_url="generated by scripts/generate_synthetic_taxonomy.py",
                ready_check="sintax_fasta_valid",
                mock=True,
            )
        ]

    # Primary: download RDP training set via ResourceDownloader (non-atomic)
    if tax_fasta.exists():
        effective_path = tax_fasta
        status_msg = "ok"
        message = f"RDP taxonomy DB already exists: {tax_fasta}"
        command: list[str] = []
    elif dry_run:
        effective_path = tax_fasta
        status_msg = "planned"
        message = "Would download RDP 16S training set from drive5.com (~50 MB)"
        command = []
    elif download_script.exists():
        downloader = ResourceDownloader(Path(), dry_run=dry_run, mock=False)
        spec = DownloadSpec(
            resource_id="taxonomy_db",
            tool_id="vsearch_taxonomy",
            command=["bash", str(download_script), "--output", str(outdir)],
            atomic=False,
            destination=outdir,
            ready_check="non_empty_dir",
            timeout_seconds=timeout,
            version="rdp_16s_v16",
        )
        result_dl = downloader.ensure(spec)
        if result_dl.status == "ok":
            effective_path = tax_fasta
            status_msg = "ok"
            message = "RDP 16S training set downloaded successfully."
            command = result_dl.command
        else:
            effective_path = synthetic_fasta
            status_msg = "fallback"
            message = f"RDP download failed: {result_dl.message}. Generating synthetic fallback."
            command = result_dl.command
            _generate_synthetic_fallback(outdir)
    else:
        effective_path = tax_fasta
        status_msg = "error"
        message = f"Download script not found: {download_script}"
        command = []

    if status_msg == "fallback" and not synthetic_fasta.exists():
        status_msg = "error"
        message = (
            "RDP download failed and synthetic fallback generation did not "
            f"produce {synthetic_fasta}."
        )

    result = DownloadResult(
        resource_id="taxonomy_db",
        path=effective_path,
        status=status_msg,
        message=message,
        command=command,
    )
    return [
        _download_result_to_row(
            result,
            tool_id="vsearch_taxonomy",
            field="taxonomy_db",
            source_url="https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz",
            ready_check="sintax_fasta_valid",
            mock=mock,
        )
    ]


def _generate_synthetic_fallback(outdir: Path) -> bool:
    """Generate a synthetic taxonomy DB when RDP download fails.

    Returns True if the synthetic FASTA was produced, False otherwise so the
    caller can report an error instead of silently pointing at a missing file.
    """
    import subprocess

    from abi.config import PROJECT_ROOT

    generate_script = PROJECT_ROOT / "scripts" / "generate_synthetic_taxonomy.py"
    synthetic_path = outdir / "synthetic_sintax.fa"
    if not generate_script.exists():
        return False
    result = subprocess.run(
        [
            "python",
            str(generate_script),
            "--output",
            str(synthetic_path),
            "--entries",
            "100",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and synthetic_path.exists()


def apply_resource_overrides(config: Dict[str, Any], overrides: Sequence[str]) -> None:
    """Apply ``--resource id=path`` overrides to a config dict in-place.

    Handles ``id=path`` syntax: sets ``config.resources.<id>`` to ``<path>``.
    For the full ``id:field=path`` syntax, use the plugin's version directly.
    """
    resources = config.setdefault("resources", {})
    if not isinstance(resources, Mapping):
        resources = {}
        config["resources"] = resources
    for item in overrides:
        key, _, path = item.partition("=")
        key = key.strip()
        path = path.strip()
        if not key or not path:
            raise ABIError(f"Invalid --resource override (expected id=path): {item!r}")
        resource_id = key
        block = resources.setdefault(resource_id, {})
        if not isinstance(block, dict):
            block = {}
            resources[resource_id] = block
        block["path"] = path
