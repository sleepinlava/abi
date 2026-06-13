"""Base classes for bioinformatics tool skill wrappers."""

from __future__ import annotations

import os
import shlex
import shutil
import string
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from abi.plugins.metagenomic_plasmid._engine.config import PROJECT_ROOT, resolved_mamba_root
from abi.plugins.metagenomic_plasmid._engine.schemas import ToolError
from abi.plugins.metagenomic_plasmid._engine.timeouts import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    timeout_from_env_or_value,
)

OPTIONAL_TEMPLATE_FIELDS = {"abundance_label", "metaphlan_long_reads_flag"}


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


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


class GenericCommandSkill(ToolSkill):
    """Generic command-template wrapper for registered command-line tools."""

    def __init__(self, metadata: Mapping[str, Any]) -> None:
        self.metadata = dict(metadata)
        self.name = str(metadata["id"])
        self.version = None
        self.env_name = str(metadata.get("env_name", "autoplasm-base"))
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
            "AUTOPLASM_TOOL_TIMEOUT_SECONDS",
            value,
            default=DEFAULT_TOOL_TIMEOUT_SECONDS,
        )

    def parse_outputs(self, output_dir: str) -> Dict[str, Any]:
        files = sorted(str(path) for path in Path(output_dir).glob("*"))
        return {"output_dir": output_dir, "files": files}

    def normalize_outputs(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        return dict(parsed)


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
