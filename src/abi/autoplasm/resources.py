"""Resource and example dataset management for AutoPlasm."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from abi.autoplasm.config import PROJECT_ROOT, resolved_mamba_root, write_yaml
from abi.autoplasm.filesystem import ensure_directory
from abi.autoplasm.schemas import AutoPlasmError
from abi.autoplasm.skills.registry import ToolRegistry
from abi.autoplasm.timeouts import (
    DEFAULT_RESOURCE_TIMEOUT_SECONDS,
    mapping_block,
    timeout_from_env_or_value,
)


class ResourceError(AutoPlasmError):
    """Raised when an AutoPlasm database or example resource cannot be prepared."""


@dataclass
class ResourceSpec:
    resource_id: str
    tool_id: str
    field: str
    env_name: str
    executable: str
    default_subdir: str
    source_url: str
    command_template: List[str]
    version: str = "latest"
    auto_setup: bool = True


@dataclass
class ResourceStatus:
    resource_id: str
    tool_id: str
    field: str
    path: str
    status: str
    version: str
    source_url: str
    checksum: str = ""
    command: List[str] | None = None
    ready_check: str = ""
    directory_file_count: int = 0
    directory_size_bytes: int = 0
    message: str = ""
    last_checked_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


EXAMPLE_ACCESSIONS = {
    "plasmid_refseq_smoke": ["NC_002127.1", "NC_011977.1", "NC_002483.1"],
}
PLASMIDFINDER_DB_URL = "https://bitbucket.org/genomicepidemiology/plasmidfinder_db.git"
RESOURCE_READY_SENTINEL = ".autoplasm_resource_ready"
MAX_DIRECTORY_SUMMARY_ENTRIES = 100_000
ResourceProgressCallback = Callable[[str, str, str], None]


def default_resource_specs(config: Mapping[str, Any]) -> List[ResourceSpec]:
    root = resource_root(config)
    return [
        ResourceSpec(
            resource_id="genomad",
            tool_id="genomad",
            field="database",
            env_name="autoplasm-plasmid-detect",
            executable="genomad",
            default_subdir="genomad",
            source_url="https://portal.nersc.gov/genomad/",
            command_template=["genomad", "download-database", str(root / "genomad")],
        ),
        ResourceSpec(
            resource_id="bakta",
            tool_id="bakta",
            field="database",
            env_name="autoplasm-annotation",
            executable="bakta_db",
            default_subdir="bakta",
            source_url="https://bakta.readthedocs.io/en/latest/cli/database.html",
            command_template=[
                "bakta_db",
                "download",
                "--output",
                str(root / "bakta"),
                "--type",
                str(_resource_block(config, "bakta").get("type", "light")),
            ],
            version=str(_resource_block(config, "bakta").get("version", "light")),
        ),
        ResourceSpec(
            resource_id="mob_suite",
            tool_id="mob_suite",
            field="database",
            env_name="autoplasm-annotation",
            executable="mob_init",
            default_subdir="mob_suite",
            source_url="https://github.com/phac-nml/mob-suite",
            command_template=[
                "mob_init",
                "--database_directory",
                str(root / "mob_suite"),
            ],
        ),
        ResourceSpec(
            resource_id="plasmidfinder",
            tool_id="plasmidfinder",
            field="database",
            env_name="autoplasm-annotation",
            executable="git",
            default_subdir="plasmidfinder_db",
            source_url=PLASMIDFINDER_DB_URL,
            command_template=[
                "git",
                "clone",
                PLASMIDFINDER_DB_URL,
                str(root / "plasmidfinder_db"),
            ],
        ),
        ResourceSpec(
            resource_id="metaphlan",
            tool_id="metaphlan",
            field="database",
            env_name="autoplasm-stats",
            executable="metaphlan",
            default_subdir="metaphlan",
            source_url="https://github.com/biobakery/MetaPhlAn",
            command_template=[
                "metaphlan",
                "--install",
                "--db_dir",
                str(root / "metaphlan"),
            ],
            auto_setup=False,
        ),
    ]


def resource_root(config: Mapping[str, Any]) -> Path:
    resources = config.get("resources", {})
    root = resources.get("root") if isinstance(resources, Mapping) else None
    return Path(str(root or PROJECT_ROOT / "resources" / "autoplasm"))


def check_resources(
    config: Mapping[str, Any],
    *,
    resource_ids: Sequence[str] | None = None,
) -> List[Dict[str, Any]]:
    ids = set(resource_ids or [])
    rows = []
    for spec in default_resource_specs(config):
        if ids and spec.resource_id not in ids:
            continue
        rows.append(_status_for_spec(config, spec).to_dict())
    return rows


def setup_resources(
    config: Mapping[str, Any],
    *,
    resource_ids: Sequence[str] | None = None,
    dry_run: bool = False,
    mock: bool = False,
    progress_callback: ResourceProgressCallback | None = None,
) -> List[Dict[str, Any]]:
    root = resource_root(config)
    if not dry_run:
        ensure_directory(root, label="Resource root directory")
    ids = set(resource_ids or [])
    statuses: List[ResourceStatus] = []
    for spec in default_resource_specs(config):
        if ids and spec.resource_id not in ids:
            continue
        if not ids and not spec.auto_setup:
            continue
        _notify_progress(progress_callback, "start", spec.resource_id, "preparing")
        path = _configured_resource_path(config, spec)
        command = _resolved_resource_command(config, spec, path)
        if dry_run:
            status = _status_for_spec(
                config,
                spec,
                status_override="planned",
                command=command,
                message="Download was planned but not executed.",
            )
            statuses.append(status)
            _notify_progress(progress_callback, "finish", spec.resource_id, status.status)
            continue
        if mock:
            ensure_directory(path, label=f"Resource directory for {spec.resource_id}")
            (path / ".autoplasm_mock_resource").write_text(
                f"{spec.resource_id}\n", encoding="utf-8"
            )
            _write_ready_sentinel(path, spec)
            status = _status_for_spec(
                config,
                spec,
                status_override="ok",
                command=command,
                message="Mock resource prepared.",
            )
            statuses.append(status)
            _notify_progress(progress_callback, "finish", spec.resource_id, status.status)
            continue
        if _resource_path_ready(path, spec):
            status = _status_for_spec(
                config,
                spec,
                status_override="ok",
                command=command,
                message="Existing database found; download skipped.",
            )
            statuses.append(status)
            _notify_progress(progress_callback, "finish", spec.resource_id, status.status)
            continue
        if _resource_path_blocks_download(path):
            status = _status_for_spec(
                config,
                spec,
                status_override="incomplete",
                command=command,
                message=(
                    "Existing resource path is not a complete database; download skipped "
                    "to avoid overwriting. Remove it or configure another path before rerun."
                ),
            )
            statuses.append(status)
            _notify_progress(progress_callback, "finish", spec.resource_id, status.status)
            continue
        try:
            _notify_progress(progress_callback, "download", spec.resource_id, "downloading")
            _prepare_resource_download_target(path)
            _run_resource_command(config, spec, command)
            if spec.resource_id == "plasmidfinder":
                _run_plasmidfinder_install(config, path)
            _write_ready_sentinel(path, spec)
            status = _status_for_spec(
                config,
                spec,
                status_override="ok" if _resource_path_ready(path, spec) else "partial",
                command=command,
                message="Resource command completed.",
            )
            statuses.append(status)
            _notify_progress(progress_callback, "finish", spec.resource_id, status.status)
        except MemoryError:
            raise
        except Exception as exc:  # pragma: no cover - external command boundary
            status = _status_for_spec(
                config,
                spec,
                status_override="failed",
                command=command,
                message=str(exc),
            )
            statuses.append(status)
            _notify_progress(progress_callback, "finish", spec.resource_id, status.status)
    if not dry_run:
        manifest_path = root / "resources.json"
        write_resource_manifest(statuses, manifest_path)
    return [status.to_dict() for status in statuses]


def write_resource_manifest(statuses: Iterable[ResourceStatus], path: str | Path) -> Path:
    manifest_path = Path(path)
    ensure_directory(manifest_path.parent, label="Resource manifest directory")
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "resources": [status.to_dict() for status in statuses],
    }
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def write_resources_provenance(config: Mapping[str, Any], outdir: str | Path) -> Path:
    path = Path(outdir) / "provenance" / "resources.json"
    statuses = [ResourceStatus(**row) for row in check_resources(config)]
    return write_resource_manifest(statuses, path)


def write_environment_snapshot(
    config: Mapping[str, Any],
    registry: ToolRegistry,
    path: str | Path,
) -> Path:
    envs = []
    mamba_root = resolved_mamba_root()
    for tool in registry.list_tools():
        env_name = str(tool.get("env_name", ""))
        executable = str(tool.get("executable", ""))
        executable_path = mamba_root / "envs" / env_name / "bin" / executable
        envs.append(
            {
                "tool_id": tool.get("id"),
                "env_name": env_name,
                "executable": executable,
                "executable_path": str(executable_path),
                "executable_exists": executable_path.exists(),
            }
        )
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mamba_root": str(mamba_root),
        "profile": config.get("profile", ""),
        "environments": envs,
    }
    snapshot_path = Path(path)
    write_yaml(data, snapshot_path)
    return snapshot_path


def fetch_example_dataset(
    dataset: str,
    outdir: str | Path,
    *,
    mock: bool = False,
) -> Dict[str, Any]:
    if dataset not in EXAMPLE_ACCESSIONS:
        raise ResourceError(f"Unsupported example dataset: {dataset}")
    output_dir = ensure_directory(outdir, label="Example dataset output directory")
    rows = []
    files = []
    for accession in EXAMPLE_ACCESSIONS[dataset]:
        url = _efetch_url(accession)
        fasta_path = output_dir / f"{accession}.fasta"
        if mock:
            text = f">{accession} mock plasmid sequence\nATGCATGCATGCATGCATGC\n"
            fasta_path.write_text(text, encoding="utf-8")
        else:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
                fasta_path.write_bytes(response.read())
        checksum = sha256_path(fasta_path)
        rows.append(
            {
                "sample_id": accession.replace(".", "_"),
                "group": "public",
                "platform": "assembly",
                "read1": "",
                "read2": "",
                "long_reads": "",
                "assembly": str(fasta_path),
                "technology": "RefSeq",
                "host_reference": "",
                "notes": f"source={url};sha256={checksum}",
            }
        )
        files.append(
            {
                "accession": accession,
                "url": url,
                "path": str(fasta_path),
                "sha256": checksum,
            }
        )
    sample_sheet = output_dir / "sample_sheet.tsv"
    fields = [
        "sample_id",
        "group",
        "platform",
        "read1",
        "read2",
        "long_reads",
        "assembly",
        "technology",
        "host_reference",
        "notes",
    ]
    with sample_sheet.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(str(row[field]) for field in fields) + "\n")
    manifest = output_dir / "dataset_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset": dataset,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "mock": mock,
                "files": files,
                "sample_sheet": str(sample_sheet),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"dataset": dataset, "sample_sheet": sample_sheet, "manifest": manifest, "files": files}


def required_resource_issues(
    config: Mapping[str, Any],
    selected_tools: Iterable[str],
) -> List[str]:
    selected = set(selected_tools)
    issues = []
    for spec in default_resource_specs(config):
        if spec.tool_id not in selected:
            continue
        status = _status_for_spec(config, spec)
        if status.status != "ok":
            issues.append(
                f"{spec.tool_id}.{spec.field} is {status.status}: {status.path}. "
                "Run setup-resources or configure a valid local path."
            )
    return issues


def sha256_path(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _status_for_spec(
    config: Mapping[str, Any],
    spec: ResourceSpec,
    *,
    status_override: str | None = None,
    command: List[str] | None = None,
    message: str = "",
) -> ResourceStatus:
    path = _configured_resource_path(config, spec)
    if status_override:
        status = status_override
    elif _resource_path_ready(path, spec):
        status = "ok"
    else:
        status = "incomplete" if path.exists() else "missing"
    checksum = ""
    if path.is_file():
        checksum = sha256_path(path)
    file_count, size_bytes = _directory_summary(path)
    return ResourceStatus(
        resource_id=spec.resource_id,
        tool_id=spec.tool_id,
        field=spec.field,
        path=str(path),
        status=status,
        version=str(_resource_block(config, spec.resource_id).get("version", spec.version)),
        source_url=str(
            _resource_block(config, spec.resource_id).get("source_url", spec.source_url)
        ),
        checksum=checksum,
        command=command or _resolved_resource_command(config, spec, path),
        ready_check=_resource_ready_check(path, spec),
        directory_file_count=file_count,
        directory_size_bytes=size_bytes,
        message=message,
        last_checked_at=datetime.now().isoformat(timespec="seconds"),
    )


def _configured_resource_path(config: Mapping[str, Any], spec: ResourceSpec) -> Path:
    block = _resource_block(config, spec.resource_id)
    value = block.get(spec.field)
    return Path(str(value or resource_root(config) / spec.default_subdir))


def _resource_block(config: Mapping[str, Any], resource_id: str) -> Mapping[str, Any]:
    resources = config.get("resources", {})
    if not isinstance(resources, Mapping):
        return {}
    block = resources.get(resource_id, {})
    return block if isinstance(block, Mapping) else {}


def _resolved_resource_command(
    config: Mapping[str, Any], spec: ResourceSpec, target_path: Path
) -> List[str]:
    if spec.resource_id == "genomad":
        return ["genomad", "download-database", str(target_path)]
    if spec.resource_id == "bakta":
        db_type = str(_resource_block(config, "bakta").get("type", "light"))
        return ["bakta_db", "download", "--output", str(target_path), "--type", db_type]
    if spec.resource_id == "mob_suite":
        return ["mob_init", "--database_directory", str(target_path)]
    if spec.resource_id == "plasmidfinder":
        source_url = str(
            _resource_block(config, "plasmidfinder").get(
                "source_url",
                PLASMIDFINDER_DB_URL,
            )
        )
        return [
            "git",
            "clone",
            source_url,
            str(target_path),
        ]
    return list(spec.command_template)


def _timeout_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output)


def _resource_timeout_seconds(config: Mapping[str, Any]) -> float | None:
    execution = mapping_block(config, "execution")
    resources = mapping_block(config, "resources")
    value = resources.get("timeout_seconds")
    if value is None:
        value = execution.get("resource_timeout_seconds")
    if value is None:
        value = execution.get("tool_timeout_seconds")
    return timeout_from_env_or_value(
        "AUTOPLASM_RESOURCE_TIMEOUT_SECONDS",
        value,
        default=DEFAULT_RESOURCE_TIMEOUT_SECONDS,
    )


def _raise_on_timeout(
    spec: ResourceSpec,
    timeout_seconds: float | None,
    exc: subprocess.TimeoutExpired,
) -> None:
    stderr = _timeout_output(exc.stderr)
    timeout_text = "configured timeout" if timeout_seconds is None else f"{timeout_seconds:g}s"
    message = f"{spec.resource_id} setup timed out after {timeout_text}"
    details = "\n".join(text for text in [message, stderr.strip()] if text)
    raise ResourceError(details) from exc


def _run_resource_command(
    config: Mapping[str, Any], spec: ResourceSpec, command: List[str]
) -> None:
    executable = command[0]
    resolved = _resolve_executable(config, spec.env_name, executable)
    run_command = [str(resolved), *command[1:]]
    timeout_seconds = _resource_timeout_seconds(config)
    try:
        completed = subprocess.run(
            run_command,
            check=False,
            text=True,
            capture_output=True,
            env=_resource_runtime_env(config, spec.env_name),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        _raise_on_timeout(spec, timeout_seconds, exc)
    if completed.returncode != 0:
        details = "\n".join(
            text for text in [completed.stderr.strip(), completed.stdout.strip()] if text
        )
        raise ResourceError(
            f"{spec.resource_id} setup failed with code {completed.returncode}: {details}"
        )


def _run_plasmidfinder_install(config: Mapping[str, Any], path: Path) -> None:
    install = path / "INSTALL.py"
    if not install.exists():
        return
    python = _resolve_executable(config, "autoplasm-annotation", "python")
    kma_index = _resolve_executable(config, "autoplasm-annotation", "kma_index")
    timeout_seconds = _resource_timeout_seconds(config)
    try:
        completed = subprocess.run(
            [str(python), str(install.resolve()), str(kma_index)],
            check=False,
            cwd=str(path),
            text=True,
            capture_output=True,
            env=_resource_runtime_env(config, "autoplasm-annotation"),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        _raise_on_timeout(
            ResourceSpec(
                resource_id="plasmidfinder",
                tool_id="plasmidfinder",
                field="database",
                env_name="autoplasm-annotation",
                executable="python",
                default_subdir="plasmidfinder_db",
                source_url=PLASMIDFINDER_DB_URL,
                command_template=[],
            ),
            timeout_seconds,
            exc,
        )
    if completed.returncode != 0:
        details = "\n".join(
            text for text in [completed.stderr.strip(), completed.stdout.strip()] if text
        )
        raise ResourceError(
            f"plasmidfinder database INSTALL.py failed with code {completed.returncode}: {details}"
        )


def _resolve_executable(config: Mapping[str, Any], env_name: str, executable: str) -> Path:
    if executable == "git":
        git = shutil.which("git")
        if not git:
            raise ResourceError("git is required to download the PlasmidFinder database")
        return Path(git)
    mamba_root = resolved_mamba_root()
    env_bin = mamba_root / "envs" / env_name / "bin"
    candidate = env_bin / executable
    if candidate.exists():
        return candidate
    resolved = shutil.which(executable, path=str(env_bin))
    if resolved:
        return Path(resolved)
    if config.get("mock_tools"):
        return Path(executable)
    raise ResourceError(f"Executable {executable!r} was not found in {env_bin}")


def _resource_runtime_env(config: Mapping[str, Any], env_name: str) -> Dict[str, str]:
    env = os.environ.copy()
    mamba_root = resolved_mamba_root()
    env_bin = mamba_root / "envs" / env_name / "bin"
    if env_bin.exists():
        env["PATH"] = f"{env_bin}{os.pathsep}{env.get('PATH', '')}"
        env["CONDA_PREFIX"] = str(mamba_root / "envs" / env_name)
        env["MAMBA_ROOT_PREFIX"] = str(mamba_root)
        env.pop("PYTHONPATH", None)
    return env


def _resource_path_ready(path: Path, spec: ResourceSpec) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return True
    if (path / ".lock").exists():
        return False
    if (path / RESOURCE_READY_SENTINEL).exists():
        return True
    if spec.resource_id == "genomad":
        return (path / "genomad_db").exists()
    if spec.resource_id == "mob_suite":
        blast_suffixes = {".nhr", ".nin", ".nsq", ".phr", ".pin", ".psq"}
        return any(file.suffix in blast_suffixes for file in path.glob("*"))
    if spec.resource_id == "plasmidfinder":
        return (path / "config").exists() and any(path.glob("*.fsa"))
    if spec.resource_id == "metaphlan":
        return any(path.glob("mpa_*.pkl")) or any(path.glob("*.bt2l"))
    return path.is_dir() and any(path.iterdir())


def _resource_ready_check(path: Path, spec: ResourceSpec) -> str:
    if not path.exists():
        return "path missing"
    if path.is_file():
        return "resource file exists"
    if (path / ".lock").exists():
        return "lock file present"
    if (path / RESOURCE_READY_SENTINEL).exists():
        return "ready sentinel found"
    if spec.resource_id == "genomad":
        if (path / "genomad_db").exists():
            return "genomad_db directory found"
        return "genomad_db directory missing"
    if spec.resource_id == "mob_suite":
        blast_suffixes = {".nhr", ".nin", ".nsq", ".phr", ".pin", ".psq"}
        if any(file.suffix in blast_suffixes for file in path.glob("*")):
            return "MOB-suite BLAST index found"
        return "MOB-suite BLAST index missing"
    if spec.resource_id == "plasmidfinder":
        if (path / "config").exists() and any(path.glob("*.fsa")):
            return "PlasmidFinder config and fsa files found"
        return "PlasmidFinder config or fsa files missing"
    if spec.resource_id == "metaphlan":
        if any(path.glob("mpa_*.pkl")) or any(path.glob("*.bt2l")):
            return "MetaPhlAn marker database files found"
        return "MetaPhlAn marker database files missing"
    if path.is_dir() and any(path.iterdir()):
        return "non-empty database directory found"
    return "empty directory"


def _directory_summary(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return 1, path.stat().st_size
        except OSError:
            return 1, 0
    count = 0
    size = 0
    for index, child in enumerate(path.rglob("*")):
        if index >= MAX_DIRECTORY_SUMMARY_ENTRIES:
            break
        try:
            if child.is_file():
                count += 1
                size += child.stat().st_size
        except OSError:
            continue
    return count, size


def _resource_path_blocks_download(path: Path) -> bool:
    return path.exists() and not _path_is_empty_directory(path)


def _prepare_resource_download_target(path: Path) -> None:
    if _path_is_empty_directory(path):
        path.rmdir()


def _path_is_empty_directory(path: Path) -> bool:
    return path.is_dir() and not any(path.iterdir())


def _write_ready_sentinel(path: Path, spec: ResourceSpec) -> None:
    if path.is_dir():
        (path / RESOURCE_READY_SENTINEL).write_text(f"{spec.resource_id}\n", encoding="utf-8")


def _notify_progress(
    callback: ResourceProgressCallback | None,
    event: str,
    resource_id: str,
    message: str,
) -> None:
    if callback:
        callback(event, resource_id, message)


def _efetch_url(accession: str) -> str:
    return (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=nuccore&id={accession}&rettype=fasta&retmode=text"
    )
