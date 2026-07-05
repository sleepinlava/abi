
"""Generate lock files for ABI runtime tools, Conda envs, and resources."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from abi.config import PROJECT_ROOT, resolved_mamba_root
from abi.plugins import get_plugin
from abi.resources import check_resources

DEFAULT_ANALYSIS_TYPES = (
    "amplicon_16s",
    "easymetagenome",
    "metagenomic_plasmid",
    "metatranscriptomics",
    "rnaseq_expression",
    "viral_viwrap",
    "wgs_bacteria",
)

PACKAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "amrfinderplus": ("ncbi-amrfinderplus",),
    "build_count_matrix": ("python", "pandas"),
    "conjscan": ("macsyfinder",),
    "deseq2": ("bioconductor-deseq2",),
    "deseq2_plasmid": ("bioconductor-deseq2",),
    "diversity_metrics": ("scikit-bio", "scipy", "pandas"),
    "eggnog_mapper": ("eggnog-mapper",),
    "featurecounts": ("subread",),
    "gplas2": ("gplas2",),
    "hifiasm_meta": ("hifiasm",),
    "hybridspades": ("spades",),
    "humann4": ("humann",),
    "humann_join_tables": ("humann",),
    "humann_regroup_table": ("humann",),
    "humann_renorm_table": ("humann",),
    "humann_split_stratified_table": ("humann",),
    "metaflye": ("flye",),
    "metaspades": ("spades",),
    "mob_typer": ("mob_suite",),
    "phylogeny_mafft": ("mafft",),
    "phylogeny_tree": ("fasttree",),
    "samtools_fastq": ("samtools",),
    "vsearch_denoise": ("vsearch",),
    "vsearch_derep": ("vsearch",),
    "vsearch_mergepairs": ("vsearch",),
    "vsearch_otu": ("vsearch",),
    "vsearch_taxonomy": ("vsearch",),
}


def generate_runtime_locks(
    *,
    output_dir: str | Path,
    prefix: str = "cloud",
    project_root: str | Path | None = None,
    mamba_root: str | Path | None = None,
    resource_root: str | Path | None = None,
    conda_executable: str | Path | None = None,
    include_conda_packages: bool = True,
    analysis_types: Sequence[str] = DEFAULT_ANALYSIS_TYPES,
) -> dict[str, str]:
    """Generate Conda/tool/resource/runtime lock YAML files.

    The lock files are snapshots of the current machine. They do not install or
    download anything; missing tools and resources are recorded as drift/gaps.
    """
    project = Path(project_root or PROJECT_ROOT).resolve()
    mamba = Path(mamba_root or resolved_mamba_root()).resolve()
    resources = Path(resource_root or project / "resources").resolve()
    outdir = Path(output_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    generated_at = _utc_now()
    environment_spec = _load_yaml(project / "environments.yaml")
    conda_lock = build_conda_lock(
        project_root=project,
        mamba_root=mamba,
        environment_spec=environment_spec,
        conda_executable=conda_executable,
        include_packages=include_conda_packages,
        generated_at=generated_at,
    )
    resource_lock = build_resource_lock(
        project_root=project,
        mamba_root=mamba,
        resource_root=resources,
        analysis_types=analysis_types,
        generated_at=generated_at,
    )
    tool_lock = build_tool_lock(
        project_root=project,
        mamba_root=mamba,
        resource_root=resources,
        environment_spec=environment_spec,
        conda_lock=conda_lock,
        resource_lock=resource_lock,
        generated_at=generated_at,
    )
    runtime_lock = build_runtime_summary(
        conda_lock=conda_lock,
        tool_lock=tool_lock,
        resource_lock=resource_lock,
        generated_at=generated_at,
    )

    locks = {
        "conda": conda_lock,
        "tools": tool_lock,
        "resources": resource_lock,
        "runtime": runtime_lock,
    }
    paths: dict[str, str] = {}
    for name, payload in locks.items():
        path = outdir / f"{prefix}.{name}.lock.yaml"
        _write_yaml(path, payload)
        paths[name] = str(path)
    return paths


def build_conda_lock(
    *,
    project_root: Path,
    mamba_root: Path,
    environment_spec: Mapping[str, Any],
    conda_executable: str | Path | None,
    include_packages: bool,
    generated_at: str,
) -> dict[str, Any]:
    declared = environment_spec.get("environments", {})
    declared_envs = set(declared) if isinstance(declared, Mapping) else set()
    env_root = mamba_root / "envs"
    present_envs = {p.name for p in env_root.iterdir() if p.is_dir()} if env_root.is_dir() else set()
    env_names = sorted(declared_envs | present_envs)
    conda = _resolve_conda_executable(conda_executable)

    environments: dict[str, Any] = {}
    for env_name in env_names:
        prefix = env_root / env_name
        packages: list[dict[str, Any]] = []
        package_error = ""
        if include_packages and prefix.is_dir() and conda:
            packages, package_error = _conda_list(conda, prefix)
        environments[env_name] = {
            "declared": env_name in declared_envs,
            "present": prefix.is_dir(),
            "prefix": str(prefix),
            "declared_dependencies": _declared_dependencies(declared.get(env_name, {})),
            "package_count": len(packages),
            "packages": packages,
            "package_error": package_error,
        }

    return {
        "lockfile_version": 1,
        "kind": "abi-conda-lock",
        "generated_at": generated_at,
        "project_root": str(project_root),
        "mamba_root": str(mamba_root),
        "conda_executable": str(conda) if conda else "",
        "summary": {
            "declared_envs": len(declared_envs),
            "present_envs": len(present_envs),
            "missing_envs": sorted(declared_envs - present_envs),
            "extra_envs": sorted(present_envs - declared_envs),
        },
        "environments": environments,
    }


def build_tool_lock(
    *,
    project_root: Path,
    mamba_root: Path,
    resource_root: Path,
    environment_spec: Mapping[str, Any],
    conda_lock: Mapping[str, Any],
    resource_lock: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    assignments = environment_spec.get("tool_assignments", {})
    env_packages = _env_package_lookup(conda_lock)
    resource_paths = _resource_install_paths(resource_lock)
    tools: list[dict[str, Any]] = []

    for registry in sorted((project_root / "plugins").glob("*/tool_registry.yaml")):
        plugin = registry.parent.name
        data = _load_yaml(registry)
        for tool in data.get("tools", []):
            if not isinstance(tool, Mapping):
                continue
            tool_id = str(tool.get("id", ""))
            executable = str(tool.get("executable") or tool_id)
            env_name = str(tool.get("env_name") or _assigned_env(assignments, plugin, tool_id))
            env_prefix = _env_prefix(mamba_root, env_name)
            extra_dirs = _extra_path_dirs(
                metadata=tool,
                project_root=project_root,
                resource_root=resource_root,
                env_prefix=env_prefix,
                resource_paths=resource_paths.get(tool_id, []),
                executable=executable,
            )
            resolved = _resolve_executable(executable, env_prefix=env_prefix, extra_dirs=extra_dirs)
            matching_packages = _matching_packages(
                tool_id=tool_id,
                executable=executable,
                packages=env_packages.get(env_name, {}),
            )
            required = bool(tool.get("required", False))
            default_enabled = bool(tool.get("default_enabled", False))
            tools.append(
                {
                    "plugin": plugin,
                    "tool_id": tool_id,
                    "name": str(tool.get("name", tool_id)),
                    "category": str(tool.get("category", "")),
                    "required": required,
                    "default_enabled": default_enabled,
                    "env_name": env_name,
                    "env_prefix": str(env_prefix),
                    "env_present": env_prefix.is_dir(),
                    "executable": executable,
                    "resolved_path": str(resolved) if resolved else "",
                    "status": "ok" if resolved else "missing",
                    "blocking": bool((required or default_enabled) and not resolved),
                    "extra_path_dirs": [str(path) for path in extra_dirs],
                    "matching_packages": matching_packages,
                    "version_command": str(tool.get("version_command", "")),
                }
            )

    missing = [tool for tool in tools if tool["status"] != "ok"]
    blocking = [tool for tool in tools if tool["blocking"]]
    return {
        "lockfile_version": 1,
        "kind": "abi-tools-lock",
        "generated_at": generated_at,
        "project_root": str(project_root),
        "mamba_root": str(mamba_root),
        "resource_root": str(resource_root),
        "summary": {
            "registered_tools": len(tools),
            "present_tools": len(tools) - len(missing),
            "missing_tools": len(missing),
            "blocking_missing_tools": len(blocking),
        },
        "tools": tools,
    }


def build_resource_lock(
    *,
    project_root: Path,
    mamba_root: Path,
    resource_root: Path,
    analysis_types: Sequence[str],
    generated_at: str,
) -> dict[str, Any]:
    analyses: dict[str, Any] = {}
    for analysis_type in analysis_types:
        try:
            plugin = get_plugin(analysis_type)
            config = _cloud_resource_config(
                plugin=plugin,
                analysis_type=analysis_type,
                project_root=project_root,
                mamba_root=mamba_root,
                resource_root=resource_root,
            )
            rows = check_resources(analysis_type=analysis_type, config=config)
            counts = _status_counts(rows)
            analyses[analysis_type] = {
                "status_counts": counts,
                "resources": rows,
                "error": "",
            }
        except Exception as exc:  # pragma: no cover - defensive lock reporting
            analyses[analysis_type] = {
                "status_counts": {"error": 1},
                "resources": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
    return {
        "lockfile_version": 1,
        "kind": "abi-resources-lock",
        "generated_at": generated_at,
        "project_root": str(project_root),
        "mamba_root": str(mamba_root),
        "resource_root": str(resource_root),
        "analyses": analyses,
    }


def build_runtime_summary(
    *,
    conda_lock: Mapping[str, Any],
    tool_lock: Mapping[str, Any],
    resource_lock: Mapping[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    resource_counts: dict[str, int] = {}
    for analysis in resource_lock.get("analyses", {}).values():
        if not isinstance(analysis, Mapping):
            continue
        for status, count in analysis.get("status_counts", {}).items():
            resource_counts[str(status)] = resource_counts.get(str(status), 0) + int(count)
    return {
        "lockfile_version": 1,
        "kind": "abi-runtime-lock",
        "generated_at": generated_at,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "summary": {
            "conda": conda_lock.get("summary", {}),
            "tools": tool_lock.get("summary", {}),
            "resources": resource_counts,
        },
    }


def _cloud_resource_config(
    *,
    plugin: Any,
    analysis_type: str,
    project_root: Path,
    mamba_root: Path,
    resource_root: Path,
) -> Mapping[str, Any]:
    autoplasm_root = _first_existing_dir(resource_root / "autoplasm", resource_root)
    if analysis_type == "metagenomic_plasmid":
        return plugin.load_config(
            db_profile="light",
            overrides={"resources": {"root": str(autoplasm_root)}},
        )
    if analysis_type == "amplicon_16s":
        taxonomy_dir = resource_root / "amplicon_taxonomy"
        taxonomy_db = _first_existing_file(
            taxonomy_dir / "rdp_sintax.fa",
            taxonomy_dir / "rdp_16s_v16.fa",
            *sorted(taxonomy_dir.glob("*.fa")) if taxonomy_dir.exists() else (),
        )
        return plugin.load_config(
            overrides={
                "resources": {
                    "taxonomy_db": {"path": str(taxonomy_db)},
                    "diversity_script": str(project_root / "scripts" / "amplicon_diversity.py"),
                }
            }
        )
    if analysis_type == "easymetagenome":
        humann_root = _first_existing_dir(resource_root / "humann", autoplasm_root / "humann")
        return plugin.load_config(
            overrides={
                "resources": {
                    "host_db": str(resource_root / "kneaddata_host"),
                    "kraken2_db": str(resource_root / "kraken2"),
                    "humann_nucleotide_db": str(
                        _first_existing_dir(humann_root / "nucleotide", humann_root / "chocophlan")
                    ),
                    "humann_protein_db": str(
                        _first_existing_dir(humann_root / "protein", humann_root / "uniref")
                    ),
                    "metaphlan_db": str(resource_root / "metaphlan"),
                }
            }
        )
    if analysis_type in {"metatranscriptomics", "rnaseq_expression"}:
        return plugin.load_config(
            overrides={
                "resources": {
                    "genome_index": str(resource_root / "star_index"),
                    "annotation_gtf": str(resource_root / "NC_000913.3.gtf"),
                }
            }
        )
    if analysis_type == "viral_viwrap":
        return plugin.load_config(
            overrides={
                "resources": {
                    "db_dir": str(resource_root / "viwrap"),
                    "conda_env_dir": str(mamba_root / "envs"),
                }
            }
        )
    if analysis_type == "wgs_bacteria":
        amr_db = _first_existing_dir(resource_root / "amrfinder_db", resource_root / "amrfinderplus")
        return plugin.load_config(overrides={"resources": {"amrfinder_db": str(amr_db)}})
    return plugin.load_config()


def _resolve_conda_executable(explicit: str | Path | None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env_value = os.environ.get("ABI_CONDA_EXE")
    if env_value:
        candidates.append(Path(env_value))
    which = shutil.which("conda")
    if which:
        candidates.append(Path(which))
    candidates.extend(
        [
            Path("/root/autodl-tmp/miniconda3/bin/conda"),
            Path("/root/miniconda3/bin/conda"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _conda_list(conda: Path, prefix: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        result = subprocess.run(
            [str(conda), "list", "-p", str(prefix), "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return [], "conda list timed out"
    if result.returncode != 0:
        return [], (result.stderr or result.stdout).strip()[:500]
    try:
        packages = yaml.safe_load(result.stdout) or []
    except yaml.YAMLError as exc:
        return [], f"failed to parse conda list JSON: {exc}"
    normalized = []
    for package in packages:
        if not isinstance(package, Mapping):
            continue
        normalized.append(
            {
                "name": str(package.get("name", "")),
                "version": str(package.get("version", "")),
                "build_string": str(package.get("build_string", "")),
                "channel": str(package.get("channel", "")),
            }
        )
    return sorted(normalized, key=lambda item: item["name"]), ""


def _assigned_env(assignments: Any, plugin: str, tool_id: str) -> str:
    if isinstance(assignments, Mapping):
        plugin_assignments = assignments.get(plugin, {})
        if isinstance(plugin_assignments, Mapping) and tool_id in plugin_assignments:
            return str(plugin_assignments[tool_id])
        if tool_id in assignments and not isinstance(assignments.get(tool_id), Mapping):
            return str(assignments[tool_id])
    return "abi-base"


def _env_prefix(mamba_root: Path, env_name: str) -> Path:
    direct = mamba_root / env_name
    if direct.exists():
        return direct
    return mamba_root / "envs" / env_name


def _extra_path_dirs(
    *,
    metadata: Mapping[str, Any],
    project_root: Path,
    resource_root: Path,
    env_prefix: Path,
    resource_paths: Sequence[Path],
    executable: str,
) -> list[Path]:
    values = {
        "project_root": str(project_root),
        "resource_root": str(resource_root),
        "env_prefix": str(env_prefix),
    }
    dirs: list[Path] = []
    for raw in metadata.get("extra_path_dirs", []) or []:
        text = str(raw).format_map(_SafeFormat(values))
        dirs.append(Path(text))
    for install_path in resource_paths:
        dirs.extend(_resource_executable_dirs(install_path, executable))
    return _unique_existing_dirs(dirs)


def _resource_executable_dirs(install_path: Path, executable: str) -> list[Path]:
    candidates = [install_path, install_path / "bin"]
    if executable and not Path(executable).is_absolute():
        for child in install_path.glob("*") if install_path.is_dir() else []:
            if child.is_dir() and (child / executable).exists():
                candidates.append(child)
            if child.is_dir() and (child / "bin" / executable).exists():
                candidates.append(child / "bin")
    return candidates


def _resolve_executable(executable: str, *, env_prefix: Path, extra_dirs: Sequence[Path]) -> Path | None:
    path = Path(executable)
    if path.is_absolute() or path.parent != Path("."):
        return path if path.exists() else None
    env_bin = env_prefix / "bin"
    if env_bin.is_dir():
        resolved = shutil.which(executable, path=str(env_bin))
        if resolved:
            return Path(resolved)
    for directory in extra_dirs:
        resolved = shutil.which(executable, path=str(directory))
        if resolved:
            return Path(resolved)
    resolved = shutil.which(executable)
    return Path(resolved) if resolved else None


def _matching_packages(
    *,
    tool_id: str,
    executable: str,
    packages: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates = {_normalize_package_name(tool_id), _normalize_package_name(Path(executable).name)}
    candidates.update(_normalize_package_name(alias) for alias in PACKAGE_ALIASES.get(tool_id, ()))
    matches = []
    for name in sorted(candidates):
        package = packages.get(name)
        if package:
            matches.append(dict(package))
    return matches


def _env_package_lookup(conda_lock: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    lookup: dict[str, dict[str, Mapping[str, Any]]] = {}
    for env_name, env in conda_lock.get("environments", {}).items():
        if not isinstance(env, Mapping):
            continue
        packages = {}
        for package in env.get("packages", []):
            if isinstance(package, Mapping):
                packages[_normalize_package_name(str(package.get("name", "")))] = package
        lookup[str(env_name)] = packages
    return lookup


def _resource_install_paths(resource_lock: Mapping[str, Any]) -> dict[str, list[Path]]:
    paths: dict[str, list[Path]] = {}
    analyses = resource_lock.get("analyses", {})
    if not isinstance(analyses, Mapping):
        return paths
    for analysis in analyses.values():
        if not isinstance(analysis, Mapping):
            continue
        for row in analysis.get("resources", []):
            if not isinstance(row, Mapping):
                continue
            if row.get("field") != "install_path" or row.get("status") != "ok":
                continue
            tool_id = str(row.get("tool_id", ""))
            path = Path(str(row.get("path", "")))
            if tool_id and path.exists():
                paths.setdefault(tool_id, []).append(path)
    return paths


def _declared_dependencies(env_spec: Any) -> list[Any]:
    if isinstance(env_spec, Mapping):
        deps = env_spec.get("dependencies", [])
        return list(deps) if isinstance(deps, list) else []
    return []


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(payload), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _normalize_package_name(value: str) -> str:
    text = Path(value).name.lower()
    text = re.sub(r"(\.py|\.pl|\.r)$", "", text)
    return text.replace("_", "-")


def _first_existing_dir(*paths: Path) -> Path:
    for path in paths:
        if path.is_dir():
            return path
    return paths[0]


def _first_existing_file(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    return paths[0]


def _unique_existing_dirs(paths: Sequence[Path]) -> list[Path]:
    seen: set[str] = set()
    result = []
    for path in paths:
        if not path.is_dir():
            continue
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            result.append(path.resolve())
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _SafeFormat(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
