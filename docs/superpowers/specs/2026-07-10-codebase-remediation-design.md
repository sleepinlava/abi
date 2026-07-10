# ABI Codebase Remediation Design

- Status: Approved
- Date: 2026-07-10
- Scope: repository-wide audit findings from the 2026-07-10 review
- Strategy: security-first, backward-compatible, incremental guarded extraction

## 1. Objective

This design turns the audit findings into independently testable and reversible changes. It
prioritizes correctness and security, preserves existing CLI shapes and public planning types,
and moves policy out of transport adapters into a small set of deep core modules.

The work must not become a single rewrite. Each change set must have its own regression tests,
acceptance criteria, and rollback boundary. New modules are introduced behind compatibility
interfaces, compared with current behavior, and made authoritative only after parity is proven.

## 2. Confirmed findings

| ID | Severity | Finding |
|---|---|---|
| F01 | P1 | Raw `sample_id` values can escape the configured output root. |
| F02 | P1 | Nextflow silently omits internal steps and passes dependency channels through. |
| F03 | P1 | Built wheels omit `environments.yaml`. |
| F04 | P1 | Most tool resource contracts are not connected to runtime metadata. |
| F05 | P1 | `ResourceSpec.merge()` cannot represent an explicit override equal to a default value. |
| F06 | P1 | Nextflow ignores shared runtime resource and container overrides. |
| F07 | P1 | `ResourceDownloader` records integrity metadata but does not enforce it. |
| F08 | P1 | A direct-layout `ABI_MAMBA_ROOT` is ignored by the canonical root resolver. |
| F09 | P2 | Long-read MetaPhlAn routing and generic optional-flag rendering have regressed. |
| F10 | P2 | Inline Python command templates are syntactically invalid or unsafe to compose. |
| F11 | P2 | `abi-sciplot render` exposes an uncontrolled optional-dependency import failure. |
| F12 | P2 | Pytest, contract lint, XPASS, Ruff check, and Ruff format gates are not all green. |

## 3. Chosen approach

The chosen approach is guarded extraction:

1. Restore a trustworthy quality baseline.
2. Add immediate security and correctness guards.
3. Extract environment, execution-policy, tool-catalog, and compiled-plan modules behind current
   public interfaces.
4. Migrate one runtime adapter at a time.
5. Remove old policy paths only after parity tests pass.

Alternatives rejected:

- A parallel v2 core would leave two semantic systems active for too long.
- A one-shot rewrite would create an unnecessarily large regression and rollback surface.

## 4. Architectural direction

The dependency direction is:

```text
CLI / MCP / Agent
        |
existing public interfaces
        |
Sample Intake + Path Policy -> DAG Planner
                                  |
Runtime Environment -> Tool Catalog -> Compiled Execution Plan
                                         |       |       |
                                       Local    HPC   Nextflow

Resource Lifecycle -> plugin/tool resource adapters
```

Transport adapters translate a compiled plan to their execution format. They must not choose
resource precedence, guess environments, discard steps, or weaken path rules.

### 4.1 Path Policy

Add `src/abi/path_policy.py` with a deliberately small interface:

```python
validate_sample_id(value: str) -> str
resolve_within(root: Path, candidate: str | Path, *, label: str) -> Path
```

`SampleInput` remains in `src/abi/schemas.py`; its validator delegates to Path Policy. The DAG
planner, local executor, and single-step runner also call `resolve_within`, providing defense in
depth when a caller constructs a `PlanStep` without schema validation.

The policy rejects absolute paths, both path separator styles, NUL/control characters, dot and
dot-dot identifiers, traversal components, excessive length, and resolved symlink escapes.

### 4.2 Runtime Environment

Add `src/abi/runtime_environment.py` with:

```python
discover_mamba_root(explicit: Path | None = None) -> Path
resolve_environment_prefix(name: str, root: Path | None = None) -> Path
load_environment_assignments() -> Mapping[str, str]
```

It supports both `<root>/envs/<name>` and `<root>/<name>` layouts. Existing
`resolved_mamba_root()` remains as a compatibility delegate.

The source-tree `environments.yaml` remains canonical. Wheel builds copy it to
`abi/data/environments.yaml`; installed code reads it via `importlib.resources`. Source and wheel
execution use the same loader.

### 4.3 Tool Catalog

Add `src/abi/tool_catalog.py`. It compiles registry declarations, tool contracts, environment
assignments, and execution metadata into immutable `RuntimeToolDescriptor` values.

```python
@dataclass(frozen=True)
class RuntimeToolDescriptor:
    tool_id: str
    command: CommandDescriptor
    resources: ResourceSpec
    environment: str | None
    container_image: str | None
    inputs: Mapping[str, InputDescriptor]
    outputs: Mapping[str, OutputDescriptor]
```

`ToolRegistry` initially becomes a compatibility adapter over the catalog. Its existing
`get`, `has`, and `create` entry points remain available. Contract lint reuses catalog conflict
detection so validation and runtime cannot implement different merge rules.

