"""Public ABI plugin interfaces -- the contract every plugin must fulfill.

This module defines three ``Protocol`` classes that plugins implement. A
plugin is a Python package that provides a concrete class conforming to one
of these protocols. The ABI core discovers plugins via entry points and
calls their methods in a defined lifecycle.

**Plugin lifecycle / 插件生命周期**

1. **Discovery** -- the ABI core scans installed Python packages for
   ``abi_plugins`` entry points. Each entry point returns a class object.
2. **Initialization** (optional) -- if the class implements
   ``ABIInitializablePlugin``, the core sets ``plugin.root`` before any
   other method is called.
3. **Config loading** -- ``load_config()`` reads the plugin's config file
   and returns a validated settings dictionary.
4. **Plan building** -- ``build_plan()`` takes the config and produces an
   ``ABIExecutionPlan``.
5. **Execution** -- the executor iterates ``plan.steps``, calling each
   tool's handler (tools are registered via ``registry()``).
6. **Dry run** (optional) -- if the plugin implements ``ABIDryRunPlugin``,
   ``execute_dry_run()`` simulates execution without side effects.
7. **Report** -- ``write_report()`` generates final output reports.

**Why Protocols? / 为何使用 Protocol？**
``typing.Protocol`` gives us structural subtyping: a plugin does NOT need to
inherit from ``ABIPlugin``; it only needs to provide the right attributes
and methods. This avoids forcing all plugins into a single inheritance tree
and makes testing easier (mock plugins are plain objects).
Protocol 提供结构化子类型：插件无需继承 ABIPlugin，只需提供正确的属性和方法。
这避免了将所有插件强制纳入单一继承树，也使测试更简单（mock 插件是普通对象）。

**Naming convention / 命名规范**

* ``ABIPlugin`` -- base protocol for all plugins.
* ``ABIDryRunPlugin`` -- extends ``ABIPlugin`` with dry-run capability.
* ``ABIInitializablePlugin`` -- extends ``ABIPlugin`` with a ``root``
  attribute for file-system-aware plugins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol

from abi.schemas import ABIExecutionPlan
from abi.tools import ToolRegistry

__all__ = [
    "ABIDryRunPlugin",
    "ABIInitializablePlugin",
    "ABIPlugin",
]


class ABIPlugin(Protocol):
    """Base protocol that every ABI plugin must satisfy.

    A plugin is identified by four metadata attributes and must provide six
    methods. The methods are called in lifecycle order: ``load_config`` →
    ``build_plan`` → ``registry`` (for tool access) → ``parse_outputs``
    (per-tool) → ``write_report`` (final).
    插件由四个元数据属性标识，必须提供六个方法。方法按生命周期顺序调用：
    load_config → build_plan → registry（工具访问）→ parse_outputs（每个工具）
    → write_report（最终）。
    """

    # ── Plugin metadata / 插件元数据 ──
    # These attributes are read by the ABI core at discovery time and
    # presented to users in the plugin list. They act as the plugin's
    # "identity card."
    # 这些属性在发现时被 ABI 核心读取，并在插件列表中呈现给用户。
    # 它们如同插件的"身份证"。

    plugin_id: str
    # Unique plugin identifier (e.g. "plasmidfinder", "plasforest").
    # Used as the entry-point name and in error messages.
    # 唯一插件标识符（如 "plasmidfinder"、"plasforest"）。
    # 用作入口点名和错误消息中的标识。

    display_name: str
    # Human-readable name shown in the dashboard and CLI (e.g. "PlasmidFinder").
    # 在仪表盘和 CLI 中显示的人类可读名称（如 "PlasmidFinder"）。

    description: str
    # One-line description of what the plugin does. Shown in help text.
    # 插件功能的单行描述。显示在帮助文本中。

    report_title: str
    # Title used in the generated report (e.g. "PlasmidFinder Results").
    # 在生成的报告中使用的标题（如 "PlasmidFinder Results"）。

    # ── Lifecycle methods / 生命周期方法 ──

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Load and validate the plugin's configuration.

        **Parameters / 参数:**
        * ``config_path`` -- path to a YAML/TOML config file. If ``None``,
          the plugin loads its built-in defaults.
        * ``profile`` -- optional config profile name (for plugins that
          support multiple named profiles within one file).
        * ``overrides`` -- key-value pairs that override config file values.
          Applied last, after defaults and file loading.

        **Returns / 返回:**
        A dictionary of validated configuration values. The keys are
        plugin-specific; the ABI core treats this as opaque and passes it
        straight to ``build_plan()``.

        **Validation / 校验:**
        This method should validate all values and raise ``ConfigError``
        on any problem. Do NOT defer validation to ``build_plan()`` --
        fail fast at config time so the user gets immediate feedback.
        此方法应校验所有值，遇到任何问题抛出 ConfigError。
        不要将校验推迟到 build_plan() -- 在配置阶段快速失败，使用户即时获得反馈。
        """
        ...

    def build_plan(
        self,
        config: Mapping[str, Any],
        *,
        check_files: bool = True,
    ) -> ABIExecutionPlan:
        """Build the execution plan from validated configuration.

        **Parameters / 参数:**
        * ``config`` -- the dictionary returned by ``load_config()``.
        * ``check_files`` -- if True, verify that referenced files (reads,
          assemblies, references) exist on disk. Set to False for dry-run
          or testing where files may not be available.

        **Returns / 返回:**
        An ``ABIExecutionPlan`` with all steps ordered and annotated.

        **Design note / 设计说明:**
        This is the core "intelligence" method. The plan builder must:
        1. Inspect the sample collection (samples, platforms, groups).
        2. Select appropriate tools from ``self.registry()``.
        3. Order steps so that dependencies are satisfied.
        4. Set ``step.inputs`` to point to concrete files.
        这是核心"智能"方法。计划构建器必须：检查样本集合、从 registry() 选择工具、
        排定步骤顺序以满足依赖、设置 step.inputs 指向具体文件。
        """
        ...

    def registry(self) -> ToolRegistry:
        """Return the plugin's ``ToolRegistry``.

        The registry maps ``tool_id`` strings to tool handler objects.
        The ABI core calls this after ``build_plan()`` to look up tool
        metadata (version, schema, executor) for each step in the plan.

        **Why separate from build_plan? / 为何与 build_plan 分离？**
        The registry is an object, not a dict, because it carries tool
        metadata and validation logic. Keeping it as a separate method
        lets the core access tool info without re-building the plan.
        registry 是一个对象而非字典，因为它携带着工具元数据和校验逻辑。
        将其作为独立方法使核心可以在不重新构建计划的情况下访问工具信息。
        """
        ...

    def table_schemas(self) -> Mapping[str, Iterable[str]]:
        """Return the expected output table schemas for result validation.

        Maps table name (e.g. "plasmid_calls") → list of expected column
        names (e.g. ["contig_id", "plasmid_type", "length", "coverage"]).

        **Why this exists / 为何存在:**
        The result validator uses these schemas to check that tool outputs
        contain the expected columns. If a tool's output format changes,
        this method must be updated so validation catches the mismatch.
        结果校验器使用这些 schema 来检查工具输出是否包含预期列。
        如果工具输出格式发生变化，此方法必须更新以便校验器捕获不匹配。
        """
        ...

    def parse_outputs(
        self,
        tool_id: str,
        output_dir: str | Path,
        sample_id: str,
    ) -> Mapping[str, Iterable[Mapping[str, Any]]]:
        """Parse a tool's output into structured data for reports and
        downstream consumption.

        **Parameters / 参数:**
        * ``tool_id`` -- the tool whose output to parse.
        * ``output_dir`` -- directory where the tool wrote its results.
        * ``sample_id`` -- the sample context (for per-sample outputs).

        **Returns / 返回:**
        A mapping of table name → iterable of row dicts. Each row dict maps
        column name to value. This structure is consumed by ``abi_validate_result``
        and the report writer.

        **Design note / 设计说明:**
        This method exists because tools produce wildly different output
        formats (CSV, TSV, JSON, custom formats). The parser normalizes
        everything into a uniform table-of-dicts representation that the
        rest of ABI can consume without format-specific logic.
        此方法的存在是因为各工具产生截然不同的输出格式（CSV、TSV、JSON、
        自定义格式）。解析器将所有格式统一规范化为字典表格表示，使
        ABI 的其余部分无需处理格式特定逻辑即可消费。
        """
        ...

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        """Generate the final analysis report.

        **Parameters / 参数:**
        * ``plan`` -- the ``ABIExecutionPlan`` that was executed.
        * ``result_dir`` -- directory containing all tool outputs.

        **Returns / 返回:**
        A mapping of report section name (e.g. "summary", "plasmid_calls")
        → path to the generated report file.

        **Implementor notes / 实现者注意事项:**
        * The report should be self-contained (inline all assets, use
          relative paths, or embed images as base64).
        * Large tables should be paginated or summarized.
        * The return dict keys should match the keys in ``table_schemas()``
          so the result validator can cross-check.
        报告应自包含（内联所有资产、使用相对路径或将图片嵌入为 base64）。
        大表格应分页或汇总。返回字典的键应与 table_schemas() 中的键匹配
        ，以便结果校验器交叉检查。
        """
        ...


