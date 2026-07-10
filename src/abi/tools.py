"""Tool skill base classes and registry loader for ABI plugins.

# Architecture / 架构
This module defines the canonical tool abstraction for the ABI pipeline:

    ToolSkill (ABC)          ← abstract lifecycle: check → plan → validate → run → parse
        └── GenericCommandSkill  ← YAML-driven command-template wrapper

    ToolRegistry             ← loads tool_registry.yaml, creates GenericCommandSkill instances

    RunResult                ← immutable dataclass for tool execution outcomes

    SafeFormatDict           ← lenient str.format_map() dict that returns "" for missing keys

# Design decisions / 设计决策
- **Template-driven**: Instead of writing a Python class per tool, 99% of tools
  are defined entirely in YAML via GenericCommandSkill's command_template
  field.  Only tools with complex post-processing need a custom ToolSkill
  subclass. / 99% 的工具通过 YAML 中的 command_template 定义，无需 Python 子类

- **Conda/Mamba environment isolation**: GenericCommandSkill resolves the
  tool's conda env via `resolved_mamba_root() / envs / env_name`, then
  prepends its `bin/` directory to PATH.  This avoids activating the
  environment via shell scripts that would complicate subprocess invocation.
  / 通过 PATH 前置而非激活 conda 环境来简化子进程调用

- **SafeFormatDict**: Python's str.format_map() raises KeyError for missing
  keys, which would crash the pipeline if a template references a parameter
  the user hasn't set.  SafeFormatDict returns "" instead, so the command
  renders with an empty placeholder rather than aborting. / 缺键返回空串而非异常

- **Dotted-field validation**: ``{key.attr}`` references in templates are
  rejected at validation time via ``_check_dotted_fields()`` because
  SafeFormatDict can only resolve simple ``{key}`` lookups — Python's
  ``format_map`` would attempt ``getattr(value, "attr")`` on the resolved
  string, causing an ``AttributeError`` at render time. / 模板中的 {key.attr}
  引用在验证时被拒绝。

- **Immutable RunResult**: Marked @dataclass (frozen=False for practical
  reasons but convention is read-only after construction).  This ensures
  that callers cannot accidentally mutate a result that other code holds a
  reference to. / RunResult 构建后视为只读
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import string
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Dict, Iterable, List, Mapping, Optional

import yaml

from abi.config import PROJECT_ROOT, resolved_mamba_root
from abi.errors import ConfigError, MissingTemplateParamError, ToolError
from abi.timeouts import DEFAULT_TOOL_TIMEOUT_SECONDS, timeout_from_env_or_value

_logger = logging.getLogger("abi.tools")

__all__ = [
    "GenericCommandSkill",
    "ResourceSpec",
    "RunResult",
    "ToolRegistry",
    "ToolSkill",
    "resolve_resources",
]

# Template fields that are allowed to be empty without causing validation errors.
# These represent optional pipeline features (e.g. abundance estimation, long-read
# Metaphlan) that may legitimately be unset for some analyses. / 允许为空的模板字段
OPTIONAL_TEMPLATE_FIELDS = {
    "abundance_label",
    "metaphlan_long_reads_flag",
    # Cross-sample visualization parameters — legitimately empty for single-sample runs
    "reference_plasmids",
    "host_plasmid_links",
    "annotations",
    "typing",
    "genbank_files",
}


def _derive_composite_params(params: Dict[str, Any]) -> None:
    """Auto-construct composite template parameters from granular inputs.

    Some tool contracts declare abstract input parameters (e.g.
    ``metaphlan_input``) that represent a combination of concrete inputs the
    DAG provides (``read1``, ``read2``).  Rather than requiring every DAG
    node or tool contract to duplicate this composition logic, we derive the
    composite parameter here when the pieces are available.

    Derivation rules (all use ``setdefault`` — never overwrite):
    - ``metaphlan_input`` ← ``{read1},{read2}`` (paired-end) or ``{read1}``
      (single-end) or ``{long_reads}`` (long-read).
    """
    if "metaphlan_input" not in params:
        r1 = params.get("read1")
        r2 = params.get("read2")
        lr = params.get("long_reads")
        if r1 and r2:
            params["metaphlan_input"] = f"{r1},{r2}"
        elif r1:
            params["metaphlan_input"] = str(r1)
        elif lr:
            params["metaphlan_input"] = str(lr)

    if "metaphlan_long_reads_flag" not in params:
        r1 = params.get("read1")
        r2 = params.get("read2")
        lr = params.get("long_reads")
        if r1 and r2:
            params["metaphlan_long_reads_flag"] = ""
        elif lr:
            params["metaphlan_long_reads_flag"] = "--long_reads"
        else:
            params["metaphlan_long_reads_flag"] = ""


# Template fields that represent external resource files (databases, models, indexes).
# These are checked by _resource_status() to verify they exist on disk before the
# pipeline runs. / 表示外部资源文件的模板字段，运行前由 _resource_status() 检查
RESOURCE_FIELDS = {
    "database",
    "model",
    "refgraph",
    "ref_list",
    "reflist",
    "plasmid_index",
    "annotations",
    "gene_calls",
    "reference",
    "reference_plasmids",
    "genome_index",
    "annotation_gtf",
    "abricate_db",
}


# ── ResourceSpec ───────────────────────────────────────────────────────
# Compute resource request for a single tool invocation.  Resolved from
# multiple layers: tool contract → resource profile → user config → CLI overrides.
# / 单个工具调用的计算资源请求，由多个层级解析得出。


@dataclass
class ResourceSpec:
    """Compute resource request for a tool invocation.

    Stored as human-readable strings (``"8GB"``, ``"04:00:00"``) and
    rendered to scheduler-specific formats via ``to_nextflow_directives()``
    and ``to_slurm_directives()``.

    # Resolution precedence / 解析优先级
    Tool contract (authoritative default) < resource profile < user config
    defaults < per-tool user config override < CLI flag.
    """

    cpu: int = 1
    memory: str = "4GB"
    walltime: str = "01:00:00"
    accelerator: str | None = None
    disk: str | None = None

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "ResourceSpec":
        """Extract resource spec from tool contract or registry metadata.

        Looks for a ``resources`` key in the metadata dict; returns defaults
        for any field not present. / 从 YAML 元数据中提取资源规格。
        """
        resources = metadata.get("resources")
        if not isinstance(resources, Mapping):
            return cls()
        return cls(
            cpu=int(resources.get("cpu", 1)),
            memory=str(resources.get("memory", "4GB")),
            walltime=str(resources.get("walltime", "01:00:00")),
            accelerator=str(resources["accelerator"]) if resources.get("accelerator") else None,
            disk=str(resources["disk"]) if resources.get("disk") else None,
        )

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any]) -> "ResourceSpec":
        """Build from a resource profile dict (e.g. ``hpc_large.yaml``).

        Profile values that are absent or None fall back to the dataclass defaults.
        / 从资源 profile 构建，缺失字段使用默认值。
        """
        return cls(
            cpu=int(profile.get("cpu", 1)),
            memory=str(profile.get("memory", "4GB")),
            walltime=str(profile.get("walltime", "01:00:00")),
            accelerator=str(profile["accelerator"]) if profile.get("accelerator") else None,
            disk=str(profile["disk"]) if profile.get("disk") else None,
        )

    # ── Merging ───────────────────────────────────────────────────────

    def merge(self, overrides: "ResourceSpec | None") -> "ResourceSpec":
        """Return a new spec with non-default fields from *overrides* applied.

        Only fields where *overrides* differs from the hardcoded defaults are
        copied — this avoids overwriting intentional values with accidental
        defaults. / 只复制 overrides 中与硬编码默认值不同的字段。
        """
        if overrides is None:
            return self
        defaults = ResourceSpec()
        return ResourceSpec(
            cpu=overrides.cpu if overrides.cpu != defaults.cpu else self.cpu,
            memory=overrides.memory if overrides.memory != defaults.memory else self.memory,
            walltime=(
                overrides.walltime if overrides.walltime != defaults.walltime else self.walltime
            ),
            accelerator=(
                overrides.accelerator
                if overrides.accelerator != defaults.accelerator
                else self.accelerator
            ),
            disk=overrides.disk if overrides.disk != defaults.disk else self.disk,
        )

    # ── Scheduler rendering ───────────────────────────────────────────

    def to_nextflow_directives(self) -> list[str]:
        """Render as Nextflow process directives.

        Example: ``["cpus 8", "memory '16.GB'", "time '04:00:00'"]``
        """
        lines = [f"cpus {self.cpu}"]
        lines.append(f"memory '{_memory_to_nextflow(self.memory)}'")
        lines.append(f"time '{self.walltime}'")
        if self.disk:
            lines.append(f"disk '{_disk_to_nextflow(self.disk)}'")
        if self.accelerator:
            lines.append(f"accelerator {self.accelerator}")
        return lines

    def to_slurm_directives(self) -> list[str]:
        """Render as ``#SBATCH`` directives.

        Example:
        ``["#SBATCH --cpus-per-task=8", "#SBATCH --mem=16G", "#SBATCH --time=04:00:00"]``
        """
        lines = [f"#SBATCH --cpus-per-task={self.cpu}"]
        lines.append(f"#SBATCH --mem={_memory_to_slurm(self.memory)}")
        lines.append(f"#SBATCH --time={self.walltime}")
        if self.accelerator:
            lines.append(f"#SBATCH --gres={self.accelerator}")
        return lines

    def to_pbs_directives(self) -> list[str]:
        """Render as ``#PBS`` directives.

        Example:
        ``["#PBS -l nodes=1:ppn=8", "#PBS -l mem=16gb", "#PBS -l walltime=04:00:00"]``
        """
        lines = [f"#PBS -l nodes=1:ppn={self.cpu}"]
        lines.append(f"#PBS -l mem={_memory_to_pbs(self.memory)}")
        lines.append(f"#PBS -l walltime={self.walltime}")
        return lines


# ── Memory formatting helpers ─────────────────────────────────────────
# Convert human-readable memory strings to scheduler-specific formats.


def _memory_to_nextflow(memory: str) -> str:
    """Convert ``"16GB"`` → ``"16.GB"`` for Nextflow process directives."""
    import re

    m = re.match(r"(\d+)\s*(GB|MB|TB|G|M|T)", memory.upper().replace(" ", ""))
    if not m:
        return memory
    value, unit = m.group(1), m.group(2)
    if unit in ("G", "GB"):
        return f"{value}.GB"
    if unit in ("M", "MB"):
        return f"{value}.MB"
    if unit in ("T", "TB"):
        return f"{value}.TB"
    return memory


def _memory_to_slurm(memory: str) -> str:
    """Convert ``"16GB"`` → ``"16G"`` for ``#SBATCH --mem``."""
    import re

    m = re.match(r"(\d+)\s*(GB|MB|TB|G|M|T)", memory.upper().replace(" ", ""))
    if not m:
        return memory
    value, unit = m.group(1), m.group(2)
    if unit in ("G", "GB"):
        return f"{value}G"
    if unit in ("M", "MB"):
        return f"{value}M"
    if unit in ("T", "TB"):
        return f"{value}T"
    return memory


