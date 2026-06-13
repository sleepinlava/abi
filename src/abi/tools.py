"""Tool skill base classes and registry loader for ABI plugins."""

from __future__ import annotations

import os
import shlex
import shutil
import string
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from abi.config import PROJECT_ROOT, resolved_mamba_root
from abi.errors import ConfigError, ToolError
from abi.timeouts import DEFAULT_TOOL_TIMEOUT_SECONDS, timeout_from_env_or_value

__all__ = [
    "GenericCommandSkill",
    "RunResult",
    "ToolRegistry",
    "ToolSkill",
]

OPTIONAL_TEMPLATE_FIELDS = {"abundance_label", "metaphlan_long_reads_flag"}
RESOURCE_FIELDS = {
    "database",
    "model",
    "refgraph",
    "ref_list",
    "plasmid_index",
    "annotations",
    "gene_calls",
    "reference",
    "genome_index",
    "annotation_gtf",
}


# ── RunResult ──────────────────────────────────────────────────────────


@dataclass
class RunResult:
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── ToolSkill (abstract base) ──────────────────────────────────────────


class ToolSkill:
    name: str
    version: Optional[str]
    env_name: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    def check_installation(self) -> bool:
        raise NotImplementedError

    def plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def validate_inputs(self, params: Dict[str, Any]) -> None:
        raise NotImplementedError

    def select_params(self, params: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
        raise NotImplementedError

    def build_command(self, params: Dict[str, Any]) -> List[str]:
        raise NotImplementedError

    def run(self, params: Dict[str, Any], dry_run: bool = False) -> RunResult:
        raise NotImplementedError

    def parse_outputs(self, output_dir: str) -> Dict[str, Any]:
        raise NotImplementedError

    def normalize_outputs(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def dry_run(self, params: Dict[str, Any]) -> RunResult:
        return self.run(params, dry_run=True)


# ── GenericCommandSkill ────────────────────────────────────────────────


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


class GenericCommandSkill(ToolSkill):
    """Generic command-template wrapper for registered command-line tools."""

    def __init__(self, metadata: Mapping[str, Any]) -> None:
        self.metadata = dict(metadata)
        self.name = str(metadata["id"])
        self.version = None
        self.env_name = str(metadata.get("env_name", "abi-base"))
        self.input_schema = {"inputs": metadata.get("inputs", [])}
        self.output_schema = {"outputs": metadata.get("outputs", [])}

    @property
    def executable(self) -> str:
        return str(self.metadata.get("executable") or self.name)

    @property
    def command_template(self) -> str:
        template = self.metadata.get("command_template")
        if template:
            return str(template)
        return f"{self.executable} --input {{input}} --output {{output_dir}} --threads {{threads}}"

    @property
    def mamba_root(self) -> Path:
        return resolved_mamba_root()

    @property
    def env_prefix(self) -> Path:
        return self.mamba_root / "envs" / self.env_name

    @property
    def env_bin(self) -> Path:
        return self.env_prefix / "bin"

    def runtime_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if self.env_bin.exists():
            env["PATH"] = f"{self.env_bin}{os.pathsep}{env.get('PATH', '')}"
            env["CONDA_PREFIX"] = str(self.env_prefix)
            env["MAMBA_ROOT_PREFIX"] = str(self.mamba_root)
            env.pop("PYTHONPATH", None)
        return env

    def check_installation(self) -> bool:
        if self.metadata.get("mock_tools"):
            return True
        executable_path = Path(self.executable)
        if executable_path.is_absolute() or executable_path.parent != Path("."):
            return executable_path.exists()
        if not self.env_bin.exists():
            return False
        return shutil.which(self.executable, path=str(self.env_bin)) is not None

    def plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        return {
            "tool_name": self.name,
            "env_name": self.env_name,
            "command": self.build_command(selected),
            "outputs": selected.get("outputs", {}),
        }

    def validate_inputs(self, params: Dict[str, Any]) -> None:
        missing: List[str] = []
        for key in self.metadata.get("inputs", []):
            value = params.get(key)
            if value and not Path(str(value)).exists():
                missing.append(f"{key}={value}")
        if missing and not params.get("dry_run", False):
            raise ToolError(f"{self.name}: input files do not exist: {', '.join(missing)}")

    def select_params(self, params: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
        selected = dict(params)
        selected.setdefault("threads", 1)
        selected.setdefault("database", "DATABASE_NOT_CONFIGURED")
        selected.setdefault("abricate_db", "card")
        selected.setdefault("env_name", self.env_name)
        selected.setdefault("mode", mode)
        selected.setdefault("minimap2_preset", "map-ont")
        selected.setdefault("project_root", str(PROJECT_ROOT))
        selected.setdefault("abundance_label", "")
        if selected.get("output_dir") and selected.get("sample_id"):
            output_dir = Path(str(selected["output_dir"]))
            sample_id = str(selected["sample_id"])
            label = str(selected.get("abundance_label", ""))
            selected.setdefault("alignment", str(output_dir / f"{sample_id}{label}.sam"))
            selected.setdefault("bam", str(output_dir / f"{sample_id}{label}.bam"))
            selected.setdefault("abundance", str(output_dir / f"{sample_id}{label}.coverm.tsv"))
        selected.setdefault(
            "auto_selection_reason",
            f"{self.name} parameters selected by {mode} mode",
        )
        return selected

    def command_text(self, params: Dict[str, Any]) -> str:
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        return self.command_template.format_map(SafeFormatDict(_template_values(selected)))

    def build_command(self, params: Dict[str, Any]) -> List[str]:
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        template = self.command_text(selected)
        try:
            return shlex.split(template)
        except ValueError as exc:
            raise ToolError(f"{self.name}: could not parse command template: {exc}") from exc

    def _required_template_fields(self) -> List[str]:
        fields: List[str] = []
        formatter = string.Formatter()
        for _, field_name, _, _ in formatter.parse(self.command_template):
            if field_name:
                root = field_name.split(".", 1)[0].split("[", 1)[0]
                if root not in fields:
                    fields.append(root)
        return fields

    def _validate_template_params(self, params: Mapping[str, Any]) -> None:
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

    def _command_without_stdout_redirect(
        self, command: List[str]
    ) -> tuple[List[str], Optional[Path]]:
        if ">" not in command:
            return command, None
        index = command.index(">")
        if index + 1 >= len(command):
            raise ToolError(f"{self.name}: stdout redirection is missing a target path")
        target = Path(command[index + 1])
        cleaned = command[:index] + command[index + 2 :]
        if ">" in cleaned:
            raise ToolError(f"{self.name}: multiple stdout redirections are not supported")
        return cleaned, target

    def run(self, params: Dict[str, Any], dry_run: bool = False) -> RunResult:
        selected = self.select_params(params, mode=str(params.get("mode", "auto")))
        self.validate_inputs({**selected, "dry_run": dry_run})
        if not dry_run:
            self._validate_template_params(selected)
            if not self.check_installation():
                raise ToolError(
                    f"{self.name}: executable {self.executable!r} was not found in "
                    f"{self.env_bin} or PATH"
                )
        command = self.build_command(selected)
        start = datetime.now()
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
            )

        executable_command, redirected_stdout = self._command_without_stdout_redirect(command)
        stdout_path = redirected_stdout or (
            Path(str(selected["stdout_path"])) if selected.get("stdout_path") else None
        )
        stderr_path = Path(str(selected["stderr_path"])) if selected.get("stderr_path") else None
        stdout_handle = None
        stderr_handle = None
        timeout_seconds = self._timeout_seconds(selected)
        timed_out = False
        timeout_message = ""
        timeout_stdout = ""
        try:
            if stdout_path:
                stdout_path.parent.mkdir(parents=True, exist_ok=True)
                stdout_handle = stdout_path.open("w", encoding="utf-8")
            if stderr_path:
                stderr_path.parent.mkdir(parents=True, exist_ok=True)
                stderr_handle = stderr_path.open("w", encoding="utf-8")
            completed = subprocess.run(
                executable_command,
                check=False,
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
            if stdout_handle:
                stdout_handle.close()
            if stderr_handle:
                stderr_handle.close()
        end = datetime.now()
        if timed_out:
            status = "timeout"
            return_code = -1
            stdout = "" if stdout_path else timeout_stdout
            stderr = "" if stderr_path else timeout_message
        else:
            status = "success" if completed.returncode == 0 else "failed"
            return_code = completed.returncode
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
        )

    def _timeout_seconds(self, selected: Mapping[str, Any]) -> float | None:
        value = selected.get("timeout_seconds", self.metadata.get("timeout_seconds"))
        return timeout_from_env_or_value(
            "ABI_TOOL_TIMEOUT_SECONDS",
            value,
            default=DEFAULT_TOOL_TIMEOUT_SECONDS,
        )

    def parse_outputs(self, output_dir: str) -> Dict[str, Any]:
        files = sorted(str(path) for path in Path(output_dir).glob("*"))
        return {"output_dir": output_dir, "files": files}

    def normalize_outputs(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        return dict(parsed)


# ── ToolRegistry ───────────────────────────────────────────────────────


class ToolRegistry:
    def __init__(self, tools: Iterable[Mapping[str, Any]]) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            tool_id = str(tool.get("id", "")).strip()
            if not tool_id:
                raise ConfigError("tool_registry.yaml contains a tool without id")
            if tool_id in self._tools:
                raise ConfigError(f"Duplicate tool id in registry: {tool_id}")
            self._tools[tool_id] = dict(tool)

    @classmethod
    def from_path(cls, path: str | Path | None = None) -> "ToolRegistry":
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
        return cls(tools)

    def ids(self) -> List[str]:
        return sorted(self._tools)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [self._tools[tool_id] for tool_id in self.ids()]

    def get(self, tool_id: str) -> Dict[str, Any]:
        if tool_id not in self._tools:
            raise ConfigError(f"Tool {tool_id!r} is not registered")
        return self._tools[tool_id]

    def has(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def create(self, tool_id: str, *, mock_tools: bool = False) -> GenericCommandSkill:
        metadata = dict(self.get(tool_id))
        metadata["mock_tools"] = mock_tools
        return GenericCommandSkill(metadata)

    def check_tools(
        self, *, mock_tools: bool = False, config: Mapping[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
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


def _template_values(values: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: _template_value(value) for key, value in values.items()}


def _template_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if os.name == "nt" and isinstance(value, str):
        return value.replace("\\", "/")
    return value


def _timeout_output(exc_stdout: Any) -> str:
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
    stderr = _timeout_output(exc.stderr)
    timeout_text = "configured timeout" if timeout_seconds is None else f"{timeout_seconds:g}s"
    message = f"{tool_name}: command timed out after {timeout_text}"
    return "\n".join(text for text in [message, stderr.strip()] if text)


def _resource_status(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, Dict[str, str]]:
    fields = _resource_fields(str(metadata.get("command_template", "")))
    if not fields:
        return "not_required", {}

    tool_id = str(metadata.get("id", ""))
    resources = config.get("resources", {})
    tool_params = config.get("tool_params", {})
    configured: Dict[str, Any] = {}
    if isinstance(resources, Mapping):
        tool_resources = resources.get(tool_id, {})
        if isinstance(tool_resources, Mapping):
            configured.update(tool_resources)
        for field in fields:
            if field in resources:
                configured[field] = resources[field]
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
    fields: List[str] = []
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(command_template):
        if not field_name:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root in RESOURCE_FIELDS and root not in fields:
            fields.append(root)
    return fields
