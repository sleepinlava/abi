"""Provenance writer — reproducibility metadata for scientific figures.

Every figure must have a provenance record that includes:
- Input data SHA256 hash
- FigureSpec (resolved)
- Software versions (ABI, Python, matplotlib, pandas, numpy)
- Renderer backend
- Theme and palette names
- Statistical test metadata
- Timestamp
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from abi.sciplot.schema.figure_spec import FigureSpec


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def _get_package_version(pkg_name: str) -> Optional[str]:
    """Get the installed version of a package."""
    try:
        mod = __import__(pkg_name, fromlist=["__version__"])
        return getattr(mod, "__version__", None) or getattr(mod, "version", None)
    except ImportError:
        return None


def write_provenance(
    spec: FigureSpec, output_dir: Path, extra_metadata: Optional[Dict[str, Any]] = None
) -> Path:
    """Write provenance.json for a rendered figure.

    Args:
        spec: The validated FigureSpec used for rendering.
        output_dir: Directory to write provenance.json into.
        extra_metadata: Additional metadata to include.

    Returns:
        Path to the written provenance.json file.
    """
    # Compute input hash
    input_sha256 = ""
    if spec.data.table.exists():
        input_sha256 = _sha256_file(spec.data.table)

    # Collect package versions
    packages: Dict[str, Optional[str]] = {
        "matplotlib": _get_package_version("matplotlib"),
        "pandas": _get_package_version("pandas"),
        "numpy": _get_package_version("numpy"),
        "seaborn": _get_package_version("seaborn"),
        "pydantic": _get_package_version("pydantic"),
    }

    record: Dict[str, Any] = {
        "figure_id": spec.figure_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "abi_version": spec.provenance.abi_version or "unknown",
        "skill": "abi_sciplot",
        "skill_version": "0.1.0",
        "renderer": "matplotlib",
        "renderer_version": _get_package_version("matplotlib") or "unknown",
        "python_version": sys.version.split()[0],
        "input_table": str(spec.data.table),
        "input_sha256": input_sha256,
        "theme": spec.style.theme,
        "palette": spec.style.palette,
        "statistical_test": spec.statistics.test if spec.statistics else None,
        "multiple_testing_correction": spec.statistics.correction if spec.statistics else None,
        "packages": {k: v or "unknown" for k, v in packages.items()},
    }

    if extra_metadata:
        record.update(extra_metadata)

    output_dir.mkdir(parents=True, exist_ok=True)
    prov_path = output_dir / f"{spec.export.basename}.provenance.json"
    prov_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return prov_path
