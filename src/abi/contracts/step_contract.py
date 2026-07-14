"""Step-level contract enforcement for ABI pipeline execution.

This module implements the runtime contract verification layer that sits
between tool execution and provenance recording.  Each step's outputs are
validated against the contracts declared in ``pipeline_dag.yaml``.

Design / 设计
--------------

**Three-phase verification per step:**

1. **Pre-execution** — verify that input files exist and (when checksum chain
   is enabled) their SHA256 matches the upstream record.

2. **Post-execution** — validate that declared output files exist, pass size /
   format checks, and satisfy per-node assertions.

3. **Checksum recording** — compute SHA256 for each output file and persist
   to ``provenance/checksums.json`` so downstream steps can verify.

**Contract violation response:**
When a contract check fails, the step is marked ``"contract_violation"``
and a ``ContractViolationError`` is raised with structured diagnostic
information — which violation, expected vs actual values, and suggested
recovery action.  Downstream steps are blocked.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from abi.errors import ABIError

# ═══════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ContractViolation:
    """A single contract check failure with diagnostic detail."""

    check: str  # e.g. "file_exists", "min_size", "assertion", "checksum_mismatch"
    detail: str  # human-readable description
    path: str = ""  # the file/field that failed
    expected: str = ""
    actual: str = ""


@dataclass
class StepContractResult:
    """Aggregate result of all contract checks for one step."""

    passed: bool
    violations: List[ContractViolation] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=dict)  # path -> sha256


class ContractViolationError(ABIError):
    """Raised when a step's output contract is violated.

    Carries structured violation data so agents can diagnose and recover.
    """

    def __init__(self, step_id: str, violations: List[ContractViolation]) -> None:
        self.step_id = step_id
        self.violations = violations
        detail = "; ".join(f"{v.check}: {v.detail}" for v in violations[:5])
        if len(violations) > 5:
            detail += f" (+{len(violations) - 5} more)"
        super().__init__(f"Step {step_id!r} contract violated: {detail}")


# ═══════════════════════════════════════════════════════════════════════════
# Checksum persistence
# ═══════════════════════════════════════════════════════════════════════════

CHECKSUMS_FILENAME = "checksums.json"


def load_checksums(
    provenance_dir: str | Path,
    *,
    step_id: str = "",
    strict: bool | None = None,
) -> Dict[str, str]:
    """Load the recorded checksum map from a provenance directory.

    Args:
        provenance_dir: Path to the provenance directory.
        strict: If True, raise ContractViolation when ``checksums.json`` is
            missing.  Defaults to the ``ABI_REQUIRE_CHECKSUMS`` environment
            variable (S8 fix).

    Returns:
        Checksum map (file path → SHA256 hex string), or ``{}`` when the
        file is absent and strict mode is off.

    Raises:
        ContractViolationError: When strict mode is on and the file is missing.
    """
    if strict is None:
        strict = os.environ.get("ABI_REQUIRE_CHECKSUMS") == "1"
    path = Path(provenance_dir) / CHECKSUMS_FILENAME
    if not path.exists():
        if strict:
            raise ContractViolationError(
                step_id=step_id,
                violations=[
                    ContractViolation(
                        check="missing_checksums",
                        detail=f"Checksum file {path} required but not found. "
                        f"Set ABI_REQUIRE_CHECKSUMS=0 to skip this check.",
                        path=str(path),
                    )
                ],
            )
        import logging

        logging.getLogger("abi.contracts").warning(
            "checksums.json not found; input integrity not verified for this step"
        )
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return dict(json.load(fh))


def save_checksums(provenance_dir: str | Path, checksums: Dict[str, str]) -> Path:
    """Persist the checksum map atomically.

    Backward-compatible alias for :func:`save_checksums_atomic`; there is no
    longer a public path that writes ``checksums.json`` non-atomically.
    """
    return save_checksums_atomic(provenance_dir, checksums)


def save_checksums_atomic(provenance_dir: str | Path, checksums: Dict[str, str]) -> Path:
    """Persist checksums via tmp+rename for atomicity (B25 fix).

    Writes to a ``.tmp`` file, calls ``fsync()``, then uses ``os.replace()``
    which is atomic on POSIX filesystems.  On NFS, ``os.replace()`` is atomic
    for the directory entry but the data may not be durable without an fsync
    on the directory — for NFS safety, combine with ``B26`` (atomic_write).

    Merges with existing checksums identically to ``save_checksums()``.
    """
    existing = load_checksums(provenance_dir)
    existing.update(checksums)
    path = Path(provenance_dir) / CHECKSUMS_FILENAME
    tmp_path = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path


def invalidate_step_checksums(
    checksums: Dict[str, str],
    contract_spec: Mapping[str, Any] | None = None,
    *,
    output_paths: List[str] | None = None,
    output_dir: str | Path | None = None,
) -> None:
    """Remove checksums for outputs that a step will regenerate (B25 fix).

    Called before re-executing a step (retry / resume) so that stale
    checksums from a prior partial execution do not persist.

    Matching strategy (in order of preference):
    1. ``output_dir`` — removes any checksum whose key falls within this directory.
    2. ``output_paths`` — removes checksums matching exact output file paths.
    3. ``contract_spec`` — legacy heuristic: matches by output key name as a
       substring within checksum file paths.

    At least one of ``contract_spec``, ``output_paths``, or ``output_dir``
    should be provided.
    """
    to_remove: List[str] = []

    # Strategy 1: output directory (most robust)
    if output_dir is not None:
        dir_str = str(output_dir)
        for checksum_key in list(checksums):
            if checksum_key.startswith(dir_str) or checksum_key.startswith(str(Path(dir_str))):
                to_remove.append(checksum_key)

    # Strategy 2: exact output paths
    elif output_paths:
        path_set = {str(p) for p in output_paths}
        for checksum_key in list(checksums):
            if checksum_key in path_set:
                to_remove.append(checksum_key)

    # Strategy 3: heuristic by contract output key names
    elif contract_spec:
        output_spec = contract_spec.get("outputs", {})
        if output_spec:
            declared_output_names = set(output_spec.keys())
            for checksum_key in list(checksums):
                key_basename = Path(checksum_key).name
                key_parent = str(Path(checksum_key).parent)
                for output_name in declared_output_names:
                    # Match: output name appears in the checksum path or filename
                    if (
                        output_name in checksum_key
                        or output_name in key_basename
                        or output_name in key_parent
                    ):
                        to_remove.append(checksum_key)
                        break

    for key in set(to_remove):  # Deduplicate
        if key in checksums:
            del checksums[key]


# ═══════════════════════════════════════════════════════════════════════════
# Checksum computation
# ═══════════════════════════════════════════════════════════════════════════

_READ_SIZE = 65536  # 64 KiB chunks


def compute_file_checksum(path: str | Path, *, follow_symlinks: bool = True) -> str:
    """Compute the SHA256 hex digest of a file.

    Returns ``""`` if the file does not exist.

    When ``follow_symlinks=True`` (default), symbolic links are resolved to
    their target before hashing so the checksum reflects the actual content
    rather than the link path (B7 fix).
    """
    file_path = Path(path)
    if follow_symlinks and file_path.is_symlink():
        file_path = file_path.resolve()
    if not file_path.is_file():
        return ""
    sha = hashlib.sha256()
    with file_path.open("rb") as fh:
        while chunk := fh.read(_READ_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def compute_output_checksums(outputs: Mapping[str, Any]) -> Dict[str, str]:
    """Compute SHA256 for every output path that points to an existing file.

    Directories are skipped (they don't have a single checksum).
    Keys that hold non-path values are silently ignored.
    """
    checksums: Dict[str, str] = {}
    for key, value in outputs.items():
        if not isinstance(value, (str, Path)):
            continue
        path = Path(str(value))
        if not path.is_file():
            continue
        digest = compute_file_checksum(path)
        if digest:
            checksums[str(path)] = digest
    return checksums


# ═══════════════════════════════════════════════════════════════════════════
# Output contract validation
# ═══════════════════════════════════════════════════════════════════════════


def validate_output_contract(
    step_id: str,
    outputs: Mapping[str, Any],
    contract_spec: Optional[Mapping[str, Any]] = None,
) -> StepContractResult:
    """Validate that a step's outputs satisfy its declared contract.

    Checks performed (when the contract declares them):

    1. **file_exists** — every declared output path must exist on disk.
    2. **min_size** — files and directories must meet minimum size thresholds.
    3. **extensions** — files must have one of the declared extensions.
    4. **required_keys** — JSON output files must contain declared top-level keys.
    5. **schema** — JSON output sub-fields must match type and range constraints.

    Args:
        step_id: The step identifier (for error messages).
        outputs: The step's ``outputs`` dict (``{key: value}``).
        contract_spec: The ``outputs`` block from ``pipeline_dag.yaml``, or
            ``None`` to skip validation.

    Returns:
        A ``StepContractResult`` with ``passed=True`` if all checks pass.
    """
    if not contract_spec:
        return StepContractResult(passed=True)

    violations: List[ContractViolation] = []
    checksums: Dict[str, str] = {}

    for key, spec in contract_spec.items():
        if not isinstance(spec, Mapping):
            continue
        contract = spec.get("contract")
        if not isinstance(contract, Mapping):
            continue

        value = outputs.get(key)
        path_str = str(value) if value else ""
        file_path = Path(path_str) if path_str else None

        # ── file_exists ──
        if file_path is not None and not file_path.exists():
            violations.append(
                ContractViolation(
                    check="file_exists",
                    detail=f"Output {key!r} does not exist",
                    path=path_str,
                    expected="file or directory",
                    actual="missing",
                )
            )
            continue  # skip remaining checks for this missing file

        # ── min_size ──
        min_size_str = contract.get("min_size")
        if min_size_str and file_path is not None:
            min_bytes = _parse_size(min_size_str)
            actual_size = _file_or_dir_size(file_path)
            if actual_size < min_bytes:
                violations.append(
                    ContractViolation(
                        check="min_size",
                        detail=(
                            f"Output {key!r} size {_fmt_size(actual_size)} "
                            f"< minimum {_fmt_size(min_bytes)}"
                        ),
                        path=path_str,
                        expected=f">= {_fmt_size(min_bytes)}",
                        actual=_fmt_size(actual_size),
                    )
                )

        # ── extensions ──
        allowed_exts = contract.get("extensions")
        if allowed_exts and isinstance(allowed_exts, list) and file_path is not None:
            if file_path.is_file() and not any(path_str.endswith(ext) for ext in allowed_exts):
                violations.append(
                    ContractViolation(
                        check="extension",
                        detail=(
                            f"Output {key!r} extension {file_path.suffix!r} "
                            f"not in allowed: {allowed_exts}"
                        ),
                        path=path_str,
                        expected=str(allowed_exts),
                        actual=file_path.suffix,
                    )
                )

        # ── contains (directory contents check) ──
        contains = contract.get("contains")
        if contains and isinstance(contains, list) and file_path is not None:
            if file_path.is_dir():
                for expected_name in contains:
                    if not (file_path / expected_name).exists():
                        violations.append(
                            ContractViolation(
                                check="contains",
                                detail=(
                                    f"Output directory {key!r} missing "
                                    f"expected file: {expected_name!r}"
                                ),
                                path=str(file_path / expected_name),
                                expected=expected_name,
                                actual="missing",
                            )
                        )

        # ── min_files (directory contents count) ──
        min_files = contract.get("min_files")
        if min_files is not None and file_path is not None:
            actual_files = _count_regular_files(file_path)
            if actual_files < int(min_files):
                violations.append(
                    ContractViolation(
                        check="min_files",
                        detail=(
                            f"Output {key!r} has {actual_files} files, minimum {min_files} required"
                        ),
                        path=path_str,
                        expected=f">= {min_files}",
                        actual=str(actual_files),
                    )
                )

        # ── min_contigs (FASTA-specific) ──
        min_contigs = contract.get("min_contigs")
        if min_contigs is not None and file_path is not None and file_path.is_file():
            actual_contigs = _count_fasta_contigs(file_path)
            if actual_contigs < int(min_contigs):
                violations.append(
                    ContractViolation(
                        check="min_contigs",
                        detail=(
                            f"Output {key!r} has {actual_contigs} contigs, "
                            f"minimum {min_contigs} required"
                        ),
                        path=path_str,
                        expected=f">= {min_contigs}",
                        actual=str(actual_contigs),
                    )
                )

        # ── JSON schema check ──
        required_keys = contract.get("required_keys")
        schema = contract.get("schema")
        if file_path is not None and file_path.is_file() and file_path.suffix == ".json":
            if required_keys and isinstance(required_keys, list):
                violations.extend(_validate_json_required_keys(file_path, required_keys, key))
            if schema and isinstance(schema, Mapping):
                json_violations = _validate_json_schema(file_path, schema, key)
                violations.extend(json_violations)

        # ── Checksum ──
        if file_path is not None and file_path.is_file():
            digest = compute_file_checksum(file_path)
            if digest:
                checksums[str(file_path)] = digest

    passed = len(violations) == 0
    return StepContractResult(passed=passed, violations=violations, checksums=checksums)


# Forbidden AST node types in assertion expressions (S3 fix).
# These could be used to define functions, generate values, or cause side effects
# beyond simple expression evaluation.
_FORBIDDEN_AST_NODES = frozenset(
    {
        ast.Lambda,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.DictComp,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.NamedExpr,  # walrus operator :=
    }
)


def _validate_assertion_ast(expression: str) -> str | None:
    """Reject assertion expressions containing forbidden Python constructs (S3 fix).

    Returns an error message string if forbidden constructs are found,
    or ``None`` if the expression passes validation.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None  # will be caught by eval() itself
    for node in ast.walk(tree):
        if type(node) in _FORBIDDEN_AST_NODES:
            return f"{type(node).__name__} is not allowed in assertion expressions"
        # Block attribute access on dunder names (escaping __class__ etc.)
        if isinstance(node, ast.Attribute) and isinstance(node.attr, str):
            if node.attr.startswith("__"):
                return f"Attribute access on {node.attr!r} is not allowed"
        # Block subscript access with dunder names
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                if node.slice.value.startswith("__"):
                    return f"Subscript access with {node.slice.value!r} is not allowed"
    return None


def _normalise_assertion(expression: str) -> str:
    """Normalise natural-language assertion syntax to valid Python.

    ``output_files.x exists`` → ``exists(output_files.x)``
    """
    return re.sub(r"(\S+)\s+exists\s*$", r"exists(\1)", expression.strip())


def _isclose_for_assertions(
    a: float | int,
    b: float | int,
    rel_tol: float = 1e-9,
    abs_tol: float = 0.0,
) -> bool:
    """Thin wrapper around ``math.isclose()`` for use in assertion expressions (B13 fix).

    DAG assertions can use ``isclose()`` for float-tolerant comparisons:
    ``"isclose(output_json.summary.q20_rate, 0.95, rel_tol=0.01)"``
    """
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)