def _memory_to_pbs(memory: str) -> str:
    """Convert ``"16GB"`` → ``"16gb"`` for ``#PBS -l mem``."""
    return _memory_to_slurm(memory).lower()


def _disk_to_nextflow(disk: str) -> str:
    """Convert ``"50GB"`` → ``"50.GB"`` for Nextflow ``disk`` directive."""
    return _memory_to_nextflow(disk)


# ── Resource resolution engine ─────────────────────────────────────────


def resolve_resources(
    tool_id: str,
    tool_metadata: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
    cli_overrides: ResourceSpec | None = None,
    resource_profile: str | None = None,
    resource_profiles_dir: str | Path | None = None,
) -> ResourceSpec:
    """Resolve compute resources through the layered override chain.

    Resolution order (most specific wins): / 解析顺序（最具体的优先）
    1. Hardcoded defaults (cpu=1, memory="4GB", walltime="01:00:00")
    2. Tool contract ``resources:`` block (authoritative per-tool default)
    3. Resource profile YAML (if ``resource_profile`` is specified)
    4. User config ``execution.resources.defaults``
    5. User config ``execution.resources.tool_overrides.<tool_id>``
    6. CLI overrides (``--cpu``, ``--memory``, ``--walltime``, etc.)

    Returns a resolved ``ResourceSpec`` ready for scheduler rendering.
    """
    # Layer 1: hardcoded defaults / 硬编码默认值
    spec = ResourceSpec()

    # Layer 2: tool contract (authoritative per-tool base) / 工具合同
    tool_resources = ResourceSpec.from_metadata(tool_metadata)
    spec = spec.merge(tool_resources)

    # Layer 3: resource profile (named preset) / 资源 profile
    if resource_profile:
        profile_data = _load_resource_profile(resource_profile, resource_profiles_dir)
        if profile_data:
            spec = spec.merge(ResourceSpec.from_profile(profile_data))

    # Layer 4-5: user config overrides / 用户配置覆盖
    if config:
        exec_cfg = config.get("execution", {})
        if isinstance(exec_cfg, Mapping):
            resources_cfg = exec_cfg.get("resources", {})
            if isinstance(resources_cfg, Mapping):
                # Layer 4: global defaults / 全局默认
                defaults = resources_cfg.get("defaults")
                if isinstance(defaults, Mapping):
                    spec = spec.merge(ResourceSpec.from_profile(defaults))
                # Layer 5: per-tool override / 单工具覆盖
                overrides = resources_cfg.get("tool_overrides", {})
                if isinstance(overrides, Mapping):
                    tool_override = overrides.get(tool_id)
                    if isinstance(tool_override, Mapping):
                        spec = spec.merge(ResourceSpec.from_profile(tool_override))

    # Layer 6: CLI overrides (highest priority) / CLI 覆盖（最高优先级）
    if cli_overrides:
        spec = spec.merge(cli_overrides)

    return spec


def _load_resource_profile(
    name: str,
    profiles_dir: str | Path | None = None,
) -> Mapping[str, Any] | None:
    """Load a named resource profile YAML file.

    Searches: / 搜索路径
    1. ``profiles_dir/<name>.yaml`` (if provided)
    2. ``PROJECT_ROOT/config/resource_profiles/<name>.yaml``
    """
    from abi.config import PROJECT_ROOT, load_yaml

    candidates = []
    if profiles_dir:
        candidates.append(Path(profiles_dir) / f"{name}.yaml")
    candidates.append(PROJECT_ROOT / "config" / "resource_profiles" / f"{name}.yaml")
    for candidate in candidates:
        if candidate.exists():
            return load_yaml(str(candidate))
    return None


# ── Container image resolution ─────────────────────────────────────────


def resolve_container_image(
    tool_id: str,
    tool_metadata: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
    cli_image: str | None = None,
) -> str | None:
    """Resolve container image through the layered override chain.

    1. CLI ``--container-image`` (per-invocation override)
    2. ``execution.container.tool_images.<tool_id>`` (per-tool in config)
    3. ``execution.container.default_image`` (global in config)
    4. Tool contract ``execution.container_image`` (authoritative default)
    5. Tool registry ``container_image`` (flat metadata)
    6. None (use conda env)
    """
    # Layer 1: tool metadata (registry flat or contract nested)
    img = tool_metadata.get("container_image")
    if not img:
        exec_block = tool_metadata.get("execution", {})
        if isinstance(exec_block, Mapping):
            img = exec_block.get("container_image")
    result = str(img) if img else None

    # Layer 2-3: user config
    if config:
        exec_cfg = config.get("execution", {})
        if isinstance(exec_cfg, Mapping):
            container_cfg = exec_cfg.get("container", {})
            if isinstance(container_cfg, Mapping):
                # Layer 2: global default image
                default_img = container_cfg.get("default_image")
                if default_img:
                    result = str(default_img)
                # Layer 3: per-tool override
                tool_images = container_cfg.get("tool_images", {})
                if isinstance(tool_images, Mapping):
                    tool_img = tool_images.get(tool_id)
                    if tool_img:
                        result = str(tool_img)

    # Layer 4: CLI override (highest priority)
    if cli_image:
        result = cli_image

    return result


def _resolve_container_runtime(config: Mapping[str, Any] | None = None) -> str:
    """Resolve the container runtime engine from env or config.

    Checks ``ABI_CONTAINER_RUNTIME`` env var, then config
    ``execution.container.runtime``, then auto-detects from PATH.
    Returns one of ``"docker"``, ``"singularity"``, ``"podman"``, ``"apptainer"``.
    / 从环境变量或配置解析容器运行时引擎。
    """
    import os as _os

    # Env var (highest priority) / 环境变量（最高优先级）
    env_runtime = _os.environ.get("ABI_CONTAINER_RUNTIME")
    if env_runtime:
        return env_runtime.strip().lower()

    # Config / 配置
    if config:
        exec_cfg = config.get("execution", {})
        if isinstance(exec_cfg, Mapping):
            container_cfg = exec_cfg.get("container", {})
            if isinstance(container_cfg, Mapping):
                runtime = container_cfg.get("runtime")
                if runtime:
                    return str(runtime).strip().lower()

    # Auto-detect / 自动检测
    for candidate in ("docker", "podman", "singularity", "apptainer"):
        if shutil.which(candidate):
            return candidate
    return "docker"  # fallback


def _wrap_container_command(
    command: list[str],
    *,
    image: str,
    work_dir: str | None = None,
    runtime: str = "docker",
    cpu: int | None = None,
    memory: str | None = None,
) -> list[str]:
    """Wrap a command list for container execution.

    Docker/Podman:
      ``docker run --rm --cpus=<N> -m <M> -v <wd>:<wd> -w <wd> <image> <cmd>``
    Singularity/Apptainer:
      ``singularity exec --bind <wd> --pwd <wd> <image> <cmd>``
    """
    cwd = work_dir or str(Path.cwd())
    if runtime in ("singularity", "apptainer"):
        cmd = [runtime, "exec", "--bind", f"{cwd}:{cwd}", "--pwd", cwd]
        if cpu:
            cmd.extend(["--cpus", str(cpu)])
        if memory:
            cmd.extend(["--memory", memory])
        cmd.append(image)
        cmd.extend(command)
        return cmd
    else:
        # Docker / Podman
        cmd = [runtime, "run", "--rm"]
        if cpu:
            cmd.extend(["--cpus", str(cpu)])
        if memory:
            cmd.extend(["--memory", memory])
        cmd.extend(["-v", f"{cwd}:{cwd}", "-w", cwd, image])
        cmd.extend(command)
        return cmd