class ABIDryRunPlugin(ABIPlugin, Protocol):
    """Plugin that supports dry-run execution.

    A dry run simulates the entire execution without side effects:
    no files are written, no subprocesses are spawned (or they run with
    ``--dry-run`` flags). The output is a directory of *predicted* outputs
    that can be diffed against the real outputs after an actual run.

    **Why a separate protocol? / 为何是单独的协议？**
    Not all plugins support dry-run. Making it a separate protocol lets
    the ABI core check ``isinstance(plugin, ABIDryRunPlugin)`` before
    offering dry-run to the user, and lets plugin authors opt in only
    when they are ready to maintain the dry-run path.
    并非所有插件都支持 dry-run。将其作为单独的协议使 ABI 核心可以在向用户
    提供 dry-run 前检查 isinstance(plugin, ABIDryRunPlugin)，也让插件作者
    仅在准备好维护 dry-run 路径时才选择加入。
    """

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        """Simulate execution and return predicted output paths.

        **Parameters / 参数:**
        * ``plan`` -- the ``ABIExecutionPlan`` to simulate.
        * ``config`` -- validated config from ``load_config()``.

        **Returns / 返回:**
        A mapping of step_id → predicted output directory path. These
        directories contain empty or template files with the same names
        and structure as the real output, but without real data.

        **Implementor notes / 实现者注意事项:**
        The dry run should be fast -- at least an order of magnitude faster
        than the real run. It should validate that all input files exist
        (if ``check_files=True`` in the plan) but should NOT run actual
        computations.
        dry-run 应该很快 -- 至少比真实运行快一个数量级。应校验所有输入文件
        是否存在（如果计划中 check_files=True），但不运行实际计算。
        """
        ...


class ABIInitializablePlugin(ABIPlugin, Protocol):
    """Plugin that needs a filesystem root before it can operate.

    Plugins that read asset files (templates, default configs, database
    indices) relative to their installation directory should implement this
    protocol. The ABI core sets ``plugin.root`` to the plugin package's
    directory on disk before calling any other method.

    **When to use / 何时使用:**
    * Your plugin ships data files inside its Python package.
    * Your plugin needs to resolve paths relative to its installation.
    * Your plugin loads default configurations from disk.

    **When NOT to use / 何时不使用:**
    * Your plugin is pure Python with no data files.
    * Your plugin reads all data from environment variables or APIs.
    * Your plugin is self-contained in a single module.

    **Lifecycle / 生命周期:**
    1. ABI core discovers plugin class.
    2. If ``issubclass(plugin_cls, ABIInitializablePlugin)`` → set
       ``plugin.root = Path(package.__path__[0])``.
    3. Call ``load_config()``, ``build_plan()``, etc. as normal.
    """
    root: Path
    # Absolute path to the plugin package's root directory.
    # Set by the ABI core after discovery, before any method call.
    # 插件包根目录的绝对路径。由 ABI 核心在发现后、任何方法调用前设置。