# ═══════════════════════════════════════════════════════════════════════════
# Assertion evaluation
# ═══════════════════════════════════════════════════════════════════════════


class _AttrDict:
    """A recursive dict wrapper that supports attribute access.

    ``d.summary.total_reads`` is equivalent to ``d["summary"]["total_reads"]``.
    Used to make assertion expressions like ``output_json.summary.total_reads > 0``
    work naturally with JSON-parsed dicts.
    """

    def __init__(self, data: Any) -> None:
        object.__setattr__(self, "_data", data)
        if isinstance(data, dict):
            for key, value in data.items():
                object.__setattr__(
                    self,
                    key,
                    _AttrDict(value) if isinstance(value, (dict, list)) else value,
                )

    def __getattr__(self, name: str) -> Any:
        # Called only when normal attribute lookup fails.
        # S3: block dunder attribute access to prevent eval escape vectors.
        if name.startswith("__"):
            raise AttributeError(f"Access to {name!r} is blocked in assertion expressions")
        return None

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_data"))

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_data"))

    def __eq__(self, other: Any) -> bool:
        return object.__getattribute__(self, "_data") == other

    def __ne__(self, other: Any) -> bool:
        return object.__getattribute__(self, "_data") != other

    def __lt__(self, other: Any) -> bool:
        data = object.__getattribute__(self, "_data")
        if isinstance(data, (int, float)) and isinstance(other, (int, float)):
            return data < other
        return NotImplemented

    def __le__(self, other: Any) -> bool:
        data = object.__getattribute__(self, "_data")
        if isinstance(data, (int, float)) and isinstance(other, (int, float)):
            return data <= other
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        data = object.__getattribute__(self, "_data")
        if isinstance(data, (int, float)) and isinstance(other, (int, float)):
            return data > other
        return NotImplemented

    def __ge__(self, other: Any) -> bool:
        data = object.__getattribute__(self, "_data")
        if isinstance(data, (int, float)) and isinstance(other, (int, float)):
            return data >= other
        return NotImplemented

    def __int__(self) -> int:
        return int(object.__getattribute__(self, "_data"))

    def __float__(self) -> float:
        return float(object.__getattribute__(self, "_data"))

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_data"))