# ── RunResult ──────────────────────────────────────────────────────────
# Immutable-by-convention result of a single tool invocation.
# All fields are populated once in GenericCommandSkill.run() and then only read.
# / 单次工具调用的结果，构建后只读。


@dataclass
class RunResult:
    """Immutable record of a tool execution.

    # Why a dataclass? / 为什么用 dataclass？
    - `to_dict()` via `asdict()` gives a JSON-serializable dict for logging.
    - `@dataclass` auto-generates __init__, __repr__, __eq__ — less boilerplate.
    - Consumers can destructure: `result.tool_name`, `result.return_code`, etc.

    # Fields / 字段
    - tool_name: Registry id of the tool (e.g. "fastqc") / 工具注册 ID
    - command: The full shell command token list that was executed / 执行的命令
    - return_code: Exit code (0=success, -1=timeout) / 退出码
    - stdout/stderr: Captured output (empty if redirected to files) / 捕获的输出
    - start_time/end_time: ISO 8601 timestamps with second precision / 时间戳
    - duration_seconds: Wall-clock duration / 耗时
    - outputs: Dict of output file paths the tool produced / 输出文件路径
    - log_file: Optional path to the step log (if configured) / 步骤日志路径
    - status: "success", "failed", "timeout", or "dry_run" / 执行状态
    """

    tool_name: str
    command: List[str]
    return_code: int
    stdout: str
    stderr: str
    start_time: str
    end_time: str
    duration_seconds: float
    outputs: Dict[str, Any] = field(default_factory=dict)
    log_file: Optional[str] = None
    status: str = "success"
    # The fully-resolved parameters after select_params() merge (B23 fix).
    # Records what was actually executed, not what was planned.
    # select_params() 合并后的完整参数，记录实际执行的参数。
    resolved_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dict for JSON serialization in logs/reports.

        Uses dataclasses.asdict() which recursively converts the dataclass
        to nested dicts/lists. / 递归转换为嵌套 dict/list 用于 JSON 序列化。
        """
        return asdict(self)


# ── ToolSkill (abstract base) ──────────────────────────────────────────
# Defines the standard lifecycle every tool follows in the ABI pipeline.
# Subclasses must implement all methods (GenericCommandSkill provides defaults).
# / 定义每个工具在 ABI 管道中的标准生命周期。子类必须实现所有方法。


class ToolSkill:
    """Abstract base for all tool skills.

    # Lifecycle / 生命周期
    The pipeline orchestrator calls these methods in order:

    1. check_installation()  → Can the tool binary be found? / 工具是否可找到？
    2. plan()                → What will this step do? (for dry-run preview) / 步骤做什么？
    3. validate_inputs()     → Do the required input files exist? / 输入文件存在？
    4. select_params()       → Merge user params with defaults. / 合并用户参数和默认值
    5. build_command()       → Render the shell command token list. / 生成命令
    6. run()                 → Execute the command via subprocess. / 执行命令
    7. parse_outputs()       → Discover output files on disk. / 发现输出文件
    8. normalize_outputs()   → Convert parsed data to standard schema. / 标准化输出

    # Why separate parse_outputs and normalize_outputs? / 为什么分两步？
    Parsing discovers what files exist (facts). Normalization transforms them
    into the standard schema (policy). Separating them lets plugins override
    `normalize_outputs` to remap fields without touching file discovery logic.
    / 解析发现事实，标准化转换格式。分离后插件可覆盖 normalize_outputs 而不影响文件发现。
    """

    # Class-level defaults (overridden by subclasses or YAML metadata)
    name: str
    version: Optional[str]
    env_name: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    def check_installation(self) -> bool:
        """Return True if the tool executable is available on PATH or in its conda env.

        Called early in the pipeline to fail fast if a required tool is missing.
        / 管道早期调用，如工具缺失则快速失败。
        """
        raise NotImplementedError

    def plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a plan dict describing what this step will do.

        Used for dry-run previews and provenance records. / 用于试运行预览和溯源记录。
        """
        raise NotImplementedError

    def validate_inputs(self, params: Dict[str, Any]) -> None:
        """Raise ToolError if any required input file does not exist.

        Called BEFORE the command is built so callers get a clear error rather
        than a confusing "file not found" from the tool itself. / 在构建命令前验证输入。
        """
        raise NotImplementedError

    def select_params(self, params: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
        """Merge user-provided params with sensible defaults for this tool.

        # Modes / 模式
        - "auto": Automatic parameter selection (defaults + heuristics) / 自动选择
        - "manual": Respect user params as-is (minimal defaults) / 尊重用户参数

        Returns a complete params dict ready for build_command(). / 返回完整参数字典。
        """
        raise NotImplementedError

    def build_command(self, params: Dict[str, Any]) -> List[str]:
        """Render the selected params into a shell command token list.

        Returns a list of strings suitable for subprocess.run(). The list form
        avoids shell injection vulnerabilities that would exist with a string
        command + shell=True. / 返回列表形式避免 shell 注入。
        """
        raise NotImplementedError

    def run(self, params: Dict[str, Any], dry_run: bool = False) -> RunResult:
        """Execute the tool and return a RunResult.

        # dry_run mode / 试运行模式
        When dry_run=True, validates inputs and builds the command but does NOT
        execute the tool. Returns a RunResult with status="dry_run". / 仅验证和构建不执行。
        """
        raise NotImplementedError

    def parse_outputs(self, output_dir: str) -> Dict[str, Any]:
        """Scan the output directory and return discovered file paths.

        Returns a dict with keys like "output_dir" and "files". / 扫描输出目录返回文件路径。
        """
        raise NotImplementedError

    def normalize_outputs(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Transform parsed output dict to match the tool's output_schema.

        Plugins may override this to remap field names without changing the
        file-discovery logic in parse_outputs(). / 插件可覆盖此方法重新映射字段。
        """
        raise NotImplementedError

    def dry_run(self, params: Dict[str, Any]) -> RunResult:
        """Convenience: run with dry_run=True. / 便捷方法：以试运行模式执行。"""
        return self.run(params, dry_run=True)

    def capture_version(self) -> str:
        """Return the tool's version string, or ``""`` if unavailable (B5/B2 fix).

        Default implementation: runs ``version_command`` from YAML metadata
        with a short timeout.  If ``version_regex`` is configured, extracts
        the first capture group from the command output.

        Failure is non-fatal — returns a diagnostic string like
        ``"version_command_failed(exit=1)"`` or ``"version_command_timeout"``
        so the pipeline can continue while recording the failure reason.

        Subclasses may override this to provide tool-specific version logic.
        """
        return ""


# ── GenericCommandSkill ────────────────────────────────────────────────
# This is the workhorse: it maps a YAML tool definition to a fully functional
# ToolSkill.  Instead of writing Python, users author YAML with a command_template
# string like `tool --input {input} --threads {threads}`.  GenericCommandSkill
# renders the template, resolves the conda environment, and invokes the command.
#
# 这是主力类：将 YAML 工具定义映射为完整的 ToolSkill。用户在 YAML 中编写
# command_template 字符串，由 GenericCommandSkill 渲染模板、解析 conda 环境并调用命令。


class _PathHintFormat(dict[str, str]):
    """Keep unknown path-template fields unchanged instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class SafeFormatDict(dict):
    """A dict subclass that handles missing keys during str.format_map().

    # Motivation / 动机
    Python's str.format_map() raises KeyError when a template contains a key
    that is not in the mapping.  Tool command templates may reference optional
    parameters (e.g. `{metaphlan_long_reads_flag}`) that are legitimately absent.

    # Two modes / 两种模式

    - **Strict** (``strict=True``): raises ``MissingTemplateParamError`` for
      unrecognized keys.  Controlled by the ``ABI_STRICT_TEMPLATES`` env var
      (default ``"1"`` in CI, ``"0"`` in production).  Use this during
      development and testing to catch template typos early.
    - **Lenient** (``strict=False``, default): returns ``""`` for missing keys
      and logs a WARNING so the omission is traceable but does not abort the
      pipeline.  Safe for production where unknown optional parameters are
      tolerable.

    # Tracked missing keys / 缺失键追踪
    ``missing_keys`` records every key that was substituted with an empty
    string.  Callers can inspect this after ``format_map()`` to detect
    parameter gaps without aborting.
    """

    # Class-level missing keys tracking — accumulates across all instances
    # so callers can inspect total missing-key surface after batch rendering.
    # 类级别缺失键追踪 — 跨所有实例累计，调用者可在批量渲染后检查总缺失键面积。
    _all_missing_keys: ClassVar[set[str]] = set()

    @classmethod
    def clear_all_missing_keys(cls) -> None:
        """Reset the class-level missing key tracker.

        Useful between independent rendering passes (e.g. between tool
        command templates and DAG path templates).
        """
        cls._all_missing_keys.clear()

    @classmethod
    def get_all_missing_keys(cls) -> set[str]:
        """Return a copy of all missing keys tracked across instances."""
        return cls._all_missing_keys.copy()

    def __init__(
        self,
        *args: Any,
        strict: bool | None = None,
        tool_name: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        # Resolve strict mode: explicit arg > env var > default False
        if strict is None:
            strict = os.environ.get("ABI_STRICT_TEMPLATES", "0") == "1"
        self.strict = strict
        self.tool_name = tool_name
        self.missing_keys: list[str] = []

    def __getitem__(self, key: str) -> Any:
        """Return the value for *key*, joining lists into space-separated strings.

        This is called by ``str.format_map()`` for each template key.  When a
        parameter value is a list (e.g. aggregated cross-sample inputs), the
        items are joined with spaces so they form valid command-line arguments.
        Non-list values are returned unchanged — ``str.format_map()`` will call
        ``str()`` on them as needed.
        / 当值为列表时（如跨样本聚合输入），用空格连接。非列表值原样返回。
        """
        val = super().__getitem__(key)
        if isinstance(val, (list, tuple)):
            return " ".join(str(v) for v in val)
        return val

    def __missing__(self, key: str) -> str:
        """Handle a missing template key.

        In strict mode, raises ``MissingTemplateParamError``.
        In lenient mode, logs a WARNING and returns ``""``.
        Keys registered in OPTIONAL_TEMPLATE_FIELDS are silently defaulted to ``""``.
        """
        self.missing_keys.append(key)
        SafeFormatDict._all_missing_keys.add(key)
        # Fields registered as optional are legitimately absent — no warning needed.
        if key in OPTIONAL_TEMPLATE_FIELDS:
            return ""
        if self.strict:
            tool_label = self.tool_name or "unknown"
            raise MissingTemplateParamError(
                f"{tool_label}: command template references undefined "
                f"parameter {key!r}. Add it to select_params() defaults or "
                f"register it in OPTIONAL_TEMPLATE_FIELDS."
            )
        _logger.warning(
            "Template parameter %r missing from params for tool %r; substituting empty string.",
            key,
            self.tool_name or "unknown",
        )
        return ""


class GenericCommandSkill(ToolSkill):
    """Generic command-template wrapper for registered command-line tools.

    # How it works / 工作原理
    1. Constructor receives YAML metadata dict from ToolRegistry. / 构造器接收 YAML 元数据
    2. select_params() merges user params with defaults (threads, database paths, etc.).
       / select_params() 合并用户参数与默认值
    3. command_text() renders the template with SafeFormatDict to avoid KeyError.
       / command_text() 使用 SafeFormatDict 渲染模板
    4. build_command() tokenizes the rendered text via shlex.split(). / shlex.split() 分词
    5. run() resolves the conda env, optionally redirects stdout/stderr to files,
       and invokes subprocess.run() with a configurable timeout. / 解析环境并执行

    # Stdout redirection / 标准输出重定向
    If the command template contains `> output.txt`, _command_without_stdout_redirect()
    strips the redirection from the command list and opens the target file as a
    handle passed to subprocess.run().  This avoids shell=True while still
    supporting large output files that would overwhelm PIPE buffers. / 支持大文件
    输出而不使用 shell=True。
    """

    def __init__(self, metadata: Mapping[str, Any]) -> None:
        # Store the full metadata dict; YAML fields beyond the documented ones
        # are preserved for tool-specific logic. / 存储完整元数据，未记录字段也保留
        self.metadata = dict(metadata)
        self.name = str(metadata["id"])
        self.version = None  # Can be set by a tool-specific subclass / 可由工具子类设置
        self.env_name = str(metadata.get("env_name", "abi-base"))
        # input_schema and output_schema are lightweight wrappers that plugins
        # may override with richer typing / 输入输出 schema 是轻量包装器
        self.input_schema = {"inputs": metadata.get("inputs", [])}
        self.output_schema = {"outputs": metadata.get("outputs", [])}

    @property
    def executable(self) -> str:
        """The binary name or path. Defaults to the tool id if not set in YAML.

        # Why default to id? / 为什么默认用 id？
        Many tools use the same name for their registry id and binary (e.g.
        "fastqc" is both the id and the executable name), so defaulting to
        the id reduces YAML boilerplate. / 减少 YAML 样板代码。
        """
        return str(self.metadata.get("executable") or self.name)

    @property
    def command_template(self) -> str:
        """The Python format-string template for the command.

        If not specified in YAML, a sensible default is generated from the
        executable name and common parameters. / 未指定时从可执行文件名生成默认模板。
        """
        template = self.metadata.get("command_template")
        if template:
            return str(template)
        return f"{self.executable} --input {{input}} --output {{output_dir}} --threads {{threads}}"

    @property
    def resources(self) -> "ResourceSpec":
        """Compute resource request for this tool from its YAML metadata."""
        return ResourceSpec.from_metadata(self.metadata)

    @property
    def container_image(self) -> str | None:
        """Container image for this tool (e.g ``docker://biocontainers/fastp:v0.23``).

        Read from metadata key ``container_image`` (flat registry) or
        ``execution.container_image`` (tool contract). Returns None if not set.
        / 读取容器镜像，未设置返回 None。
        """
        img = self.metadata.get("container_image")
        if img:
            return str(img)
        execution = self.metadata.get("execution", {})
        if isinstance(execution, Mapping):
            img = execution.get("container_image")
            if img:
                return str(img)
        return None

    @property
    def mamba_root(self) -> Path:
        """Resolved path to the conda/mamba installation root.

        Delegates to abi.config.resolved_mamba_root() which checks the
        ABI_MAMBA_ROOT env var, config file, and default paths in order.
        / 按优先级解析 conda/mamba 根目录。
        """
        return resolved_mamba_root()

    @property
    def env_prefix(self) -> Path:
        """Path to the conda environment directory.

        Supports two layouts:
        1. Direct: ``{mamba_root}/{env_name}`` (e.g. mamba env create -p ...)
        2. Managed: ``{mamba_root}/envs/{env_name}`` (standard conda convention)

        The direct layout is checked first; the managed layout is the fallback.
        / 支持两种布局，优先检查直接路径。
        """
        direct = self.mamba_root / self.env_name
        if direct.exists():
            return direct
        return self.mamba_root / "envs" / self.env_name

    @property
    def env_bin(self) -> Path:
        """Path to the bin/ directory inside the conda environment.

        Prepending this to PATH is how we "activate" the environment without
        running the conda shell activation script. / 前置到 PATH 以"激活"环境。
        """
        return self.env_prefix / "bin"

    def runtime_env(self) -> Dict[str, str]:
        """Build the OS environment dict for subprocess invocation.

        # What we do / 做了什么
        - Copy the current process environment (so PATH, HOME, etc. are inherited).
          / 复制当前进程环境
        - Prepend {env_bin} to PATH so the conda env's binaries are found first.
          / 前置 conda env 的 bin 目录
        - Prepend registry-declared ``extra_path_dirs`` for tools installed as
          ABI resources (for example PLASMe or Platon source checkouts).
        - Set CONDA_PREFIX and MAMBA_ROOT_PREFIX so tools that introspect their
          conda environment (e.g. Python scripts that check sys.prefix) work correctly.
          / 设置 CONDA_PREFIX 等供工具内省
        - Remove PYTHONPATH to prevent the host Python's site-packages from
          leaking into the isolated conda environment. / 移除 PYTHONPATH 防泄漏
        """
        env = os.environ.copy()
        # Fix OMP_NUM_THREADS=0 (invalid value) inherited from host environment.
        # Valid values are positive integers or unset. / 修复宿主环境中无效的 0 值。
        omp_threads = env.get("OMP_NUM_THREADS", "")
        if omp_threads == "0" or omp_threads == 0:
            env.pop("OMP_NUM_THREADS", None)
        path_parts: list[str] = []
        if self.env_bin.exists():
            path_parts.append(str(self.env_bin))
            env["CONDA_PREFIX"] = str(self.env_prefix)
            env["MAMBA_ROOT_PREFIX"] = str(self.mamba_root)
            env.pop("PYTHONPATH", None)
        path_parts.extend(str(path) for path in self.extra_path_dirs())
        if path_parts:
            path_parts.append(env.get("PATH", ""))
            env["PATH"] = os.pathsep.join(part for part in path_parts if part)
        return env

    def extra_path_dirs(self) -> list[Path]:
        """Return existing registry-declared PATH additions for resource-installed tools."""
        raw_dirs = self.metadata.get("extra_path_dirs", [])
        if not isinstance(raw_dirs, list):
            return []
        resource_root = (
            os.environ.get("ABI_RESOURCE_ROOT")
            or os.environ.get("AUTOPLASM_RESOURCE_ROOT")
            or str(PROJECT_ROOT / "resources" / "autoplasm")
        )
        values = {
            "project_root": str(PROJECT_ROOT),
            "resource_root": resource_root,
            "env_prefix": str(self.env_prefix),
        }
        paths: list[Path] = []
        seen: set[str] = set()
        for raw in raw_dirs:
            try:
                candidate = Path(str(raw).format_map(_PathHintFormat(values)))
            except Exception:
                continue
            if not candidate.is_dir():
                continue
            resolved = str(candidate.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(candidate.resolve())
        return paths

    def check_installation(self) -> bool:
        """Return True if the tool executable can be found.

        # Resolution order / 解析顺序
        1. If mock_tools is set, always return True (for testing). / mock 模式直接返回
        2. If executable is an absolute path or contains a directory component,
           check with .exists() directly. / 绝对路径直接检查
        3. Otherwise, search in the conda env's bin directory via shutil.which().
           / 在 conda env 的 bin 目录中搜索
        """
        if self.metadata.get("mock_tools"):
            return True
        executable_path = Path(self.executable)
        # Absolute path or path with directory: check directly / 绝对路径或含目录：直接检查
        if executable_path.is_absolute() or executable_path.parent != Path("."):
            return executable_path.exists()
        # Simple name: search in conda env's bin first, then system PATH.
        # / 简单名称：先在 conda env 中搜索，然后搜索系统 PATH。
        if self.env_bin.exists() and shutil.which(self.executable, path=str(self.env_bin)):
            return True
        for directory in self.extra_path_dirs():
            if shutil.which(self.executable, path=str(directory)):
                return True
        # Fall back to full system PATH (some tools like Rscript may only
        # exist outside the conda env). / 回退到完整系统 PATH。
        return shutil.which(self.executable) is not None

    def plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a lightweight plan dict describing this step.

        Used by the pipeline orchestrator for dry-run previews. / 用于管道试运行预览。
        """
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        return {
            "tool_name": self.name,
            "env_name": self.env_name,
            "command": self.build_command(selected),
            "outputs": selected.get("outputs", {}),
        }

    def validate_inputs(self, params: Dict[str, Any]) -> None:
        """Check that all required input files exist on disk.

        Only validates inputs that look like file paths — string parameters
        (e.g. primer sequences, database names, URLs) are skipped.

        When a parameter value is a list (aggregated cross-sample inputs),
        each element is checked individually. / 列表参数逐项检查。

        # Skip in dry_run / 试运行时跳过
        In dry-run mode, input files may not exist yet (e.g. outputs of
        upstream steps), so validation is skipped. / 试运行时上游输出可能还不存在。
        """
        missing: List[str] = []
        resource_placeholders: List[str] = []
        for key in self.metadata.get("inputs", []):
            value = params.get(key)
            if not value:
                continue
            # Handle aggregated lists (cross-sample inputs) / 处理聚合列表
            candidates: List[str] = []
            if isinstance(value, (list, tuple)):
                candidates = [str(v) for v in value]
            else:
                candidates = [str(value)]
            for cand in candidates:
                if key in RESOURCE_FIELDS and any(
                    marker in cand for marker in ("NOT_CONFIGURED", "PLACEHOLDER", "TODO")
                ):
                    resource_placeholders.append(f"{key}={cand}")
                    continue
                if _looks_like_path(cand) and not Path(cand).exists():
                    missing.append(f"{key}={cand}")
        if resource_placeholders and not params.get("dry_run", False):
            raise ToolError(
                f"{self.name}: Resource NOT_CONFIGURED: {', '.join(resource_placeholders)}"
            )
        if missing and not params.get("dry_run", False):
            raise ToolError(f"{self.name}: input files do not exist: {', '.join(missing)}")

    def select_params(self, params: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
        """Merge user params with tool-specific defaults.

        # Default layering / 默认值层级
        User params > Tool defaults > Pipeline-wide defaults

        # Why setdefault and not {**defaults, **params}? / 为什么用 setdefault？
        setdefault preserves user-provided values exactly as given, while dict
        merging would overwrite user values with defaults if the defaults come
        last.  This way the user always wins. / setdefault 确保用户值优先。
        """
        selected = dict(params)
        # ── Universal defaults / 通用默认值 ──
        selected.setdefault("threads", 1)
        selected.setdefault("database", "DATABASE_NOT_CONFIGURED")
        selected.setdefault("abricate_db", "card")
        selected.setdefault("env_name", self.env_name)
        selected.setdefault("mode", mode)
        selected.setdefault("minimap2_preset", "map-ont")
        selected.setdefault("project_root", str(PROJECT_ROOT))
        selected.setdefault("abundance_label", "")
        # ── Derived output paths / 推导输出路径 ──
        # When both output_dir and sample_id are known, we can derive standard
        # output file paths (alignment, BAM, abundance) so individual tools
        # don't need to duplicate this logic. / 已知输出目录和样本 ID 时可推导标准输出路径
        if selected.get("output_dir") and selected.get("sample_id"):
            output_dir = Path(str(selected["output_dir"]))
            sample_id = str(selected["sample_id"])
            label = str(selected.get("abundance_label", ""))
            selected.setdefault("alignment", str(output_dir / f"{sample_id}{label}.sam"))
            selected.setdefault("bam", str(output_dir / f"{sample_id}{label}.bam"))
            selected.setdefault("abundance", str(output_dir / f"{sample_id}{label}.coverm.tsv"))
        # ── Auto-derive composite inputs from granular fields / 从细粒度字段自动推导复合输入 ──
        # Some tool contracts declare abstract input parameters (e.g. metaphlan_input)
        # that must be assembled from the concrete inputs the DAG provides
        # (read1, read2).  This avoids requiring every DAG node to duplicate
        # the composition logic. / 工具合约中的抽象参数从 DAG 提供的具体输入自动组装
        _derive_composite_params(selected)
        selected.setdefault(
            "auto_selection_reason",
            f"{self.name} parameters selected by {mode} mode",
        )
        return selected

    def command_text(self, params: Dict[str, Any]) -> str:
        """Render the command template as a string.

        Uses ``SafeFormatDict`` to handle missing template keys.
        In strict mode (``ABI_STRICT_TEMPLATES=1``), unknown keys raise
        ``MissingTemplateParamError``.  In lenient mode (default), they
        produce a WARNING and render as empty strings.
        """
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        fmt_dict = SafeFormatDict(
            _template_values(selected),
            tool_name=self.name,
        )
        return self.command_template.format_map(fmt_dict)

    def build_command(self, params: Dict[str, Any]) -> List[str]:
        """Render and tokenize the command into a list of strings.

        After rendering, inspects ``SafeFormatDict.missing_keys`` and logs
        a summary of all missing parameters for diagnostic purposes.
        """
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        fmt_dict = SafeFormatDict(
            _template_values(selected),
            tool_name=self.name,
        )
        template = self.command_template.format_map(fmt_dict)
        # Log a single summary line if any params were missing
        if fmt_dict.missing_keys:
            _logger.info(
                "%s: missing template params: %s",
                self.name,
                ", ".join(sorted(set(fmt_dict.missing_keys))),
            )
        try:
            tokens = shlex.split(template)
        except ValueError as exc:
            raise ToolError(f"{self.name}: could not parse command template: {exc}") from exc
        # S6: if any parameter value starts with "-", insert "--" after the
        # tool binary to prevent user-supplied values from being interpreted
        # as CLI flags by the tool.
        values = _template_values(selected)
        if any(
            isinstance(v, str) and str(v).startswith("-") for v in values.values()
        ) and _supports_option_stop(tokens):
            tokens.insert(1, "--")
        return tokens

    def _required_template_fields(self) -> List[str]:
        """Parse the command template and return all unique field names.

        Uses string.Formatter().parse() which extracts {field_name} references
        from format strings. Strips attribute/index suffixes (e.g. {x.y} → "x",
        {a[0]} → "a") so we check the root key. / 解析模板返回所有字段名。
        """
        fields: List[str] = []
        formatter = string.Formatter()
        for _, field_name, _, _ in formatter.parse(self.command_template):
            if field_name:
                # Strip .attr and [index] suffixes / 去除属性和索引后缀
                root = field_name.split(".", 1)[0].split("[", 1)[0]
                if root not in fields:
                    fields.append(root)
        return fields

    def _validate_template_params(self, params: Mapping[str, Any]) -> None:
        """Ensure all required template parameters have non-empty values.

        # When this runs / 执行时机
        Called inside run() AFTER validate_inputs() but BEFORE the subprocess,
        so missing template params are caught before the tool is invoked.
        / 在验证输入后、执行子进程前调用，提前捕获缺失参数。

        # Why not always validate? / 为什么不总是验证？
        Optional fields (OPTIONAL_TEMPLATE_FIELDS) are skipped, and
        "DATABASE_NOT_CONFIGURED" is treated as a valid sentinel for tools that
        don't need a database. / 可选字段和哨兵值被跳过。
        """
        missing = []
        for field_name in self._required_template_fields():
            if field_name in OPTIONAL_TEMPLATE_FIELDS:
                continue
            value = params.get(field_name)
            if value is None or value == "" or value == "DATABASE_NOT_CONFIGURED":
                missing.append(field_name)
        if missing:
            raise ToolError(
                f"{self.name}: command template parameters are not configured: "
                + ", ".join(sorted(missing))
            )

    def _check_dotted_fields(self) -> None:
        """Raise ToolError if the command template uses unsupported dotted field refs.

        SafeFormatDict resolves ``{key}`` references but Python's ``str.format_map``
        interprets ``{key.attr}`` as attribute access on the resolved value, which
        would fail with ``AttributeError`` because ABI params are plain strings.
        This check catches such templates at validation time with a clear message.
        / SafeFormatDict 能解析 {key} 但不能解析 {key.attr}，此检查提前捕获。
        """
        dotted: List[str] = []
        formatter = string.Formatter()
        for _, field_name, _, _ in formatter.parse(self.command_template):
            if field_name and ("." in field_name or "[" in field_name):
                dotted.append(field_name)
        if dotted:
            raise ToolError(
                f"{self.name}: command template contains unsupported dotted/indexed field "
                f"references: {', '.join(sorted(dotted))}. "
                f"Use simple {{field_name}} references instead of {{field.attr}} or "
                f"{{field[index]}}."
            )

    def _command_without_stdout_redirect(
        self, command: List[str]
    ) -> tuple[List[str], Optional[Path]]:
        """Separate stdout redirection from the command token list.

        # Motivation / 动机
        command_template strings often end with `> {output_file}`.  We cannot
        pass ">" to subprocess.run() as part of the token list — it only works
        with shell=True.  Instead, we strip the ">" and target from the command
        and pass the target as a file handle to subprocess.run()'s stdout kwarg.
        / 将 ">" 重定向从命令中分离，避免使用 shell=True。

        Returns (cleaned_command, target_path_or_None). / 返回清理后的命令和重定向路径。
        """
        if ">" not in command:
            return command, None
        index = command.index(">")
        if index + 1 >= len(command):
            raise ToolError(f"{self.name}: stdout redirection is missing a target path")
        target = Path(command[index + 1])
        # Remove ">" AND the target path from the command / 从命令中移除 ">" 和目标路径
        cleaned = command[:index] + command[index + 2 :]
        if ">" in cleaned:
            raise ToolError(f"{self.name}: multiple stdout redirections are not supported")
        return cleaned, target

    def run(self, params: Dict[str, Any], dry_run: bool = False) -> RunResult:
        """Execute the tool command and return the result.

        # Execution flow / 执行流程
        1. select_params() — merge defaults / 合并默认参数
        2. validate_inputs() — check input files exist / 验证输入文件
        3. _validate_template_params() — check template fields populated / 验证模板字段
        4. check_installation() — verify binary exists / 验证二进制文件
        5. build_command() — render and tokenize / 渲染并分词
        6. _command_without_stdout_redirect() — handle > redirect / 处理重定向
        7. subprocess.run() — execute with timeout / 带超时执行
        8. Return RunResult — immutable result record / 返回不可变结果

        # Timeout handling / 超时处理
        Timeout is configured via `timeout_seconds` param or the
        ABI_TOOL_TIMEOUT_SECONDS env var.  On timeout, RunResult.status is
        "timeout" and return_code is -1. / 超时时 status="timeout", return_code=-1。
        """
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        self.validate_inputs({**selected, "dry_run": dry_run})
        # Full validation only for real runs / 实际运行才做完整验证
        if not dry_run:
            self._check_dotted_fields()
            self._validate_template_params(selected)
            if not self.check_installation():
                raise ToolError(
                    f"{self.name}: executable {self.executable!r} was not found in "
                    f"{self.env_bin} or PATH"
                )
        command = self.build_command(selected)
        start = datetime.now()
        # ── Dry-run: skip execution, return immediately / 试运行：跳过执行 ──
        if dry_run:
            end = datetime.now()
            return RunResult(
                tool_name=self.name,
                command=command,
                return_code=0,
                stdout="",
                stderr="",
                start_time=start.isoformat(timespec="seconds"),
                end_time=end.isoformat(timespec="seconds"),
                duration_seconds=0.0,
                outputs=dict(selected.get("outputs", {})),
                status="dry_run",
                resolved_params=dict(selected),
            )

        # ── Real execution / 实际执行 ──
        # Strip stdout redirection from command and get target path / 去掉重定向获取目标路径
        executable_command, redirected_stdout = self._command_without_stdout_redirect(command)
        stdout_path = redirected_stdout or (
            Path(str(selected["stdout_path"])) if selected.get("stdout_path") else None
        )
        stderr_path = Path(str(selected["stderr_path"])) if selected.get("stderr_path") else None
        # S4: validate redirected_stdout stays within the output directory.
        # provider-generated stdout_path/stderr_path (provenance/step_logs/) are
        # always safe — only validate redirected_stdout from the command template.
        _output_dir = (
            Path(str(selected["output_dir"])).resolve() if selected.get("output_dir") else None
        )
        if _output_dir:
            if redirected_stdout:
                stdout_path = _safe_output_path(stdout_path, _output_dir)
            # stdout_path from selected["stdout_path"] and stderr_path are
            # ABI-internal paths — skip validation for those.
        stdout_handle = None
        stderr_handle = None
        timeout_seconds = self._timeout_seconds(selected)
        # Track timeout state outside try/finally so finally block can use it / finally 块需要访问
        timed_out = False
        timeout_message = ""
        timeout_stdout = ""
        try:
            # Open output file handles if paths are configured / 打开输出文件句柄
            if stdout_path:
                stdout_path.parent.mkdir(parents=True, exist_ok=True)
                stdout_handle = stdout_path.open("w", encoding="utf-8")
            if stderr_path:
                stderr_path.parent.mkdir(parents=True, exist_ok=True)
                stderr_handle = stderr_path.open("w", encoding="utf-8")
            completed = subprocess.run(
                executable_command,
                check=False,  # We handle return codes ourselves / 自己处理返回码
                text=True,
                stdout=stdout_handle if stdout_handle else subprocess.PIPE,
                stderr=stderr_handle if stderr_handle else subprocess.PIPE,
                env=self.runtime_env(),
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            timeout_message = _timeout_message(self.name, timeout_seconds, exc)
            timeout_stdout = _timeout_output(exc.stdout)
        finally:
            # Always close file handles to flush buffers / 总是关闭文件句柄刷新缓冲
            if stdout_handle:
                stdout_handle.close()
            if stderr_handle:
                stderr_handle.close()
        end = datetime.now()
        # ── Build result / 构建结果 ──
        if timed_out:
            status = "timeout"
            return_code = -1
            stdout = "" if stdout_path else timeout_stdout
            stderr = "" if stderr_path else timeout_message
        else:
            status = "success" if completed.returncode == 0 else "failed"
            return_code = completed.returncode
            # If output was redirected to a file, captions are empty / 输出重定向到文件则捕获为空
            stdout = "" if stdout_path else completed.stdout
            stderr = "" if stderr_path else completed.stderr
        return RunResult(
            tool_name=self.name,
            command=command,
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
            start_time=start.isoformat(timespec="seconds"),
            end_time=end.isoformat(timespec="seconds"),
            duration_seconds=(end - start).total_seconds(),
            outputs={
                **dict(selected.get("outputs", {})),
                **({"stdout_path": str(stdout_path)} if stdout_path else {}),
                **({"stderr_path": str(stderr_path)} if stderr_path else {}),
            },
            status=status,
            resolved_params=dict(selected),
        )

    def _timeout_seconds(self, selected: Mapping[str, Any]) -> float | None:
        """Resolve the timeout for this tool invocation.

        # Resolution order / 解析顺序
        1. User-provided `timeout_seconds` in step params / 用户步骤参数
        2. Tool-level `timeout_seconds` in YAML metadata / YAML 元数据
        3. ABI_TOOL_TIMEOUT_SECONDS environment variable / 环境变量
        4. DEFAULT_TOOL_TIMEOUT_SECONDS constant (hard-coded fallback) / 硬编码兜底

        Returns None if no timeout should be applied (subprocess waits forever).
        / 返回 None 表示不设超时。
        """
        value = selected.get("timeout_seconds", self.metadata.get("timeout_seconds"))
        return timeout_from_env_or_value(
            "ABI_TOOL_TIMEOUT_SECONDS",
            value,
            default=DEFAULT_TOOL_TIMEOUT_SECONDS,
        )

    def capture_version(self) -> str:
        """Capture the tool's version string from ``version_command`` metadata (B5/B2 fix).

        Resolution order:
        1. If ``mock_tools`` is set, return ``"mock"``.
        2. If ``version_command`` is not configured, return ``""`` (not captured).
        3. Run the command via subprocess (list form, no shell) with a 10-second timeout.
        4. If ``version_regex`` is configured, extract the first capture group.
        5. On failure, return a diagnostic string (non-fatal).

        The ``version_regex`` field in the tool contract YAML uses Python
        regex syntax.  Example:
            version_command: "fastp --version"
            version_regex: "fastp\\\\s+(\\\\d+\\\\.\\\\d+\\\\.\\\\d+)"

        .. note::

            ``version_command`` is split via ``shlex.split()`` and run as a
            token list (no ``shell=True``) to prevent command injection through
            compromised YAML tool contracts (S1/S2 fix).
        """
        if self.metadata.get("mock_tools"):
            return "mock"
        version_cmd_str = str(self.metadata.get("version_command", ""))
        if not version_cmd_str:
            return ""
        try:
            version_cmd_list = shlex.split(version_cmd_str)
        except ValueError:
            return "version_command_parse_error"
        try:
            result = subprocess.run(
                version_cmd_list,
                capture_output=True,
                text=True,
                timeout=int(self.metadata.get("version_timeout", 10)),
                env=self.runtime_env(),
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode != 0:
                return f"version_command_failed(exit={result.returncode})"
            # Apply version_regex if configured (B2)
            regex = str(self.metadata.get("version_regex", ""))
            if regex:
                m = re.search(regex, output)
                if m:
                    return m.group(1)
                return f"regex_unmatched:{output[:80]}"
            return output[:120]
        except subprocess.TimeoutExpired:
            return "version_command_timeout"
        except Exception as exc:
            return f"version_command_error:{exc}"

    def parse_outputs(self, output_dir: str) -> Dict[str, Any]:
        """Discover output files by scanning the output directory.

        The default implementation is a simple glob — subclasses for tools with
        complex output structures (e.g. multiple subdirectories, specific file
        patterns) should override this. / 默认 glob 扫描，复杂输出结构的工具应覆盖此方法。
        """
        files = sorted(str(path) for path in Path(output_dir).glob("*"))
        return {"output_dir": output_dir, "files": files}

    def normalize_outputs(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Return parsed outputs unchanged (identity transform).

        Subclasses override this to remap field names, filter files, or add
        computed values. / 子类可覆盖以重新映射字段名或添加计算值。
        """
        return dict(parsed)


# ── ToolRegistry ───────────────────────────────────────────────────────
# Registry that loads tool definitions from a YAML file (tool_registry.yaml)
# and provides lookup, creation, and health-check operations.
#
# YAML 工具注册表，从 tool_registry.yaml 加载工具定义，提供查找、创建和健康检查操作。


class ToolRegistry:
    """YAML-based tool registry with resource checking.

    # Responsibilities / 职责
    1. Load and validate tool_registry.yaml at startup. / 加载并验证 YAML
    2. Provide O(1) lookups by tool_id. / O(1) 查找
    3. Create GenericCommandSkill instances on demand (factory pattern). / 工厂模式创建实例
    4. Check tool installation status and resource availability. / 检查安装和资源状态

    # Why a registry and not just dict? / 为什么用注册表而非简单 dict？
    - Validation at load time (duplicate IDs, missing required fields). / 加载时验证
    - Factory method (create()) injects mock_tools flag uniformly. / 工厂方法统一注入
    - check_tools() provides a health-check summary consumed by the CLI. / 健康检查供 CLI 使用

    # Thread safety / 线程安全
    The registry is read-only after construction (the _tools dict is never
    mutated after __init__), so it is safe to share across threads without
    locking. / 构造后只读，线程安全。
    """

    _env_assignments: dict[str, dict[str, str]] | None = None
    """Cache: plugin_name → {tool_id → env_name} loaded from environments.yaml."""

    def __init__(
        self,
        tools: Iterable[Mapping[str, Any]],
        *,
        environments_path: str | Path | None = None,
        plugin_name: str = "_default",
    ) -> None:
        """Build the registry from an iterable of tool definition dicts.

        # env_name resolution / 环境名称解析
        If *environments_path* points to a valid environments.yaml, the
        ``tool_assignments`` section is loaded and used to fill in ``env_name``
        for any tool that does not already declare one in its registry YAML.
        *plugin_name* selects the per-plugin subsection in tool_assignments.
        / 从 environments.yaml 自动补齐缺失的 env_name。
        """
        self._plugin = plugin_name

        # Load tool→env assignments from environments.yaml (once)
        if ToolRegistry._env_assignments is None and environments_path is not None:
            ToolRegistry._load_environment_assignments(environments_path)

        self._tools: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            tool_id = str(tool.get("id", "")).strip()
            if not tool_id:
                raise ConfigError("tool_registry.yaml contains a tool without id")
            if tool_id in self._tools:
                raise ConfigError(f"Duplicate tool id in registry: {tool_id}")
            tool_dict = dict(tool)
            # Auto-fill env_name from environments.yaml if missing
            if not tool_dict.get("env_name") and ToolRegistry._env_assignments:
                resolved = ToolRegistry.env_for(tool_id, plugin_name=plugin_name)
                if resolved and resolved != "abi-base":
                    tool_dict["env_name"] = resolved
            self._tools[tool_id] = tool_dict

    @classmethod
    def from_path(cls, path: str | Path | None = None) -> "ToolRegistry":
        """Load the registry from a YAML file on disk.

        Automatically looks for ``environments.yaml`` in the project root to
        resolve ``env_name`` for tools that do not declare it in their registry
        YAML.  The plugin name is auto-detected from the path
        (``plugins/<name>/tool_registry.yaml``). / 自动从 environments.yaml 解析 env_name。
        """
        if path is None:
            raise ConfigError("ToolRegistry.from_path requires an explicit path")
        registry_path = Path(path)
        if not registry_path.exists():
            raise ConfigError(f"Tool registry does not exist: {registry_path}")
        with registry_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        tools = data.get("tools")
        if not isinstance(tools, list):
            raise ConfigError("tool_registry.yaml must contain a tools list")

        # Auto-detect plugin name from path
        plugin = registry_path.parent.name if "plugins" in str(registry_path) else "_default"
        if plugin == "config":
            plugin = "_default"

        # Auto-detect environments.yaml for env_name resolution
        env_path = registry_path.parent.parent / "environments.yaml"
        if not env_path.exists():
            env_path = PROJECT_ROOT / "environments.yaml"

        return cls(
            tools,
            environments_path=env_path if env_path.exists() else None,
            plugin_name=plugin,
        )

    @classmethod
    def _load_environment_assignments(cls, path: str | Path) -> None:
        """Load tool→env assignments from environments.yaml (idempotent cache).

        Called once by __init__; subsequent calls are no-ops because the
        result is stored in the class-level ``_env_assignments`` cache.
        Supports both flat ``{tool_id: env}`` and nested
        ``{plugin: {tool_id: env}}`` formats.
        / 从 environments.yaml 加载工具→环境映射，结果缓存于类变量。
        """
        if cls._env_assignments is not None:
            return
        env_file = Path(path)
        if not env_file.exists():
            return
        data = yaml.safe_load(env_file.read_text(encoding="utf-8")) or {}
        raw = data.get("tool_assignments", {})
        # Detect format: if top-level values are dicts, it's plugin-qualified
        if raw and isinstance(next(iter(raw.values())), dict):
            cls._env_assignments = {
                str(plugin): {str(k): str(v) for k, v in tools.items()}
                for plugin, tools in raw.items()
            }
        else:
            # Flat format — all tools go under a default plugin key
            cls._env_assignments = {"_default": {str(k): str(v) for k, v in raw.items()}}

    @classmethod
    def env_for(
        cls,
        tool_id: str,
        *,
        plugin_name: str | None = None,
        plugin: str | None = None,
    ) -> str:
        """Resolve the conda environment name for *tool_id*.

        Prefer an explicit ``plugin_name`` (``plugin`` is kept as a legacy
        alias), then fall back to ``_default``. Returns ``"abi-base"`` when no
        assignment is known; plugin-qualified lookups never search other
        plugin maps implicitly.
        """
        if cls._env_assignments is None:
            return "abi-base"

        selected_plugin = plugin_name if plugin_name is not None else plugin
        plugin_map = cls._env_assignments.get(selected_plugin, {}) if selected_plugin else {}
        if plugin_map and tool_id in plugin_map:
            return plugin_map[tool_id]

        default_map = cls._env_assignments.get("_default", {})
        if tool_id in default_map:
            return default_map[tool_id]
        return "abi-base"

    def ids(self) -> List[str]:
        """Return sorted tool IDs for stable iteration order.

        # Why sorted? / 为什么排序？
        Deterministic ordering is important for CLI output, reports, and tests.
        Without sorting, dict iteration order (which IS insertion-ordered in
        Python 3.7+) could vary across registry files. / 确定性顺序对 CLI 和测试很重要。
        """
        return sorted(self._tools)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return all tool metadata dicts in sorted id order.

        Returns a list (not a generator) so callers can iterate multiple times.
        / 返回列表而非生成器，调用者可多次遍历。
        """
        return [self._tools[tool_id] for tool_id in self.ids()]

    def get(self, tool_id: str) -> Dict[str, Any]:
        """Look up a tool's metadata dict by id. Raises ConfigError if not found.

        # Fail-fast / 快速失败
        Raises ConfigError immediately rather than returning None, so callers
        don't need to null-check and the error message includes the missing id.
        / 立即报错而非返回 None，调用者无需空值检查。
        """
        if tool_id not in self._tools:
            raise ConfigError(f"Tool {tool_id!r} is not registered")
        return self._tools[tool_id]

    def has(self, tool_id: str) -> bool:
        """Check if a tool id is registered (safe for conditionals). / 安全检查工具是否注册。"""
        return tool_id in self._tools

    def create(self, tool_id: str, *, mock_tools: bool = False) -> GenericCommandSkill:
        """Factory: create a GenericCommandSkill from the tool's metadata.

        # Why a factory method? / 为什么用工厂方法？
        - Centralizes the mock_tools injection (every skill created in test
          mode gets this flag uniformly). / 统一注入 mock_tools 标志
        - Copies the metadata dict to prevent mutations from leaking back
          into the registry. / 复制元数据防止修改泄漏回注册表
        """
        metadata = dict(self.get(tool_id))
        metadata["mock_tools"] = mock_tools
        return GenericCommandSkill(metadata)

    def check_tools(
        self, *, mock_tools: bool = False, config: Mapping[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """Health-check all registered tools and return a status summary.

        # What this checks / 检查内容
        1. Is the tool binary installed and findable? / 工具二进制是否可找到？
        2. Are required resource files (databases, models, indexes) present?
           / 资源文件是否存在？

        Returns a list of dicts suitable for rendering as a table or JSON.
        / 返回字典列表，适合渲染为表格或 JSON。

        # Why does this exist separately from check_installation()? / 为什么独立存在？
        check_installation() checks one tool. check_tools() iterates over all
        tools and also checks resource availability, producing a machine-readable
        summary consumed by `abi check` and dashboard views. / 批量检查并检查资源。
        """
        rows: List[Dict[str, Any]] = []
        for metadata in self.list_tools():
            skill = self.create(str(metadata["id"]), mock_tools=mock_tools)
            installed = skill.check_installation()
            resource_status, resource_details = _resource_status(metadata, config or {})
            rows.append(
                {
                    "tool_id": metadata["id"],
                    "name": metadata.get("name", metadata["id"]),
                    "category": metadata.get("category", ""),
                    "required": bool(metadata.get("required", False)),
                    "default_enabled": bool(metadata.get("default_enabled", False)),
                    "env_name": metadata.get("env_name", ""),
                    "executable": metadata.get("executable", ""),
                    "installed": installed,
                    "resource_status": resource_status,
                    "resources": resource_details,
                    "status": "ok" if installed else "missing",
                }
            )
        return rows


# ── Internal helpers ───────────────────────────────────────────────────
# Package-private utilities for template rendering, timeout handling, and
# resource validation. Not exported in __all__.
# 包内部工具函数，不被 __all__ 导出。


def _template_values(values: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively convert all values to template-safe strings.

    Applies _template_value() to each value in the mapping. / 将每个值转为模板安全字符串。
    """
    return {key: _template_value(value) for key, value in values.items()}


def _looks_like_path(value: str) -> bool:
    """Return True if *value* looks like a file path rather than a string parameter.

    Distinguishes file paths (``/data/reads.fastq.gz``, ``./sample.tsv``) from
    string parameters (``GTGCCAGCMGCCGCGGTAA``, ``8``, ``local``).  Used by
    ``validate_inputs`` to avoid checking DNA sequences and other non-path values.
    """
    if value.startswith("/") or value.startswith("./") or value.startswith("../"):
        return True
    path_exts = (
        ".fq",
        ".fastq",
        ".fa",
        ".fasta",
        ".fna",
        ".bam",
        ".sam",
        ".tsv",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".txt",
        ".gz",
        ".bz2",
        ".nwk",
        ".tree",
        ".R",
        ".py",
        ".sh",
    )
    if any(value.endswith(ext) for ext in path_exts):
        return True
    if "/" in value:
        return True
    return False


def _supports_option_stop(tokens: list[str]) -> bool:
    """Return True when ``--`` can be inserted after the executable token."""
    if len(tokens) <= 1:
        return False
    executable = Path(tokens[0]).name
    if executable in {"sh", "bash"} and tokens[1] == "-c":
        return False
    return True


def _safe_output_path(path: Path | None, output_dir: Path) -> Path | None:
    """Validate that *path* resolves inside *output_dir* (S4 fix).

    Raises ``ToolError`` if the resolved path escapes the output directory,
    preventing path-traversal attacks via user-controlled output paths.
    """
    if path is None:
        return None
    output_resolved = output_dir.resolve()
    if path.is_absolute():
        resolved = path.resolve()
    else:
        cwd_resolved = path.resolve()
        if (
            str(cwd_resolved).startswith(str(output_resolved) + os.sep)
            or cwd_resolved == output_resolved
        ):
            resolved = cwd_resolved
        else:
            resolved = (output_dir / path).resolve()
    if not (str(resolved).startswith(str(output_resolved) + os.sep) or resolved == output_resolved):
        raise ToolError(
            f"Output path {path!s} escapes output directory {output_dir}. Resolved to: {resolved}"
        )
    return resolved


def _template_value(value: Any) -> Any:
    """Convert a single value for safe insertion into a command template.

    # Why convert Path to POSIX? / 为什么要转 Path 为 POSIX 路径？
    On Windows, Path.as_posix() uses forward slashes, which are understood by
    most bioinformatics tools even on Windows (WSL, Git Bash, MSYS2). / 正斜杠
    在 Windows 上的生物信息工具中也能工作。

    # Why convert backslashes on Windows? / 为什么在 Windows 上转反斜杠？
    Backslashes in command templates would be interpreted as escape characters
    by shlex.split(), causing parse errors. / 反斜杠会被 shlex.split() 解释为转义字符。
    """
    if isinstance(value, Path):
        return value.as_posix()
    if os.name == "nt" and isinstance(value, str):
        return value.replace("\\", "/")
    return value


def _timeout_output(exc_stdout: Any) -> str:
    """Safely decode stderr/stdout captured from a TimeoutExpired exception.

    subprocess.TimeoutExpired stores captured output as bytes or str depending
    on whether text=True was used. This helper normalizes to str. / 统一解码为字符串。
    """
    if exc_stdout is None:
        return ""
    if isinstance(exc_stdout, bytes):
        return exc_stdout.decode("utf-8", errors="replace")
    return str(exc_stdout)


def _timeout_message(
    tool_name: str,
    timeout_seconds: float | None,
    exc: subprocess.TimeoutExpired,
) -> str:
    """Build a human-readable timeout error message.

    Includes the tool name, timeout value, and any stderr captured before the
    timeout. / 包含工具名、超时值和超时前捕获的 stderr。

    # Why ":g" format? / 为什么用 ":g" 格式？
    The ":g" format specifier removes trailing zeros (e.g. 3600.0 → "3600s"
    rather than "3600.0s"). / 去除尾随零使输出更整洁。
    """
    stderr = _timeout_output(exc.stderr)
    timeout_text = "configured timeout" if timeout_seconds is None else f"{timeout_seconds:g}s"
    message = f"{tool_name}: command timed out after {timeout_text}"
    # Include stderr only if non-empty for cleaner error messages / 仅 stderr 非空时才包含
    return "\n".join(text for text in [message, stderr.strip()] if text)


def _resource_status(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, Dict[str, str]]:
    """Check whether resource files (databases, models, indexes) are configured and exist.

    # Resource resolution logic / 资源解析逻辑
    1. Parse the tool's command_template to find resource field references
       (e.g. {database}, {model}, {refgraph}) via _resource_fields(). / 解析模板找资源引用
    2. Look up values in the pipeline config at two levels: / 两级查找
       - config.resources.<tool_id> — tool-specific resources / 工具级资源
       - config.resources — shared resources (applicable to all tools) / 共享资源
       - config.tool_params.<tool_id> — parameters that may include resource paths / 参数中
    3. For each field, check if a value is configured and if the path exists on disk.
       / 检查值是否配置且路径是否存在

    # Return values / 返回值
    - "ok": All resource fields are configured and paths exist. / 全部配置且存在
    - "missing": At least one configured path does not exist on disk. / 有路径不存在
    - "not_configured": At least one resource field has no value configured. / 有字段未配置
    - "not_required": No resource fields found in the template. / 模板中无资源字段

    Returns (status, details_dict) where details maps field_name → path or status.
    / 返回 (状态, 详情字典)，详情映射字段名到路径或状态。
    """
    # Extract resource field names from the command template / 从命令模板提取资源字段名
    fields = _resource_fields(str(metadata.get("command_template", "")))
    if not fields:
        return "not_required", {}

    tool_id = str(metadata.get("id", ""))
    resources = config.get("resources", {})
    tool_params = config.get("tool_params", {})
    configured: Dict[str, Any] = {}
    # Layer 1: tool-specific resource config / 第1层：工具级资源配置
    if isinstance(resources, Mapping):
        tool_resources = resources.get(tool_id, {})
        if isinstance(tool_resources, Mapping):
            configured.update(tool_resources)
        # Layer 2: shared/global resources (e.g. a common database path) / 第2层：共享资源
        for field in fields:
            if field in resources:
                configured[field] = resources[field]
    # Layer 3: tool_params may also contain resource paths / 第3层：工具参数中的资源路径
    if isinstance(tool_params, Mapping):
        tool_parameter_values = tool_params.get(tool_id, {})
        if isinstance(tool_parameter_values, Mapping):
            configured.update(tool_parameter_values)

    details: Dict[str, str] = {}
    missing = []
    not_configured = []
    for field in fields:
        value = configured.get(field)
        if not value:
            details[field] = "not_configured"
            not_configured.append(field)
            continue
        path = Path(str(value))
        if path.exists():
            details[field] = str(path)
        else:
            details[field] = f"missing:{path}"
            missing.append(field)

    if missing:
        return "missing", details
    if not_configured:
        return "not_configured", details
    return "ok", details


def _resource_fields(command_template: str) -> List[str]:
    """Parse a command template string and return resource-type field names.

    # What qualifies as a resource field? / 哪些字段算资源字段？
    Only field names listed in RESOURCE_FIELDS (database, model, refgraph, etc.)
    are returned.  Other template fields like {input}, {threads} are not resources
    and should not be checked for on-disk existence. / 只有 RESOURCE_FIELDS 中
    的字段被返回，其余字段不检查磁盘存在性。

    Uses string.Formatter().parse() to extract {field_name} references. / 使用
    Formatter.parse() 提取 {field_name} 引用。
    """
    fields: List[str] = []
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(command_template):
        if not field_name:
            continue
        # Strip .attr and [index] suffixes to get the root key / 去后缀得根键
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root in RESOURCE_FIELDS and root not in fields:
            fields.append(root)
    return fields