### 4.4 Compiled Execution Plan

Add `src/abi/workflow/compiled_plan.py` with a backend-neutral compile interface:

```python
compile_plan(
    plan: ExecutionPlan,
    config: Mapping[str, Any],
    catalog: ToolCatalog,
    policy: ExecutionPolicy,
) -> CompiledPlan
```

Each compiled step contains its original ID, complete dependencies, execution kind, resolved
resources, resolved environment or container, validated paths, command description, and output
contract.

Execution kinds are explicit:

- `external`
- `internal_worker`
- `internal_driver`

The compiler enforces unique IDs, defined dependencies, acyclicity, known tools, resolved
execution kinds, safe paths, and a one-to-one mapping from enabled steps to compiled steps.

### 4.5 Resource Lifecycle

Deepen the existing `ResourceDownloader`; do not add a competing downloader. Its internal state
machine is:

```text
ABSENT -> STAGING -> VERIFIED -> INSTALLED
                  \-> FAILED
INSTALLED -> VERIFIED or CORRUPT
CORRUPT -> STAGING
```

Checksum, required files, file count, total size, and custom validation are enforced before the
sentinel is written. A sentinel is evidence of a completed validation, not permission to skip
current validation. Installation occurs in staging and switches atomically after proof.

## 5. Canonical data flow

All backends follow one path:

```text
raw input
  -> Sample Intake
  -> ExecutionPlan
  -> compile with Tool Catalog and Invocation Policy
  -> validate invariants
  -> CompiledPlan
  -> Local / HPC / Nextflow adapter
```

An adapter may render scheduler syntax or launch processes. It may not mutate execution semantics.
Every enabled step must be either present in the compiled plan or explicitly rejected. A successful
compile cannot contain rejected steps.

## 6. Resource and execution policy

Separate partial overrides from resolved values:

```python
@dataclass(frozen=True)
class ResourceOverride:
    cpu: int | None = None
    memory: str | None = None
    walltime: str | None = None
    accelerator: str | None = None
    disk: str | None = None

@dataclass(frozen=True)
class ResourceSpec:
    cpu: int
    memory: str
    walltime: str
    accelerator: str | None
    disk: str | None
```

`None` is the only unset representation. Values such as one CPU or four GB are valid explicit
overrides even when they equal backend defaults.

Precedence, highest first:

1. Invocation override.
2. Workflow-step override.
3. Tool Catalog recommendation.
4. Backend fallback.

Recommended resources are not hard minimums. A separate minimum constraint may be declared; only
that constraint prevents lowering an invocation value.

Environment and container selection uses the same precedence. The execution mode is one of
`auto`, `native`, `conda`, or `container`. Explicitly conflicting options fail instead of being
guessed.

## 7. Nextflow semantics

### 7.1 Immediate fail-fast

Before writing a workflow, Nextflow collects unsupported internal workers and drivers. If any are
present, export fails with all step IDs and affected downstream steps. It must not overwrite an
existing workflow file and smoke mode must not bypass the check.

### 7.2 Internal worker support

The repository already contains `src/abi/step_runner.py` and a single-step CLI path. Nextflow will
reuse them rather than add another runner.

The exporter writes permission-restricted step payloads, emits an internal process that calls the
existing runner, and consumes the existing atomic result JSON. Internal drivers must be expanded
before export. Drivers that cannot be expanded remain explicitly unsupported.

Once support is enabled, the required invariant is:

```text
exported processes == enabled plan steps
```

## 8. Error model

Use stable internal error categories:

| Error | Meaning |
|---|---|
| `InputPolicyError` | Unsafe or invalid user input. |
| `PlanIntegrityError` | Invalid DAG or compiled-plan invariant. |
| `UnsupportedExecutionError` | Backend cannot preserve the requested execution semantics. |
| `ToolResolutionError` | Tool, contract, environment, or catalog resolution failed. |
| `ResourcePolicyError` | Resource values are invalid or violate a declared minimum. |
| `ArtifactIntegrityError` | A downloaded or installed resource failed validation. |
| `PackagingError` | Required installed package data is absent. |

Adapters translate these errors to user-facing diagnostics but do not swallow or reclassify them
as tool exit failures.

## 9. Command construction and optional dependencies

Long-read MetaPhlAn uses a structured boolean option rather than an optional string fragment. The
generic builder must never insert a bare `--` as an empty-field placeholder.

pyCirclize, pyvis, and DNA-feature commands move from inline `python -c` templates to dedicated
module adapters. Paths and user values are passed as argv elements, never embedded into Python
source.

SciPlot keeps visualization libraries optional. Validation remains available without matplotlib;
rendering catches the missing dependency and returns a controlled message directing the user to
install `abi-agent[report]`.

## 10. Change sets

### C00 - Restore the quality baseline