def _wrap_context(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Wrap dict values in the assertion context as _AttrDict for dot access."""
    wrapped: Dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, dict):
            wrapped[key] = _AttrDict(value)
        else:
            wrapped[key] = value
    return wrapped


def evaluate_assertions(
    assertions: List[str],
    context: Mapping[str, Any],
) -> List[ContractViolation]:
    """Evaluate runtime assertion predicates.

    Assertions are simple Python expressions evaluated in a restricted
    namespace.  Supported context variables:

    - ``output_json.<key>`` — for JSON output files, the parsed content
      (accessible via dot notation: ``output_json.summary.total_reads``).
    - ``output_files.<key>`` — ``True`` if the file exists.
    - ``return_code`` — the tool's exit code.

    Examples:
        ``"output_json.summary.after_filtering.total_reads > 0"``
        ``"output_files.real exists"``
        ``"return_code == 0"``

    Args:
        assertions: List of assertion strings from the DAG spec.
        context: Dict with keys ``output_json``, ``output_files``, ``return_code``.

    Returns:
        List of ``ContractViolation`` for assertions that evaluated to ``False``.
    """
    violations: List[ContractViolation] = []
    if not assertions:
        return violations

    # Build a safe namespace with attribute-accessible dicts.
    # 构建具有属性可访问字典的安全命名空间。
    safe_namespace = _wrap_context(context)
    safe_namespace.update(
        {
            "True": True,
            "False": False,
            "None": None,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "len": len,
            "abs": abs,
            "min": min,
            "max": max,
            "sum": sum,
            "any": any,
            "all": all,
            # ``exists`` keyword: "output_files.x exists" → bool(output_files.x)
            "exists": lambda x: bool(x),
            # ``isclose`` for float-tolerant assertions (B13 fix):
            #   "isclose(output_json.summary.q20_rate, 0.95, rel_tol=0.01)"
            "isclose": _isclose_for_assertions,
            "round": round,
        }
    )

    for assertion in assertions:
        # Normalise natural-language ``x exists`` → ``exists(x)`` so it's
        # valid Python syntax for eval(). 只转换 "x exists" 语法为有效的 Python。
        expr = _normalise_assertion(assertion)
        # S3: AST pre-scan rejects forbidden constructs (lambdas, functions, etc.)
        ast_error = _validate_assertion_ast(expr)
        if ast_error:
            violations.append(
                ContractViolation(
                    check="assertion",
                    detail=f"Forbidden construct in {assertion!r}: {ast_error}",
                    expected="safe expression without lambdas or function definitions",
                    actual=ast_error,
                )
            )
            continue
        try:
            result = eval(expr, {"__builtins__": {}}, safe_namespace)
        except Exception as exc:
            violations.append(
                ContractViolation(
                    check="assertion",
                    detail=f"Failed to evaluate: {assertion!r} — {exc}",
                    expected="evaluable expression",
                    actual=str(exc),
                )
            )
            continue

        if not result:
            violations.append(
                ContractViolation(
                    check="assertion",
                    detail=f"Assertion failed: {assertion!r}",
                    expected="True",
                    actual="False",
                )
            )

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# Input checksum verification
# ═══════════════════════════════════════════════════════════════════════════


def verify_input_checksums(
    step_id: str,
    inputs: Mapping[str, Any],
    checksum_map: Mapping[str, str],
) -> List[ContractViolation]:
    """Verify that input files match previously-recorded checksums.

    Only checks files whose paths appear in *checksum_map* — files that
    have NOT been produced by an upstream step are skipped (they are
    external inputs and have no previous checksum).

    Args:
        step_id: The step identifier.
        inputs: The step's input parameter dict.
        checksum_map: ``{path: sha256}`` from provenance/checksums.json.

    Returns:
        Violations for any checksum mismatch.
    """
    violations: List[ContractViolation] = []
    if not checksum_map:
        return violations

    for key, value in inputs.items():
        if not isinstance(value, (str, Path)):
            continue
        path = str(value)
        if path not in checksum_map:
            continue
        expected = checksum_map[path]
        actual = compute_file_checksum(path)
        if not actual:
            violations.append(
                ContractViolation(
                    check="checksum_verify",
                    detail=f"Input {key!r} missing for checksum verification",
                    path=path,
                    expected=expected[:16] + "...",
                    actual="file missing",
                )
            )
        elif actual != expected:
            violations.append(
                ContractViolation(
                    check="checksum_mismatch",
                    detail=(
                        f"Input {key!r} checksum changed — possible data corruption "
                        f"or intermediate file modification"
                    ),
                    path=path,
                    expected=expected[:16] + "...",
                    actual=actual[:16] + "...",
                )
            )

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_SIZE_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s*([KMGT]?B)?$", re.IGNORECASE)
_SIZE_UNITS: Dict[str, int] = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def _parse_size(text: str) -> int:
    """Parse a human-readable size string like ``"1KB"`` or ``"500B"`` to bytes."""
    match = _SIZE_PATTERN.match(str(text).strip())
    if not match:
        return 0
    value = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    return int(value * _SIZE_UNITS.get(unit, 1))


def _fmt_size(num_bytes: int) -> str:
    """Format a byte count in human-readable form."""
    if num_bytes < 1024:
        return f"{num_bytes}B"
    if num_bytes < 1024**2:
        return f"{num_bytes / 1024:.0f}KB"
    if num_bytes < 1024**3:
        return f"{num_bytes / 1024**2:.0f}MB"
    return f"{num_bytes / 1024**3:.1f}GB"


def _file_or_dir_size(path: Path) -> int:
    """Return the total size of a file or directory in bytes.

    For directories, computes the sum of all file sizes recursively.
    """
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                total += child.stat().st_size
        return total
    return 0


def _count_regular_files(path: Path) -> int:
    """Count regular files under a directory, or return 1 for a regular file."""
    if path.is_file():
        return 1
    if path.is_dir():
        return sum(1 for child in path.rglob("*") if child.is_file())
    return 0


def _count_fasta_contigs(path: Path) -> int:
    """Count ``>`` header lines in a FASTA file."""
    count = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(">"):
                    count += 1
    except Exception:
        return 0
    return count


def _validate_json_required_keys(
    file_path: Path,
    required_keys: List[Any],
    output_key: str,
) -> List[ContractViolation]:
    """Validate that a JSON file contains required top-level keys."""
    violations: List[ContractViolation] = []
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        return [
            ContractViolation(
                check="json_parse",
                detail=f"Cannot parse JSON output {output_key!r}: {exc}",
                path=str(file_path),
            )
        ]

    if not isinstance(data, Mapping):
        return [
            ContractViolation(
                check="json_required_key",
                detail=f"JSON output {output_key!r} is not an object",
                path=str(file_path),
                expected="object",
                actual=type(data).__name__,
            )
        ]

    for required_key in required_keys:
        key = str(required_key)
        if key not in data:
            violations.append(
                ContractViolation(
                    check="json_required_key",
                    detail=f"Required key {key!r} not found in {output_key!r}",
                    path=str(file_path),
                    expected=key,
                    actual="missing",
                )
            )
    return violations


def _validate_json_schema(
    file_path: Path,
    schema: Mapping[str, Any],
    output_key: str,
) -> List[ContractViolation]:
    """Validate a JSON file against a simplified schema expressed as dotted-key
    type constraints.

    Example schema::

        {
            "summary.before_filtering.total_reads": {"type": "integer", "min": 0},
            "summary.after_filtering.total_reads": {"type": "integer", "min": 0},
        }
    """
    violations: List[ContractViolation] = []
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        violations.append(
            ContractViolation(
                check="json_parse",
                detail=f"Cannot parse JSON output {output_key!r}: {exc}",
                path=str(file_path),
            )
        )
        return violations

    for dotted_key, constraint in schema.items():
        if not isinstance(constraint, Mapping):
            continue
        parts = dotted_key.split(".")
        value = data
        path_traversed: List[str] = []
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
                path_traversed.append(part)
            else:
                violations.append(
                    ContractViolation(
                        check="json_schema",
                        detail=(f"Key {dotted_key!r} not found in {output_key!r}"),
                        path=str(file_path),
                        expected=dotted_key,
                        actual=f"missing at {'.'.join(path_traversed) or 'root'}",
                    )
                )
                value = None
                break

        if value is None:
            continue

        expected_type = constraint.get("type")
        if expected_type == "integer" and not isinstance(value, int):
            violations.append(
                ContractViolation(
                    check="json_schema",
                    detail=f"{dotted_key!r} expected integer, got {type(value).__name__}",
                    path=str(file_path),
                    expected="integer",
                    actual=str(value),
                )
            )

        min_val = constraint.get("min")
        if min_val is not None and isinstance(value, (int, float)) and value < min_val:
            violations.append(
                ContractViolation(
                    check="json_schema",
                    detail=f"{dotted_key!r} value {value} < minimum {min_val}",
                    path=str(file_path),
                    expected=f">= {min_val}",
                    actual=str(value),
                )
            )

    return violations
