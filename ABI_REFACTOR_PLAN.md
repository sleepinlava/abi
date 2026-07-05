# ABI 修复与重构执行文档

> 生成日期: 2026-07-04
> 版本: v1.1 (2026-07-05 修订: 删除 SQLite 项; 1d/2e 按实际实现重设; 3b/3g 调整)
> 状态: 待实施

---

## 目录

1. [总体架构路线图](#1-总体架构路线图)
2. [Phase 1: 安全加固 (Week 1-2)](#2-phase-1-安全加固-week-1-2)
3. [Phase 2: 核心加固 (Week 3-8)](#3-phase-2-核心加固-week-3-8)
4. [Phase 3: 架构现代化 (Week 9-16)](#4-phase-3-架构现代化-week-9-16)
5. [API 设计参考](#5-api-设计参考)
6. [测试门禁指标](#6-测试门禁指标)
7. [风险与回退方案](#7-风险与回退方案)

---

## 1. 总体架构路线图

### 1.1 三阶段演进

```
                    ┌─────────────────────────────────────┐
                    │        Phase 1: 安全加固             │
                    │     （Week 1-2，无架构变更）          │
                    │                                     │
                    │  1a. MCP exec() 消除                  │
                    │  1b. SafeFormatDict 严格模式           │
                    │  1c. abi lint-template CLI             │
                    │  1d. ResourceDownloader 统一类         │
                    │  1e. amplicon_16s 资源迁移             │
                    │  1f. wgs_bacteria 资源迁移             │
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │        Phase 2: 核心加固              │
                    │     （Week 3-8，局部架构调整）         │
                    │                                     │
                    │  2a. StandardTableManager 线程安全     │
                    │  2b. 配置 Pydantic 模型基类            │
                    │  2c. RNASeqConfig + 加载器             │
                    │  2d. Plugin Protocol 注册时验证        │
                    │  2e. 双 DAG Phase 2 迁移               │
                    │  2f. 隐式耦合消除                      │
                    │  2g. 集成测试 + CI 门禁                │
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │        Phase 3: 架构现代化            │
                    │     （Week 9-16，架构重构）           │
                    │                                     │
                    │  3a. 双 DAG Phase 3 完成              │
                    │  3b. 插件 Pydantic 推广（观察期）      │
                    │  3c. abi doctor 命令                  │
                    │  3e. _engine/ 废弃                     │
                    │  3f. ResourceDownloader 全部迁移       │
                    │  3g. 测试覆盖率持续提升                │
                    └─────────────────────────────────────┘
```

### 1.2 文件变更清单总览

| 操作 | 文件 | 阶段 |
|:---|:---|:---:|
| **新增** | `abi/mcp/_tool_factory.py` | Phase 1 |
| **修改** | `abi/mcp/server.py` | Phase 1 |
| **修改** | `abi/tools.py` (SafeFormatDict) | Phase 1 |
| **新增** | `abi/contracts/lint_template.py` | Phase 1 |
| **修改** | `abi/cli.py` (新增 lint-template 命令) | Phase 1 |
| **新增** | `abi/resource_downloader.py` | Phase 1 |
| **修改** | `abi/tables.py` (线程安全) | Phase 2 |
| **新增** | `abi/config_models.py` | Phase 2 |
| **新增** | `abi/plugins/validator.py` | Phase 2 |
| **修改** | `abi/dag_planner.py` (增强) | Phase 2 |
| **修改** | `abi/tools.py` (ToolRegistry) | Phase 2 |
| **新增** | `scripts/migration_gate.py` | Phase 2 |
| **删除** | `_engine/planner.py` | Phase 3 |
| **新增** | `abi/doctor.py` | Phase 3 |
| **修改** | 7 个插件配置模型 | Phase 3 |

---

## 2. Phase 1: 安全加固 (Week 1-2)

### 2.1 工作项 1a — MCP exec() 消除

**目标**: 移除 `mcp/server.py:95` 的 `exec()` 调用，改用 `inspect.Signature` 工厂函数。

**变更文件**:
- `src/abi/mcp/_tool_factory.py` (新增)
- `src/abi/mcp/server.py` (修改)

**详细设计**:

```python
# src/abi/mcp/_tool_factory.py
"""Safe MCP tool function factory — replaces exec() with inspect."""

import inspect
import re
from functools import wraps
from typing import Any, Callable, Optional

_TOOL_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
_PARAM_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

_JSON_TO_PY_TYPE: dict[str, type] = {
    "string": str, "integer": int, "number": float,
    "boolean": bool, "array": list, "object": dict,
}

class ToolDescriptor:
    def __init__(self, raw_name: str, metadata: dict):
        if not _TOOL_NAME_RE.match(raw_name):
            raise ValueError(f"Invalid tool name: {raw_name!r}")
        self.name = raw_name
        self.description = str(metadata.get("description", ""))
        self.properties = self._validate_properties(metadata)
        self.required = set(metadata.get("required", []))

    def _validate_properties(self, metadata: dict) -> dict[str, dict]:
        props = metadata.get("properties", {})
        for pname in props:
            if not _PARAM_NAME_RE.match(pname):
                raise ValueError(f"Invalid parameter name {pname!r}")
        return dict(props)

    def make_function_signature(self) -> inspect.Signature:
        params = []
        for pname, pschema in self.properties.items():
            py_type = _JSON_TO_PY_TYPE.get(pschema.get("type", "string"), Any)
            if pname in self.required:
                params.append(
                    inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY, annotation=py_type)
                )
            else:
                params.append(
                    inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY,
                                      default=None, annotation=Optional[py_type])
                )
        return inspect.Signature(params)


def make_tool_func(descriptor: ToolDescriptor, agent_method: Callable[..., str]) -> Callable[..., str]:
    declared = set(descriptor.properties)

    @wraps(agent_method)
    def tool_func(**kwargs) -> str:
        unknown = set(kwargs) - declared
        if unknown:
            raise ValueError(
                f"Unknown parameters for {descriptor.name}: {', '.join(sorted(unknown))}"
            )
        return agent_method(**kwargs)

    tool_func.__name__ = tool_func.__qualname__ = descriptor.name
    tool_func.__doc__ = descriptor.description
    tool_func.__signature__ = descriptor.make_function_signature()
    return tool_func
```

**`server.py` 的修改**:

```python
# server.py 中删除 exec() 相关代码，改为：
from abi.mcp._tool_factory import ToolDescriptor, make_tool_func

def _register_mcp_tools(mcp: Any, agent: ABIAgentInterface) -> None:
    from abi.tool_descriptors import ABI_AGENT_TOOLS, TOOL_ALIASES
    for raw_name, metadata in ABI_AGENT_TOOLS.items():
        method_name = TOOL_ALIASES.get(raw_name)
        if method_name is None:
            continue
        try:
            desc = ToolDescriptor(raw_name, metadata)
            tool_func = make_tool_func(desc, getattr(agent, method_name))
        except ValueError as e:
            _logger.warning("Skipping tool %r: %s", raw_name, e)
            continue
        mcp.tool()(tool_func)
```

**验收标准**:
- [ ] `pytest tests/unit/test_mcp_tool_factory.py` 通过
- [ ] 所有现有 `abi-mcp` 工具功能不变
- [ ] 代码审查确认无 `exec()` 残留

### 2.2 工作项 1b — SafeFormatDict 严格模式

**目标**: SafeFormatDict 已实现严格模式（`ABI_STRICT_TEMPLATES` 环境变量），需要增加类级别缺失键追踪和导入检查。

**变更文件**:
- `src/abi/tools.py` (修改)

**现状**: `SafeFormatDict.__missing__()` 已支持 strict 模式并抛出 `MissingTemplateParamError`。只需增强。

**增强点**:

```python
# 在 SafeFormatDict 类中增加：
class SafeFormatDict(dict):
    # ... 现有代码 ...

    # 新增：类级别缺失键追踪
    _class_missing_keys: ClassVar[set[str]] = set()

    def __missing__(self, key: str) -> str:
        self.missing_keys.append(key)
        self._class_missing_keys.add(key)  # 新增：类级别记录
        # ... 现有逻辑 ...
```

**验收标准**:
- [ ] `ABI_STRICT_TEMPLATES=1` 时缺失键抛出 `MissingTemplateParamError`
- [ ] 默认模式（`ABI_STRICT_TEMPLATES=0`）缺失键返回 `""` 并记录 WARNING
- [ ] 类级别 `_class_missing_keys` 正确累计所有实例的缺失键

### 2.3 工作项 1c — `abi lint-template` CLI 子命令

**目标**: 新增 CLI 子命令，对插件的所有路径模板和命令模板进行严格模式验证。

**变更文件**:
- `src/abi/cli.py` (新增命令，在 `contract-lint` 命令附近)
- `src/abi/contracts/lint_template.py` (新增)

**详细设计**:

```python
# src/abi/contracts/lint_template.py
"""Template linting — validate all path and command templates."""

from __future__ import annotations
from typing import Any, List, Mapping

@dataclass
class TemplateFinding:
    severity: str  # "error" | "warning"
    location: str  # 步骤/工具 ID
    template_key: str  # outputs.path, command_template
    message: str
    missing_keys: list[str]

def lint_templates(
    analysis_type: str,
    config: Mapping[str, Any],
    plugin,
    *,
    verbose: bool = False,
) -> dict:
    """Validate all templates in a plugin's plan."""
    from abi.tools import SafeFormatDict

    findings: List[TemplateFinding] = []

    # 1. 检查工具注册表的命令模板
    registry = plugin.registry()
    for tool_spec in registry.list_tools():
        template = tool_spec.get("command_template", "")
        if "{" not in template:
            continue
        sfd = SafeFormatDict({}, strict=True, tool_name=tool_spec.get("id", ""))
        try:
            template.format_map(sfd)
        except MissingTemplateParamError as e:
            findings.append(TemplateFinding(
                severity="error",
                location=f"tool.{tool_spec.get('id', '')}",
                template_key="command_template",
                message=str(e),
                missing_keys=list(sfd.missing_keys),
            ))

    # 2. 检查 DAG 路径模板
    plan = plugin.build_plan(config, check_files=False)
    for step in plan.steps:
        for key, template in step.outputs.items():
            if not isinstance(template, str) or "{" not in template:
                continue
            sfd = SafeFormatDict({}, strict=True, tool_name=step.step_id)
            try:
                template.format_map(sfd)
            except MissingTemplateParamError as e:
                findings.append(TemplateFinding(
                    severity="error",
                    location=f"step.{step.step_id}",
                    template_key=f"outputs.{key}",
                    message=str(e),
                    missing_keys=list(sfd.missing_keys),
                ))

    return {
        "analysis_type": analysis_type,
        "findings": [f.__dict__ for f in findings],
        "error_count": sum(1 for f in findings if f.severity == "error"),
        "warning_count": sum(1 for f in findings if f.severity == "warning"),
        "passed": not any(f.severity == "error" for f in findings),
    }
```

**CLI 命令**:

```python
# 在 cli.py 中，在 contract-lint 命令附近新增
@app.command("lint-template")
def lint_template_command(
    analysis_type: str = typer.Option(
        "metagenomic_plasmid", "--type", "-t",
        help="ABI analysis type whose templates to lint.",
    ),
    config_path: str | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Validate all command and path templates for missing parameters.

    Runs every template through SafeFormatDict in strict mode to detect
    references to undefined parameters.  Exit code 0 means no errors.

    对所有命令和路径模板进行缺失参数检查。
    """
    try:
        from abi.contracts.lint_template import lint_templates
        from abi.plugins import get_plugin

        plugin = get_plugin(analysis_type)
        config = plugin.load_config(config_path)
        result = lint_templates(analysis_type, config, plugin, verbose=verbose)

        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["passed"]:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)
```

**验收标准**:
- [ ] `abi lint-template --type rnaseq_expression` 执行成功
- [ ] 有模板错误的插件返回非零退出码
- [ ] 输出 JSON 包含 `findings`, `error_count`, `passed` 字段

### 2.4 工作项 1d — ResourceDownloader 统一类

**目标**: 创建统一的资源下载类，提供原子写入、文件锁、统一哨兵格式。

**现状（v1.1 修订）**: `src/abi/resource_downloader.py` 已在远程分支实现 ~280 行，包含 `DownloadSpec`、`DownloadResult`、`ResourceDownloader` 三类。`_setup_wgs_bacteria()` 已完全迁移。本工作项剩余任务是**补齐其余 4 个资源函数的迁移**。

**变更文件**:
- `src/abi/resource_downloader.py` (已存在，需扩展 `source_files` 和 `atomic` 字段)
- `src/abi/resources.py` (修改 4 个 `_setup_*` 函数)

**已实现 API（远程分支，~280 行）**:

```python
@dataclass
class DownloadSpec:
    resource_id: str
    tool_id: str = ""
    display_name: str = ""
    source_url: str = ""
    command: list[str] | None = None
    checksum_algorithm: str = "sha256"
    expected_checksum: str = ""
    min_file_count: int = 0
    min_size_bytes: int = 0
    expected_files: list[str] = field(default_factory=list)
    ready_check: str = "sentinel"  # sentinel | non_empty_dir | path_exists
    custom_check: Callable[[Path], bool] | None = None
    destination: Path | None = None
    timeout_seconds: float = 3600.0
    version: str = ""
    source_metadata: dict = field(default_factory=dict)

@dataclass
class DownloadResult:
    resource_id: str
    path: Path
    status: str          # ok | missing | error | skipped | planned
    version: str = ""
    checksum: str = ""
    file_count: int = 0
    size_bytes: int = 0
    downloaded_at: str = ""
    message: str = ""
    command: list[str] | None = None

class ResourceDownloader:
    SENTINEL = ".abi_resource.json"
    LEGACY_SENTINELS = (".abi_ready", ".abi_mock_resource")

    def __init__(self, root, *, dry_run=False, mock=False, lock_timeout=300): ...
    def ensure(self, spec: DownloadSpec) -> DownloadResult: ...
    def check(self, spec: DownloadSpec) -> DownloadResult: ...
    def batch_ensure(self, specs: list[DownloadSpec]) -> list[DownloadResult]: ...
    # 内部: _check_existing, _download_atomic, _download_url,
    #        _compute_checksum, _write_sentinel, _mock_resource
```

**补齐设计（4 步，按难度递增）**:

#### Step 1: `_setup_reference_resources()` — 直接迁移（1 天）

与 wgs_bacteria 同质（URL 下载 + dry_run/mock/exists），照搬已验证模式：
```python
spec = DownloadSpec(
    resource_id="reference_resources",
    tool_id=tool_id,
    source_url=url,
    destination=_configured_or_default_resource_path(...),
    ready_check="sentinel",
    expected_files=[...],
)
result = ResourceDownloader(root, dry_run=dry_run, mock=mock).ensure(spec)
return _download_result_to_row(result, field, tool_id)
```

#### Step 2: `_setup_manual_resource_bundle()` — 扩展 `source_files` 字段（1 天）

手动 bundle = 多本地文件复制。**新增 `DownloadSpec.source_files: list[Path]` 字段**（不用 command，因为复制命令跨平台脆弱）：

```python
@dataclass
class DownloadSpec:
    # ... 现有字段 ...
    source_files: list[Path] = field(default_factory=list)  # 新增: 本地文件源
```

`_download_atomic()` 增加 `elif spec.source_files:` 分支，逐个 `shutil.copy2` 到 destination，写 sentinel。

#### Step 3: `_setup_amplicon_16s()` — `atomic=False` 兼容（2 天）

**核心矛盾**: RDP 下载脚本是第三方脚本，写死输出路径，无法 `.part→replace` 原子化。**新增 `DownloadSpec.atomic: bool = True` 字段**：

```python
@dataclass
class DownloadSpec:
    # ... 现有字段 ...
    atomic: bool = True  # 新增: False 时跳过 .part 中转，直接在目标目录执行
```

`atomic=False` 时，`_download_atomic()` 跳过 `.part` 中转，直接在目标目录执行命令，完成后校验 sentinel/expected_files。命令失败时调用 `_cleanup_partial()` 清空残留目录。

**权衡**: 失去原子性但获得统一性。amplicon_16s 本来就不是原子的（第三方脚本），这是如实建模。`DownloadResult.message` 标注 `non-atomic`。

#### Step 4: `_setup_rnaseq_expression()` — 辅助能力复用（2-3 天）

**本质不同**: 这是"创建 conda 环境"而非"下载文件"，强行塞进 `ensure()` 是范畴错误。

**方案**: 保持 `_setup_rnaseq_expression()` 独立，但复用 ResourceDownloader 的**辅助能力**。将 `_check_existing`、`_write_sentinel`、`_mock_resource` 拆成可独立调用的方法，rnaseq 函数手动调用这些辅助方法做 sentinel/checksum/dry_run/mock 判断，但不走 `ensure()` 主路径。

**不引入 `setup_kind` 万能枚举** — 避免范畴膨胀。

**验收标准**:
- [ ] 单元测试覆盖 `ensure()`、`check()`、`_download_atomic()`、`batch_ensure()`
- [ ] `ensure()` 在已有资源时返回 `status="ok"` 而不下载
- [ ] 下载失败时 `.part` 目录被清理
- [ ] mock 模式创建 `.abi_resource.json` 哨兵
- [ ] `source_files` 字段: 本地文件复制 + sentinel 写入
- [ ] `atomic=False`: 第三方脚本直接执行 + 失败时清理残留
- [ ] 4 个 `_setup_*` 函数全部接入（rnaseq 为辅助复用模式）

### 2.5 工作项 1e — amplicon_16s 资源迁移

**目标**: 将 `src/abi/resources.py:_setup_amplicon_16s()` 完全接入 ResourceDownloader。

**现状（v1.1 修订）**: 远程分支已部分迁移 — mock 模式已用 `ResourceDownloader(mock=True).ensure()`，但真实下载仍用 subprocess 直接调用（RDP 脚本写死路径，与 `.part→replace` 不兼容）。

**变更文件**:
- `src/abi/resource_downloader.py` (新增 `atomic` 字段)
- `src/abi/resources.py` (修改)

**关键变更**: 使用 1d Step 3 的 `atomic=False` 模式：

```python
spec = DownloadSpec(
    resource_id="amplicon_16s_rdp",
    tool_id="vsearch_taxonomy",
    command=["bash", str(script_path), "--output", str(outdir)],
    atomic=False,  # 第三方脚本，无法原子化
    ready_check="non_empty_dir",
    expected_files=[...],
    version="rdp_16s_v16",
)
result = downloader.ensure(spec)
```

**验收标准**:
- [ ] `abi setup-resources --type amplicon_16s --mock` 创建文件
- [ ] `abi check-resources --type amplicon_16s` 报告状态
- [ ] 已有资源时跳过下载
- [ ] `atomic=False` 时命令失败会清理残留目录

### 2.6 工作项 1f — wgs_bacteria 资源迁移

**目标**: 将 `src/abi/resources.py:_setup_wgs_bacteria()` 替换为 ResourceDownloader。

**变更文件**:
- `src/abi/resources.py` (修改)

**关键变更**: 类似的模式，将 `_setup_wgs_bacteria()` 替换为使用 `ResourceDownloader`。

**验收标准**:
- [ ] `abi setup-resources --type wgs_bacteria --mock` 创建文件
- [ ] `abi check-resources --type wgs_bacteria` 报告状态

---

## 3. Phase 2: 核心加固 (Week 3-8)

### 3.1 工作项 2a — StandardTableManager 线程安全

**目标**: 为 `StandardTableManager` 添加文件级锁，防止并发写入 TSV 的竞态条件。

**变更文件**:
- `src/abi/tables.py` (修改)

**详细设计**:

```python
class StandardTableManager:
    def __init__(self):
        self._table_locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._writers: dict[str, _TSVWriter] = {}

    def _lock_for(self, table_name: str) -> threading.Lock:
        with self._global_lock:
            if table_name not in self._table_locks:
                self._table_locks[table_name] = threading.Lock()
            return self._table_locks[table_name]

    def append_rows(self, table_name: str, rows: list[dict]) -> int:
        with self._lock_for(table_name):
            writer = self._writers.get(table_name)
            if writer is None:
                raise RuntimeError(f"Table {table_name!r} not ensured yet")
            return writer.append_rows(rows)
```

### 3.2 工作项 2b — 配置 Pydantic 模型基类

**目标**: 创建 `ABIConfig` Pydantic 基类，替代不透明的 `Dict[str, Any]`。

**变更文件**:
- `src/abi/config_models.py` (新增)

**详细设计**:

```python
from pydantic import BaseModel, Field
from typing import Any, Optional

class ExecutionConfig(BaseModel):
    parallel: bool = False
    workers: int = Field(default=1, ge=1, le=128)
    error_policy: str = Field(default="halt", pattern="^(halt|continue)$")
    record_progress: bool = False
    tool_timeout_seconds: Optional[float] = None

class ABIConfig(BaseModel):
    model_config = {"extra": "allow"}
    project_name: str = "ABI Analysis"
    outdir: str = "results"
    mode: str = Field(default="auto", pattern="^(auto|interactive)$")
    threads: int = Field(default=4, ge=1, le=1024)
    mamba_root: Optional[str] = None
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    resources: dict[str, Any] = Field(default_factory=dict)
```

### 3.3 工作项 2d — Plugin Protocol 注册时验证

**目标**: 在插件发现阶段验证插件类结构完整性。

**变更文件**:
- `src/abi/plugins/validator.py` (新增)
- `src/abi/plugins/__init__.py` (修改)

**详细设计**:

```python
# validator.py
import inspect
from typing import Any

REQUIRED_ATTRIBUTES = {"plugin_id", "display_name", "description", "report_title"}
REQUIRED_METHODS = {
    "load_config": ["config_path", "profile", "db_profile", "overrides"],
    "build_plan": ["config", "check_files"],
    "registry": [],
    "table_schemas": [],
    "parse_outputs": ["tool_id", "output_dir", "sample_id"],
    "write_report": ["plan", "result_dir"],
}

def validate_plugin_class(cls: type) -> None:
    for attr in REQUIRED_ATTRIBUTES:
        if not hasattr(cls, attr):
            raise ValueError(f"Plugin class {cls.__name__} missing required attribute: {attr!r}")
    for method_name, expected_params in REQUIRED_METHODS.items():
        method = getattr(cls, method_name, None)
        if not callable(method):
            raise ValueError(f"Plugin class {cls.__name__} missing required method: {method_name!r}")
```

### 3.4 工作项 2e — 双 DAG Phase 2 迁移（渐进式）

**现状（v1.1 修订）**: `dag_planner.py` 已存在 1650 行（远程），包含 `UniversalDAG`、`PluginContextResolver`、`build_plan_from_dag`（带 hooks）、`build_sample_context`。`planner.py`（845 行）已部分委托但仍保留 ~15 个 legacy helpers 和 3 组常量。**本工作项不是"从零构建"，而是"完成在途迁移 + 删除 legacy"**。

**核心风险**: 双轨并存的中途态 — `planner.py` 调用 `dag_planner.UniversalDAG` 但仍在本地解析 context/config/skip 逻辑，任何 hook 未接好会产生**静默行为差异**（不报错但结果不同）。

**变更文件**:
- `src/abi/dag_planner.py` (已存在，增强)
- `src/abi/plugins/metagenomic_plasmid/_engine/planner.py` (逐步删除 legacy helpers)
- `plugins/metagenomic_plasmid/pipeline_dag.yaml` (常量迁入)
- `plugins/metagenomic_plasmid/config_default.yaml` (常量迁入)
- `tests/unit/test_dag_planner.py` (golden file 对比测试)

#### 渐进迁移方案（Feature Flag + 逐 hook 切换，~19 天 / 4 周）

##### 阶段 0: 建立安全网（2 天，前置）

1. **快照测试**: 对当前 `planner.build_plan()` 跑 3-5 个代表性 config，录制 PlanSteps 输出为 golden file
2. **加 `ABI_DAG_PLANNER_LEGACY=1` 环境变量**:
   ```python
   def build_plan(config, ...):
       if os.environ.get("ABI_DAG_PLANNER_LEGACY"):
           return _build_plan_legacy(config, ...)  # 当前完整旧逻辑
       return _build_plan_new(config, ...)  # 走 build_plan_from_dag + hooks
   ```
3. **默认 `LEGACY=1`** — 保证现有行为不变

**这一步是整个迁移的安全锚点。没有它不要继续。**

##### 阶段 1: 迁移 `context_from_config` → `build_sample_context`（3 天）

1. 在 `dag_planner.build_sample_context()` 对照 `planner.context_from_config()` 逐行验证逻辑等价
2. `_build_plan_new()` 用 `build_sample_context()` 替换 `context_from_config()`
3. **对比测试**: golden file 分别跑 `LEGACY=1` 和 `LEGACY=0`，断言 PlanSteps 完全一致
4. 不一致 → 修 `build_sample_context`；一致 → hook 切换完成

##### 阶段 2: 迁移 `_resolve_context_conditions` → `PluginContextResolver` + `ContextResolverHook`（4 天）

1. 在 metagenomic_plasmid 插件建 `PlasmidContextResolver(PluginContextResolver)` 子类，把 `_resolve_context_conditions` 搬进 `resolve()` 和 `eligibility()`
2. `_build_plan_new()` 传入 `context_resolver=PlasmidContextResolver(...)`
3. **对比测试**: golden file 断言一致
4. 一致 → 删除 `planner._resolve_context_conditions`

##### 阶段 3: 迁移 `_config_for_sample` → `SampleConfigHook`（3 天）

同阶段 2 模式：搬成 hook 函数，传入 `sample_config_hook=`，对比测试，一致后删旧。

##### 阶段 4: 迁移 `_analysis_skip_steps` → `SkipStepHook`（2 天）

同上模式。

##### 阶段 5: 迁移常量 + 残留 helpers（3 天）

1. `STEP_DIRS`、`DATA_PROFILE_BY_PLATFORM`、`ISOLATE_PROFILES` → 移入 `pipeline_dag.yaml` 的 `category_dirs` / `platform_profiles` 节点（`UniversalDAG` 已支持 `category_dirs`）
2. 残留 helpers（`_annotation_tools`、`_tool_runtime_params`、`_metaphlan_params` 等）→ 移入 `PlasmidContextResolver` 方法或 `dag_planner.py` 的 plugin-specific 区段
3. 对比测试

##### 阶段 6: 删除 `planner.py` + 默认切换（2 天）

1. 确认所有 callers 已走 `_build_plan_new()`
2. 删除 `planner.py`
3. `ABI_DAG_PLANNER_LEGACY` 保留一个版本周期作为应急回滚开关，下个版本删除
4. **集成测试套件**: 覆盖 3+ 平台 × 2+ config 组合

#### 时间表

| 阶段 | 工作量 | 累计 | 可回滚 |
|:---|:---:|:---:|:---:|
| 0 安全网 | 2 天 | 2 | ✅（默认旧逻辑） |
| 1 context | 3 天 | 5 | ✅（LEGACY=1） |
| 2 context_resolver | 4 天 | 9 | ✅ |
| 3 sample_config | 3 天 | 12 | ✅ |
| 4 skip_step | 2 天 | 14 | ✅ |
| 5 常量+helpers | 3 天 | 17 | ✅ |
| 6 删除+测试 | 2 天 | 19 | ✅（env var 回滚） |
| **合计** | **~19 天（4 周）** | | |

#### 关键设计决策

1. **Golden file 对比测试是硬门** — 每个 hook 切换必须通过 `LEGACY=1` vs `LEGACY=0` 输出完全一致的断言，否则不合并
2. **Feature flag 默认旧逻辑** — 新逻辑只在显式 `LEGACY=0` 时启用，灰度切换
3. **逐 hook 切换而非一次性** — 4 个 hook 各自独立切换、独立验证、独立回滚
4. **常量移入 YAML** — `UniversalDAG` 已支持 `category_dirs`，常量本就该声明式定义
5. **删除 `planner.py` 是最后一步** — 在所有 hook 验证一致后才删

#### 测试套件增强

**变更文件**: `tests/unit/test_dag_planner.py` (扩充)

**新增测试**:
```python
def test_context_resolver_diversity(): ...
def test_context_resolver_differential(): ...
def test_context_resolver_network(): ...
def test_config_for_sample(): ...
def test_build_sample_context_single(): ...
def test_build_sample_context_sheet(): ...
def test_golden_file_legacy_vs_new_platform_illumina(): ...
def test_golden_file_legacy_vs_new_platform_ont(): ...
def test_golden_file_legacy_vs_new_isolate(): ...
```

### 3.5 工作项 2f — 隐式耦合消除

**目标**: `ToolRegistry.env_for()` 强制要求 `plugin_name` 参数。

**变更文件**:
- `src/abi/tools.py` (修改 `ToolRegistry.env_for()`)

```python
@classmethod
def env_for(cls, tool_id, *, plugin_name=None):
    if plugin_name is None:
        raise ValueError("plugin_name is required since ABI v2.0")
    assignments = cls._env_assignments.get(plugin_name, {})
    result = assignments.get(tool_id)
    if result is None:
        raise KeyError(f"No environment assignment for {tool_id!r} in plugin {plugin_name!r}")
    return result
```

### 3.6 工作项 2g — 集成测试 + CI 门禁

**变更文件**:
- `scripts/migration_gate.py` (新增)
- `.github/workflows/ci.yml` (新增 stage)

```yaml
# .github/workflows/ci.yml 新增 stage
migration-gate:
  stage: quality
  script:
    - python scripts/migration_gate.py
```

---

## 4. Phase 3: 架构现代化 (Week 9-16)

### 4.1 工作项 3a — 双 DAG Phase 3 完成

**门禁条件**:
- `tests/unit/test_dag_planner.py` 通过率 ≥ 90%
- `tests/integration/test_dry_run.py` 通过率 ≥ 90%
- `golden_traces` 与旧 planner 100% 一致
- 新 planner 不低于旧 planner 的通过率

**操作**: `git rm src/abi/plugins/metagenomic_plasmid/_engine/planner.py`

### 4.2 工作项 3b — 插件 Pydantic 推广（观察期）

**目标**: 在 2b（`ABIConfig` 基类）落地后，观察 3 个月再评估是否推广到全部插件。

**变更文件**:
- `plugins/*/config_default.yaml` (各插件，按需)

**策略（v1.1 修订）**: 不一刀切推广。先在 2b 验证 `ABIConfig` 的收益和迁移成本，确认收益后再逐插件推广。避免为一致性而一致性。

### 4.3 工作项 3c — `abi doctor` 命令

**变更文件**:
- `src/abi/doctor.py` (新增)
- `src/abi/cli.py` (新增命令)

**核心类**:

```python
@dataclass
class HealthCheck:
    name: str
    status: str      # passed | warning | failed | skipped
    message: str
    details: dict = field(default_factory=dict)

class Doctor:
    def run_all(self, *, analysis_type=None):
        checks = []
        checks.append(self._check_python())
        checks.append(self._check_plugins())
        if analysis_type:
            checks.append(self._check_resources(analysis_type))
            checks.append(self._check_tools(analysis_type))
        return HealthReport(checks=checks)
```

### 4.4 工作项 3g — 测试覆盖率持续提升

**目标（v1.1 修订）**: 覆盖率提升改为持续目标，不作为硬性里程碑。每次 PR 不下降即可，整体趋势向 80% 靠拢。

---

## 5. API 设计参考

### 5.1 ResourceDownloader 使用示例

```python
# 在任何插件中使用：
from abi.resource_downloader import ResourceDownloader, DownloadSpec

downloader = ResourceDownloader(
    root=Path(config.get("resources", {}).get("root", "resources")),
    dry_run=False,
    mock=False,
)

result = downloader.ensure(DownloadSpec(
    resource_id="genomad_db",
    tool_id="genomad",
    command=["genomad", "download-database", str(target)],
    ready_check="non_empty_dir",
))

if result.status != "ok":
    raise RuntimeError(f"Resource {result.resource_id}: {result.message}")
```

### 5.2 配置 Pydantic 模型使用示例

```python
from abi.config_models import ABIConfig

# 在 load_config() 中返回
config = ABIConfig(**raw_config)
print(config.outdir)           # 类型安全
print(config.execution.workers)  # 嵌套类型安全
```

### 5.3 Plugin Protocol 验证使用示例

```python
from abi.plugins.validator import validate_plugin_class

# 在 _load_entry_point_plugins() 中
try:
    validate_plugin_class(plugin_class)
    plugin = plugin_class()
except ValueError as e:
    warnings.warn(f"Skipping plugin: {e}")
```

---

## 6. 测试门禁指标

| 测试套件 | 当前 | Phase 2 目标 | Phase 3 目标 | 测量方式 |
|:---|:---:|:---:|:---:|:---|
| `tests/unit/` | 723 passed | 750+ | 800+ | `pytest tests/unit/ -q` |
| `tests/unit/test_dag_planner.py` | 现有 | ≥ 90% | ≥ 95% | `pytest --tb=short --junitxml=r.xml` |
| `tests/integration/test_dry_run.py` | 现有 | ≥ 90% | ≥ 95% | `pytest --tb=short --junitxml=r.xml` |
| `tests/` 覆盖率 | 60% | 65% | 持续向 80% 靠拢 | `pytest --cov=src/abi --cov-report=term` |
| `golden_traces/` | 现有 | 100% 一致 | 100% 一致 | `diff -r` |
| `ruff check` | 通过 | 通过 | 通过 | `ruff check src/ tests/` |
| `mypy` | 现有 | 通过 | 通过 | `mypy src/abi/` |

---

## 7. 风险与回退方案

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---:|:---:|:---|
| 双 DAG 迁移导致 metagenomic_plasmid 计划出错 | 中 | 高 | `ABI_DAG_PLANNER_LEGACY=1` 回退；逐 hook 切换 + golden file 对比测试 |
| Pydantic 模型破坏向后兼容 | 中 | 中 | `load_config()` 同时返回 `ABIConfig` + `dict`，兼容模式 2 个发布周期 |
| MCP 工具参数变化导致已有客户端断裂 | 低 | 中 | 保持 `TOOL_ALIASES` 不变；函数名和参数名完全一致 |
| ResourceDownloader 文件锁死锁 | 低 | 低 | `lock_timeout=300s` 超时回退到非原子模式 |
| `atomic=False` 第三方脚本中断残留 | 中 | 低 | 命令失败时 `_cleanup_partial()` 清空目标目录 |
| 64 个未提交改动堆积无回滚点 | 中 | 中 | 立即按工作项拆成原子提交，建立回滚点 |

---

## 附录 A: 变更文件完整清单

按阶段排列的完整文件变更列表：

```
Phase 1:
  [NEW]  src/abi/mcp/_tool_factory.py
  [MOD] src/abi/mcp/server.py
  [MOD] src/abi/tools.py (SafeFormatDict 增强)
  [NEW] src/abi/contracts/lint_template.py
  [MOD] src/abi/cli.py (lint-template 命令)
  [NEW] src/abi/resource_downloader.py (已存在, 扩展 source_files + atomic)
  [MOD] src/abi/resources.py (amplicon_16s + wgs_bacteria + reference + manual_bundle 迁移)

Phase 2:
  [MOD] src/abi/tables.py (线程安全)
  [NEW] src/abi/config_models.py
  [NEW] src/abi/plugins/validator.py
  [MOD] src/abi/plugins/__init__.py
  [MOD] src/abi/dag_planner.py (增强)
  [MOD] src/abi/plugins/metagenomic_plasmid/_engine/planner.py (逐步删除 legacy)
  [MOD] src/abi/tools.py (ToolRegistry.env_for)
  [NEW] scripts/migration_gate.py
  [MOD] .github/workflows/ci.yml
  [MOD] plugins/metagenomic_plasmid/pipeline_dag.yaml (常量迁入)
  [MOD] plugins/metagenomic_plasmid/config_default.yaml (常量迁入)
  [MOD] tests/unit/test_dag_planner.py (golden file 对比测试)

Phase 3:
  [DEL] src/abi/plugins/metagenomic_plasmid/_engine/planner.py
  [NEW] src/abi/doctor.py
  [MOD] src/abi/cli.py (doctor 命令)
  [MOD] plugins/*/config_default.yaml (各插件, 按需推广 Pydantic)
  [MOD] plugins/*/pipeline_dag.yaml (验证)
```

---

## 附录 B: 执行检查清单

### 每次提交前

- [ ] `ruff check src/ tests/`
- [ ] `ruff format --check src/ tests/`
- [ ] `mypy src/abi/ --ignore-missing-imports`
- [ ] `pytest tests/unit/ -q --tb=short`
- [ ] 新增代码有对应的单元测试

### 每次 PR 合并前

- [ ] 所有 CI 通过
- [ ] 覆盖率不下降
- [ ] 无 TODO/FIXME 残留（允许标记后续工作项的 TODO）
- [ ] code review 完成

### Phase 切换前

- [ ] 当前 Phase 所有工作项标记完成
- [ ] 门禁测试通过
- [ ] `golden_traces` 与基线一致
- [ ] 无关键性回退

---

## 附录 C: v1.1 修订说明 (2026-07-05)

基于对远程分支 `codex/abi-refactor-plan` 实际实现进度的核查，对 v1.0 做以下修订：

### 删除项
- **3d SQLite 运行元数据库** — 移出本次重构。无证据驱动的需求，引入新持久化层偏离加固主题。如需运行元数据追踪，单独立项。

### 重设项
- **1d ResourceDownloader** — 反映实际实现路径（`src/abi/resource_downloader.py`，非 `src/abi/resources/downloader.py`）。补齐设计改为 4 步：reference_resources 直接迁移 / manual_bundle 扩展 `source_files` 字段 / amplicon_16s 用 `atomic=False` 兼容第三方脚本 / rnaseq 辅助能力复用（不强行统一）。
- **2e 双 DAG 迁移** — 从"6 周大爆炸"改为"4 周渐进式"。新增 `ABI_DAG_PLANNER_LEGACY` feature flag + golden file 对比测试作为硬门。6 个阶段逐 hook 切换，每步可独立回滚。

### 调整项
- **3b 插件 Pydantic 推广** — 从"所有插件一刀切"改为"2b 落地后观察 3 个月再评估"。
- **3g 测试覆盖率** — 从"硬性 80% 里程碑"改为"持续目标，每次 PR 不下降"。

### 新增风险项
- `atomic=False` 第三方脚本中断残留 — 命令失败时 `_cleanup_partial()` 清空目标目录
- 64 个未提交改动堆积 — 立即按工作项拆成原子提交，建立回滚点