- Update the stale barplot auto-count expectation.
- remove the now-passing obsolete xfail.
- Align Platon contract and registry flags.
- Fix Ruff import and format drift.
- Require pytest, contract lint, Ruff, and mypy to be green before behavioral changes.

### C01 - Path security

- Add Path Policy.
- Delegate schema validation to it.
- Enforce containment in planner, executor, and step runner.
- Test Unix traversal, Windows traversal, absolute paths, control characters, and symlink escape.

### C02 - Nextflow fail-fast

- Validate exportability before rendering or writing.
- Reject internal steps with actionable diagnostics.
- Keep pure-external workflows working.
- Verify existing workflow files are not overwritten on failure.

### C03 - Packaging and environment resolution

- Add Runtime Environment.
- Support direct and managed Mamba layouts.
- Package environment assignments as importable data.
- Build and inspect both wheel and sdist in tests.

### C04 - Resource integrity

- Enforce every `DownloadSpec` integrity field.
- Make process locking a direct dependency/capability.
- Validate before sentinel and atomic switch.
- Recheck required payload evidence when a sentinel exists.
- Keep existing installations intact on failed replacement.

### C05 - Command adapters and SciPlot dependency handling

- Restore structured long-read MetaPhlAn behavior.
- Eliminate inline Python source templates.
- Convert missing renderer dependencies to controlled CLI errors.

### C06 - Execution policy

- Introduce `ResourceOverride`.
- Keep `ResourceSpec` as the resolved form.
- Apply the same resource and container policy in HPC and Nextflow.
- Prove an explicit default-valued override can lower a contract recommendation.

### C07 - Tool Catalog

- Compile registry, contracts, environment assignments, and execution metadata.
- Run in shadow comparison across all built-in tools.
- Resolve all differences before making it authoritative.
- Retain `ToolRegistry` compatibility entry points.

### C08 - CompiledPlan

- Compile and validate every built-in plugin in shadow mode.
- Compare order, dependencies, paths, resources, and execution kinds with current plans.
- Do not change runtime behavior until parity is established.

### C09 - Nextflow internal workers

- Reuse the existing step runner and CLI path.
- Generate payloads and processes for internal workers.
- Retain fail-fast for unsupported drivers.
- Prove the plasmid plan exports every enabled step and produces consensus artifacts.

### C10 - Adapter migration and cleanup

- Migrate Nextflow first, HPC second, and Local last as the behavioral reference.
- Remove duplicated resource, environment, and container resolution after parity.
- Keep public compatibility interfaces for at least one release cycle.

## 11. Test strategy

Each behavioral change uses a failing regression test before implementation. Focused tests run
first, followed by contract and cross-adapter tests. Real-tool smoke tests are required only where
mock execution cannot verify the contract.

Key invariants include:

- Malicious sample IDs and crafted plan outputs cannot escape the result root.
- `enabled_steps == compiled_steps` for a successful compile.
- `enabled_steps == exported_processes` for a successful Nextflow export.
- Local, HPC, and Nextflow resolve identical resources for the same step and policy.
- A missing or changed resource payload cannot be accepted solely because a sentinel exists.
- Wheel and sdist installations can load the canonical environment assignments.

Global verification:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ src/abi/sciplot/tests/ -v --tb=short
pytest tests/ --cov=src/abi --cov-fail-under=75
python -m build
```

The final gate requires zero failures, zero unexpected XPASS results, successful contract lint for
all seven built-in plugins, and verified environment data in wheel and sdist artifacts.

## 12. Rollback and compatibility

- C01 through C06 are independent after C00 and can be reverted separately.
- C07 and C08 begin in shadow mode, so rollback returns to current behavior without a data
  migration.
- C09 can be disabled back to C02 fail-fast; it must never roll back to silent omission.
- New sentinel readers accept older sentinel schemas but do not allow them to bypass current
  integrity requirements.
- Existing CLI shapes, `ExecutionPlan`, and `ToolRegistry` entry points remain stable during the
  migration.
- No persistent compiled-plan format is declared public in this work.

## 13. Non-goals

- Rewriting plugin business logic.
- Replacing all YAML command declarations with Python classes.
- Making every optional visualization dependency mandatory.
- Supporting dynamically expanding Nextflow drivers before they can preserve ABI semantics.
- Changing public CLI command names or argument shapes.

## 14. Finding-to-change mapping

| Finding | Change sets |
|---|---|
| F01 path traversal | C01 |
| F02 Nextflow step loss | C02, C08, C09 |
| F03 wheel asset omission | C03 |
| F04 disconnected contracts | C07 |
| F05 ambiguous resource merge | C06 |
| F06 ignored Nextflow overrides | C06, C08 |
| F07 inactive downloader integrity | C04 |
| F08 ignored direct Mamba layout | C03 |
| F09 MetaPhlAn regression | C05 |
| F10 inline Python commands | C05 |
| F11 SciPlot dependency failure | C05 |
| F12 red repository gates | C00 |
