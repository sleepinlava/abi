"""ABI resource checking and setup orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from abi.errors import ABIError
from abi.plugins import get_plugin
from abi.plugins.metagenomic_plasmid._engine.resources import (
    check_resources as check_autoplasm_resources,
)
from abi.plugins.metagenomic_plasmid._engine.resources import (
    setup_resources as setup_autoplasm_resources,
)

__all__ = ["check_resources", "setup_resources"]

_PLACEHOLDER_MARKERS = ("NOT_CONFIGURED", "TODO", "PLACEHOLDER")


def check_resources(
    *,
    analysis_type: str,
    config: Mapping[str, Any],
    resource_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Check configured resources for an ABI analysis type."""
    if analysis_type == "metagenomic_plasmid":
        return check_autoplasm_resources(config, resource_ids=resource_ids)
    if analysis_type == "rnaseq_expression":
        return _check_rnaseq_expression(config, resource_ids=resource_ids)
    if analysis_type == "amplicon_16s":
        return _check_amplicon_16s(config, resource_ids=resource_ids)
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
    if analysis_type == "metagenomic_plasmid":
        return setup_autoplasm_resources(
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
            mock=mock,
        )
    if analysis_type == "rnaseq_expression":
        return _setup_rnaseq_expression(
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
        )
    if analysis_type == "amplicon_16s":
        return _setup_amplicon_16s(
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


    rows = _check_generic_resources(
        "rnaseq_expression", config, resource_ids=resource_ids
    )

    # Check DESeq2 availability via Rscript
    deseq2_status = "not_installed"
    deseq2_version = ""
    rscript = os.environ.get("ABI_RSCRIPT_PATH", "Rscript")

    try:
        result = subprocess.run(
            [
                rscript, "--no-save", "-e",
                'if (requireNamespace("DESeq2", quietly=TRUE)) '
                'cat("OK:", as.character(packageVersion("DESeq2")))',
            ],
            capture_output=True, text=True, check=False, timeout=30,
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
                f"DESeq2 {deseq2_version} found." if deseq2_status == "ok"
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

    setup_script = PROJECT_ROOT / "scripts" / "setup_rnaseq_env.sh"
    if not setup_script.exists():
        raise ABIError(
            "setup_rnaseq_env.sh not found. "
            "Reinstall ABI or create the rnaseq environment manually."
        )

    mamba_root = str(
        config.get("mamba_root")
        or os.environ.get("MAMBA_ROOT")
        or str(PROJECT_ROOT / ".mamba")
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
            "message": (
                f"DESeq2 installed: {deseq2_installed}. "
                f"Env path: {rnaseq_env}. {message}"
            ),
        }
    )

    # Also run generic resource checks for genomes, annotations, etc.
    generic_rows = _check_generic_resources(
        "rnaseq_expression", config, resource_ids=resource_ids
    )
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
    rows = _check_generic_resources(
        "amplicon_16s", config, resource_ids=resource_ids
    )

    # Check taxonomy DB
    taxonomy_db = config.get("resources", {}).get(
        "taxonomy_db", "TAXONOMY_DB_NOT_CONFIGURED"
    )
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

    resources = config.get("resources", {})
    if not isinstance(resources, Mapping):
        resources = {}

    outdir = Path(str(config.get("outdir", str(PROJECT_ROOT / "data" / "taxonomy"))))
    if "taxonomy" not in outdir.parts:
        outdir = outdir / "taxonomy"
    outdir.mkdir(parents=True, exist_ok=True)

    if mock:
        generate_script = PROJECT_ROOT / "scripts" / "generate_synthetic_taxonomy.py"
        tax_fasta = outdir / "synthetic_sintax.fa"
        if not dry_run:
            subprocess.run(
                ["python", str(generate_script), "--output", str(tax_fasta), "--entries", "50"],
                capture_output=True, text=True, check=False,
            )
        return [
            {
                "resource_id": "taxonomy_db",
                "tool_id": "vsearch_taxonomy",
                "field": "taxonomy_db",
                "path": str(tax_fasta),
                "status": "ok" if dry_run else ("ok" if tax_fasta.exists() else "error"),
                "version": "synthetic_test_only",
                "source_url": "generated by scripts/generate_synthetic_taxonomy.py",
                "checksum": "",
                "command": ["python", str(generate_script)],
                "ready_check": "sintax_fasta_valid",
                "directory_file_count": 0,
                "directory_size_bytes": 0,
                "message": (
                    "Synthetic taxonomy DB generated for TESTING only. "
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
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
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
            ["python", str(generate_script), "--output", str(outdir / "synthetic_sintax.fa"),
             "--entries", "100"],
            capture_output=True, text=True, check=False,
        )
