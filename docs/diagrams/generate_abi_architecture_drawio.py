#!/usr/bin/env python3
"""Generate docs/diagrams/abi-architecture.drawio with architecture pages."""

from __future__ import annotations

from itertools import count
from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

_ID_SEQUENCE = count(1)


def _uid() -> str:
    return f"generated-{next(_ID_SEQUENCE)}"


def _cell(
    parent: Element,
    *,
    cell_id: str,
    value: str = "",
    style: str = "",
    vertex: bool = False,
    edge: bool = False,
    source: str | None = None,
    target: str | None = None,
    parent_id: str = "1",
    x: float = 0,
    y: float = 0,
    w: float = 120,
    h: float = 40,
) -> Element:
    attrs: dict[str, str] = {"id": cell_id, "parent": parent_id}
    if value:
        attrs["value"] = value
    if style:
        attrs["style"] = style
    if vertex:
        attrs["vertex"] = "1"
    if edge:
        attrs["edge"] = "1"
    if source:
        attrs["source"] = source
    if target:
        attrs["target"] = target
    cell = SubElement(parent, "mxCell", attrs)
    if vertex or edge:
        geom = SubElement(cell, "mxGeometry", {"relative": "1" if edge else "0", "as": "geometry"})
        if vertex:
            geom.set("x", str(x))
            geom.set("y", str(y))
            geom.set("width", str(w))
            geom.set("height", str(h))
    return cell


def _diagram_root(name: str) -> tuple[Element, Element]:
    diagram = Element(
        "diagram",
        {
            "id": _uid(),
            "name": name,
        },
    )
    model = SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "1422",
            "dy": "827",
            "grid": "1",
            "gridSize": "10",
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": "1600",
            "pageHeight": "1200",
            "math": "0",
            "shadow": "0",
        },
    )
    root = SubElement(model, "root")
    SubElement(root, "mxCell", {"id": "0"})
    SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    return diagram, root


# Styles
LAYER_AGENT = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;"
    "fontStyle=1;fontSize=13;"
)
LAYER_TRANSPORT = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
    "fontStyle=1;fontSize=12;"
)
LAYER_INTERFACE = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"
    "fontStyle=1;fontSize=12;"
)
LAYER_CORE = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;"
    "fontStyle=1;fontSize=12;"
)
LAYER_PLUGIN = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;"
    "fontStyle=1;fontSize=12;"
)
LAYER_RUNTIME = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;"
    "fontStyle=1;fontSize=12;"
)
LAYER_EXTERNAL = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;"
    "fontStyle=1;fontSize=12;"
)
BOX = "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#333333;fontSize=11;"
BOX_BLUE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=11;"
BOX_GREEN = "rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=11;"
BOX_ORANGE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=11;"
BOX_YELLOW = "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;"
BOX_PURPLE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=11;"
BOX_RED = "rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=11;"
CALLOUT = (
    "shape=callout;whiteSpace=wrap;html=1;perimeter=calloutPerimeter;fillColor=#fff2cc;"
    "strokeColor=#d6b656;fontSize=10;position=0.5;size=20;position2=0.5;"
)
SWIMLANE = (
    "swimlane;whiteSpace=wrap;html=1;startSize=30;fillColor=#f5f5f5;strokeColor=#666666;"
    "fontStyle=1;fontSize=12;"
)
DIAMOND = "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;"
LEGEND = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#999999;fontSize=10;"
    "align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;"
)
TREE = (
    "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#333333;fontSize=10;"
    "align=left;verticalAlign=top;spacingLeft=8;spacingTop=4;fontFamily=Courier New;"
)
EDGE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
    "strokeColor=#333333;"
)
EDGE_DATA = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
    "strokeColor=#6c8ebf;dashed=1;"
)
EDGE_CONFIG = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
    "strokeColor=#82b366;dashed=1;dashPattern=8 8;"
)
TITLE_TEXT = (
    "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;"
    "fontSize=18;fontStyle=1;"
)
FOOTER_TEXT = (
    "text;html=1;strokeColor=none;fillColor=none;align=left;fontSize=9;fontColor=#666666;"
)


def build_page1() -> Element:
    diagram, root = _diagram_root("01-系统分层总览")

    # Title
    _cell(
        root,
        cell_id="p1-title",
        value="ABI 系统分层总览 / System Layers",
        style=TITLE_TEXT,
        vertex=True,
        x=400,
        y=20,
        w=500,
        h=40,
    )

    layers = [
        (
            "p1-layer-agent",
            "Agent 平台层<br><i>Claude / ChatGPT / Cursor / HTTP Client</i>",
            LAYER_AGENT,
            80,
            80,
            1200,
            60,
        ),
        (
            "p1-layer-transport",
            "薄传输层 Thin Transport<br>CLI (cli.py) │ MCP (mcp/server.py) │ "
            "Job Service (jobs/service.py) │ Tool Export (tool_descriptors.py)",
            LAYER_TRANSPORT,
            80,
            160,
            1200,
            70,
        ),
        (
            "p1-layer-interface",
            "ABIAgentInterface<br>统一 JSON 信封 + 权限门控 + dispatch() 路由",
            LAYER_INTERFACE,
            80,
            250,
            1200,
            55,
        ),
        (
            "p1-layer-core",
            "厚核心 Thick Core<br>executor │ dag_planner │ tools │ contracts │ provenance │ "
            "diagnostics │ resources │ sciplot │ results",
            LAYER_CORE,
            80,
            325,
            1200,
            70,
        ),
        (
            "p1-layer-plugin",
            "清洁插件 Clean Plugins (7)<br>metagenomic_plasmid │ easymetagenome │ "
            "rnaseq_expression │ wgs_bacteria │ amplicon_16s │ metatranscriptomics │ "
            "viral_viwrap",
            LAYER_PLUGIN,
            80,
            415,
            1200,
            70,
        ),
        (
            "p1-layer-runtime",
            "运行时 Runtimes<br>LocalRuntime │ NextflowRuntime │ HpcRuntime │ Docker",
            LAYER_RUNTIME,
            80,
            505,
            1200,
            55,
        ),
        (
            "p1-layer-external",
            "外部世界 External<br>Bioinformatics Tools (fastp, SPAdes, Kraken2, ...) + "
            "Conda/Mamba Environments",
            LAYER_EXTERNAL,
            80,
            580,
            1200,
            55,
        ),
    ]
    for cid, val, style, x, y, w, h in layers:
        _cell(root, cell_id=cid, value=val, style=style, vertex=True, x=x, y=y, w=w, h=h)

    # SSOT boxes
    ssots = [
        (
            "p1-ssot-tools",
            "SSOT: tool_descriptors.py<br>ABI_AGENT_TOOLS + PROVIDER_PROFILES",
            BOX_BLUE,
            900,
            160,
            360,
            50,
        ),
        (
            "p1-ssot-dag",
            "SSOT: pipeline_dag.yaml<br>UniversalDAG + build_plan_from_dag()",
            BOX_GREEN,
            900,
            325,
            360,
            50,
        ),
        (
            "p1-ssot-contract",
            "SSOT: tool_contracts/*.yaml<br>GenericCommandSkill",
            BOX_ORANGE,
            900,
            415,
            360,
            50,
        ),
    ]
    for cid, val, style, x, y, w, h in ssots:
        _cell(root, cell_id=cid, value=val, style=style, vertex=True, x=x, y=y, w=w, h=h)

    # Principles callout
    principles = (
        "六大设计原则<br>"
        "1. 厚核心、薄传输<br>"
        "2. 插件拥有生物学，核心拥有机制<br>"
        "3. Agent 永不编码（JSON 信封）<br>"
        "4. 执行需门控（confirm_execution）<br>"
        "5. 声明式优于手写（DAG + YAML）<br>"
        "6. Wire-format 无关（返回 JSON 字符串）"
    )
    _cell(
        root,
        cell_id="p1-principles",
        value=principles,
        style=CALLOUT,
        vertex=True,
        x=80,
        y=660,
        w=380,
        h=160,
    )

    # Legend
    legend = (
        "图例 Legend<br>"
        "■ 蓝色 = 传输层 Transport<br>"
        "■ 绿色 = 核心层 Core<br>"
        "■ 橙色 = 插件层 Plugin<br>"
        "■ 紫色 = 运行时 Runtime<br>"
        "■ 红色 = 外部工具 External<br>"
        "→ 实线 = 同步调用<br>"
        "⇢ 虚线 = 配置/数据依赖"
    )
    _cell(
        root,
        cell_id="p1-legend",
        value=legend,
        style=LEGEND,
        vertex=True,
        x=500,
        y=660,
        w=280,
        h=160,
    )

    # Footer refs
    _cell(
        root,
        cell_id="p1-footer",
        value="关键源文件: src/abi/agent/interface.py │ src/abi/cli.py │ "
        "src/abi/mcp/server.py │ src/abi/jobs/service.py │ src/abi/tool_descriptors.py",
        style=FOOTER_TEXT,
        vertex=True,
        x=80,
        y=860,
        w=1200,
        h=30,
    )

    # Vertical flow arrows between layers
    layer_ids = [layer[0] for layer in layers]
    for src, tgt in zip(layer_ids, layer_ids[1:]):
        _cell(root, cell_id=_uid(), style=EDGE, edge=True, source=src, target=tgt, parent_id="1")

    # SSOT config edges (dashed) from transport/core to SSOT
    for src, tgt in [
        ("p1-layer-transport", "p1-ssot-tools"),
        ("p1-layer-core", "p1-ssot-dag"),
        ("p1-layer-plugin", "p1-ssot-contract"),
    ]:
        _cell(
            root,
            cell_id=_uid(),
            style=EDGE_CONFIG,
            edge=True,
            source=src,
            target=tgt,
            parent_id="1",
        )

    return diagram


def build_page2() -> Element:
    diagram, root = _diagram_root("02-Agent生命周期")

    _cell(
        root,
        cell_id="p2-title",
        value="Agent 生命周期与数据流 / Lifecycle Flow",
        style=TITLE_TEXT,
        vertex=True,
        x=400,
        y=20,
        w=500,
        h=40,
    )

    swimlanes = [
        ("p2-lane-agent", "Agent", 40, 80, 180, 700),
        ("p2-lane-if", "ABIAgentInterface", 240, 80, 200, 700),
        ("p2-lane-plugin", "Plugin", 460, 80, 180, 700),
        ("p2-lane-exec", "Executor", 660, 80, 180, 700),
        ("p2-lane-runtime", "Runtime", 860, 80, 160, 700),
        ("p2-lane-ext", "External Tools", 1040, 80, 160, 700),
    ]
    for cid, title, x, y, w, h in swimlanes:
        _cell(root, cell_id=cid, value=title, style=SWIMLANE, vertex=True, x=x, y=y, w=w, h=h)

    steps = [
        ("p2-s1", "1. list_types()", BOX, "p2-lane-agent", 20, 50, 140, 36),
        ("p2-s2", "2. plan()", BOX, "p2-lane-if", 20, 110, 160, 36),
        ("p2-s3", "load_config()<br>build_plan()", BOX_GREEN, "p2-lane-plugin", 20, 110, 140, 50),
        (
            "p2-s4",
            "build_plan_from_dag()<br>pipeline_dag.yaml",
            BOX_GREEN,
            "p2-lane-plugin",
            20,
            180,
            140,
            50,
        ),
        ("p2-s5", "3. dry_run()", BOX, "p2-lane-if", 20, 260, 160, 36),
        ("p2-s6", "execute(dry_run=True)", BOX_GREEN, "p2-lane-exec", 20, 260, 140, 36),
        ("p2-s7", "4. inspect()", BOX, "p2-lane-if", 20, 330, 160, 36),
        ("p2-s8", "5. run(confirm=false)", BOX_YELLOW, "p2-lane-if", 20, 400, 160, 40),
        ("p2-s9", "confirmation_required", BOX_YELLOW, "p2-lane-agent", 20, 400, 140, 40),
        ("p2-s10", "6. run(confirm=true)", BOX_RED, "p2-lane-if", 20, 470, 160, 40),
        ("p2-s11", "runtime.run()", BOX_PURPLE, "p2-lane-runtime", 20, 470, 120, 40),
        ("p2-s12", "execute(dry_run=False)", BOX_GREEN, "p2-lane-exec", 20, 470, 140, 40),
        ("p2-s13", "ToolSkill.run()", BOX_RED, "p2-lane-ext", 20, 470, 120, 40),
        ("p2-s14", "7. report()", BOX, "p2-lane-if", 20, 560, 160, 36),
    ]
    for cid, val, style, parent_id, x, y, w, h in steps:
        _cell(
            root,
            cell_id=cid,
            value=val,
            style=style,
            vertex=True,
            parent_id=parent_id,
            x=x,
            y=y,
            w=w,
            h=h,
        )

    # Envelope branches
    _cell(
        root,
        cell_id="p2-envelope",
        value=(
            "JSON 信封三态<br>"
            "● success → result 载荷<br>"
            "● confirmation_required → 仅 run 触发<br>"
            "● error → error_code + diagnostic_hints"
        ),
        style=BOX_YELLOW,
        vertex=True,
        x=1240,
        y=120,
        w=280,
        h=100,
    )

    # Permission levels
    _cell(
        root,
        cell_id="p2-perm",
        value=(
            "权限三级 permissions.py<br>"
            "read_only: list_types, inspect, query<br>"
            "planning_write: plan, dry_run, report<br>"
            "execution: run (需 confirm)"
        ),
        style=BOX_BLUE,
        vertex=True,
        x=1240,
        y=250,
        w=280,
        h=100,
    )

    # Output tree
    _cell(
        root,
        cell_id="p2-outdir",
        value=(
            "outdir/ 标准产物<br>"
            "├── execution_plan.json<br>"
            "├── provenance/<br>"
            "│   ├── commands.tsv<br>"
            "│   ├── checksums.json<br>"
            "│   └── run_summary.json<br>"
            "├── tables/*.tsv<br>"
            "├── report/report.md<br>"
            "└── figures/ (SciPlot)"
        ),
        style=TREE,
        vertex=True,
        x=1240,
        y=400,
        w=280,
        h=200,
    )

    # Sequence arrows
    seq_edges = [
        ("p2-s1", "p2-s2"),
        ("p2-s2", "p2-s3"),
        ("p2-s3", "p2-s4"),
        ("p2-s5", "p2-s6"),
        ("p2-s8", "p2-s9"),
        ("p2-s10", "p2-s11"),
        ("p2-s11", "p2-s12"),
        ("p2-s12", "p2-s13"),
    ]
    for src, tgt in seq_edges:
        _cell(root, cell_id=_uid(), style=EDGE, edge=True, source=src, target=tgt, parent_id="1")

    _cell(
        root,
        cell_id="p2-footer",
        value="关键源文件: src/abi/agent/interface.py │ src/abi/agent/envelopes.py │ "
        "src/abi/permissions.py │ src/abi/results.py",
        style=FOOTER_TEXT,
        vertex=True,
        x=40,
        y=820,
        w=1200,
        h=30,
    )
    return diagram


def build_page3() -> Element:
    diagram, root = _diagram_root("03-单步执行实现")

    _cell(
        root,
        cell_id="p3-title",
        value="单步执行实现 / Step Execution Detail",
        style=TITLE_TEXT,
        vertex=True,
        x=400,
        y=20,
        w=500,
        h=40,
    )

    _cell(
        root,
        cell_id="p3-plan",
        value="ExecutionPlan<br>遍历 steps",
        style=BOX,
        vertex=True,
        x=600,
        y=80,
        w=160,
        h=50,
    )
    _cell(
        root,
        cell_id="p3-loop",
        value="_execute_step()",
        style=BOX_GREEN,
        vertex=True,
        x=600,
        y=160,
        w=160,
        h=40,
    )
    _cell(
        root,
        cell_id="p3-branch",
        value="节点类型?",
        style=DIAMOND,
        vertex=True,
        x=610,
        y=230,
        w=140,
        h=80,
    )

    # External path (left)
    _cell(
        root,
        cell_id="p3-ext-label",
        value="external 外部工具",
        style="text;html=1;fontStyle=1;fontSize=12;",
        vertex=True,
        x=120,
        y=230,
        w=140,
        h=30,
    )
    ext_nodes = [
        ("p3-pre", "verify_input_checksums<br>Pre-execution", 120, 300, 200, 50),
        ("p3-registry", "ToolRegistry<br>查找 tool_contract", 120, 380, 200, 50),
        ("p3-skill", "GenericCommandSkill<br>build_command + run()", 120, 460, 200, 50),
        ("p3-sub", "subprocess<br>Conda PATH 前置", 120, 540, 200, 50),
        ("p3-post", "validate_output_contract<br>Post-execution", 120, 620, 200, 50),
        ("p3-parse", "parse_outputs<br>TSVMapper / parsers.yaml", 120, 700, 200, 50),
    ]
    for cid, val, x, y, w, h in ext_nodes:
        _cell(root, cell_id=cid, value=val, style=BOX_BLUE, vertex=True, x=x, y=y, w=w, h=h)

    # Internal path (right)
    _cell(
        root,
        cell_id="p3-int-label",
        value="internal 内部处理",
        style="text;html=1;fontStyle=1;fontSize=12;",
        vertex=True,
        x=1000,
        y=230,
        w=140,
        h=30,
    )
    int_nodes = [
        ("p3-ih-spec", "internal_handler_spec()<br>解析 handler_id", 980, 300, 220, 50),
        ("p3-ih-ctx", "InternalHandlerContext<br>outdir / provenance / tables", 980, 380, 220, 50),
        ("p3-ih-run", "ABIInternalHandler.run()<br>Python 函数执行", 980, 460, 220, 50),
        ("p3-ih-result", "InternalHandlerResult<br>tables + artifacts", 980, 540, 220, 50),
    ]
    for cid, val, x, y, w, h in int_nodes:
        _cell(root, cell_id=cid, value=val, style=BOX_ORANGE, vertex=True, x=x, y=y, w=w, h=h)

    # Converge
    _cell(
        root,
        cell_id="p3-tables",
        value="StandardTableManager<br>append_rows()",
        style=BOX_GREEN,
        vertex=True,
        x=580,
        y=800,
        w=200,
        h=50,
    )
    _cell(
        root,
        cell_id="p3-prov",
        value="provenance/ + tables/<br>checksums.json 记录",
        style=BOX,
        vertex=True,
        x=580,
        y=880,
        w=200,
        h=50,
    )

    # Contract phases callout
    _cell(
        root,
        cell_id="p3-contract",
        value=(
            "合约验证三阶段 step_contract.py<br>"
            "Phase 1: Pre — 输入 checksum 校验<br>"
            "Phase 2: Post — 输出存在/大小/断言<br>"
            "Phase 3: Record — SHA256 写入 checksums.json"
        ),
        style=CALLOUT,
        vertex=True,
        x=80,
        y=80,
        w=320,
        h=120,
    )

    # Fail-fast
    _cell(
        root,
        cell_id="p3-failfast",
        value="Fail-fast: 第一步失败即停止<br>但溯源产物始终写出",
        style=BOX_RED,
        vertex=True,
        x=80,
        y=220,
        w=280,
        h=50,
    )

    # Parallel
    _cell(
        root,
        cell_id="p3-parallel",
        value="并行: config.execution.parallel<br>ThreadPoolExecutor per-sample",
        style=BOX_PURPLE,
        vertex=True,
        x=80,
        y=300,
        w=280,
        h=50,
    )

    # Legend
    _cell(
        root,
        cell_id="p3-legend",
        value="图例: 蓝色=外部工具路径 │ 橙色=内部处理路径 │ 绿色=核心模块",
        style=LEGEND,
        vertex=True,
        x=80,
        y=880,
        w=320,
        h=50,
    )

    # Edges - main flow
    main_flow = [
        ("p3-plan", "p3-loop"),
        ("p3-loop", "p3-branch"),
        ("p3-branch", "p3-pre"),
        ("p3-branch", "p3-ih-spec"),
        ("p3-pre", "p3-registry"),
        ("p3-registry", "p3-skill"),
        ("p3-skill", "p3-sub"),
        ("p3-sub", "p3-post"),
        ("p3-post", "p3-parse"),
        ("p3-parse", "p3-tables"),
        ("p3-ih-spec", "p3-ih-ctx"),
        ("p3-ih-ctx", "p3-ih-run"),
        ("p3-ih-run", "p3-ih-result"),
        ("p3-ih-result", "p3-tables"),
        ("p3-tables", "p3-prov"),
    ]
    for src, tgt in main_flow:
        _cell(root, cell_id=_uid(), style=EDGE, edge=True, source=src, target=tgt, parent_id="1")

    _cell(
        root,
        cell_id="p3-footer",
        value="关键源文件: src/abi/executor.py │ src/abi/tools.py │ "
        "src/abi/contracts/step_contract.py │ src/abi/internal.py │ src/abi/tsv_mapping.py",
        style=FOOTER_TEXT,
        vertex=True,
        x=80,
        y=980,
        w=1200,
        h=30,
    )
    return diagram


def build_page4() -> Element:
    diagram, root = _diagram_root("04-插件解剖")

    _cell(
        root,
        cell_id="p4-title",
        value="插件解剖与扩展指南 / Plugin Anatomy",
        style=TITLE_TEXT,
        vertex=True,
        x=400,
        y=20,
        w=500,
        h=40,
    )

    # EasyMetagenome column
    _cell(
        root,
        cell_id="p4-easy-header",
        value="easymetagenome（简洁插件）",
        style=SWIMLANE,
        vertex=True,
        x=40,
        y=80,
        w=520,
        h=30,
    )
    easy_tree = (
        "plugins/easymetagenome/<br>"
        "├── abi-plugin.yaml<br>"
        "├── pipeline_dag.yaml (34 nodes)<br>"
        "├── tool_registry.yaml<br>"
        "├── tool_contracts/*.yaml<br>"
        "├── parsers.yaml<br>"
        "├── standard_tables.yaml<br>"
        "├── config_default.yaml<br>"
        "└── figure_specs.yaml<br><br>"
        "src/abi/plugins/easymetagenome/<br>"
        "├── __init__.py (EasyMetagenomePlugin)<br>"
        "├── handlers.py (internal_handlers)<br>"
        "└── workflow.py (presets)"
    )
    _cell(
        root,
        cell_id="p4-easy-tree",
        value=easy_tree,
        style=TREE,
        vertex=True,
        x=60,
        y=130,
        w=480,
        h=340,
    )

    # Metagenomic plasmid column
    _cell(
        root,
        cell_id="p4-plasmid-header",
        value="metagenomic_plasmid（复杂插件）",
        style=SWIMLANE,
        vertex=True,
        x=600,
        y=80,
        w=520,
        h=30,
    )
    plasmid_tree = (
        "plugins/metagenomic_plasmid/<br>"
        "├── pipeline_dag.yaml (84 nodes)<br>"
        "├── tool_registry.yaml<br>"
        "├── tool_contracts/ (67 tools)<br>"
        "├── standard_tables.yaml<br>"
        "├── figure_specs.yaml (8 figures)<br>"
        "└── config_default.yaml<br><br>"
        "src/abi/plugins/metagenomic_plasmid/<br>"
        "└── _engine/ (40 modules, ~12k LOC)<br>"
        "    ├── pipeline.py<br>"
        "    ├── skills/ (custom ToolSkill)<br>"
        "    ├── normalize/<br>"
        "    └── report/<br><br>"
        "src/abi/autoplasm/ → 向后兼容 shim"
    )
    _cell(
        root,
        cell_id="p4-plasmid-tree",
        value=plasmid_tree,
        style=TREE,
        vertex=True,
        x=620,
        y=130,
        w=480,
        h=340,
    )

    # Core consumption points
    core_points = [
        ("p4-core-dag", "dag_planner.py<br>读取 pipeline_dag.yaml", BOX_GREEN, 200, 500, 220, 50),
        (
            "p4-core-tools",
            "ToolRegistry<br>读取 tool_registry.yaml<br>+ tool_contracts/",
            BOX_GREEN,
            480,
            500,
            220,
            50,
        ),
        ("p4-core-exec", "executor.py<br>调用 internal_handlers", BOX_GREEN, 760, 500, 220, 50),
        ("p4-core-parse", "TSVMapper<br>读取 parsers.yaml", BOX_GREEN, 200, 580, 220, 50),
        (
            "p4-core-report",
            "write_plugin_report()<br>+ sciplot figure_specs",
            BOX_GREEN,
            480,
            580,
            220,
            50,
        ),
        (
            "p4-core-entry",
            "plugins/__init__.py<br>entry_points abi.plugins",
            BOX_GREEN,
            760,
            580,
            220,
            50,
        ),
    ]
    for cid, val, style, x, y, w, h in core_points:
        _cell(root, cell_id=cid, value=val, style=style, vertex=True, x=x, y=y, w=w, h=h)

    # Arrows from plugin files to core
    config_edges = [
        ("p4-easy-tree", "p4-core-dag"),
        ("p4-plasmid-tree", "p4-core-dag"),
        ("p4-easy-tree", "p4-core-tools"),
        ("p4-plasmid-tree", "p4-core-tools"),
        ("p4-easy-tree", "p4-core-exec"),
        ("p4-easy-tree", "p4-core-parse"),
        ("p4-plasmid-tree", "p4-core-report"),
        ("p4-plasmid-tree", "p4-core-entry"),
    ]
    for src, tgt in config_edges:
        _cell(
            root,
            cell_id=_uid(),
            style=EDGE_CONFIG,
            edge=True,
            source=src,
            target=tgt,
            parent_id="1",
        )

    # Checklist
    checklist = (
        "新插件 8 步 Checklist<br>"
        "1. 实现 ABIPlugin Protocol (src/abi/plugins/&lt;name&gt;/)<br>"
        "2. 创建 abi-plugin.yaml, tool_registry.yaml, standard_tables.yaml<br>"
        "3. 添加 tool_contracts/*.yaml<br>"
        "4. 创建 pipeline_dag.yaml + build_plan_from_dag()<br>"
        "5. 简单解析用 parsers.yaml + TSVMapper<br>"
        "6. 无外部工具的步骤用 @internal_handler 注册<br>"
        "7. 在 pyproject.toml entry-points abi.plugins 注册<br>"
        "8. assert_plugin_contract(plugin) 测试验证"
    )
    _cell(
        root,
        cell_id="p4-checklist",
        value=checklist,
        style=CALLOUT,
        vertex=True,
        x=40,
        y=660,
        w=1080,
        h=140,
    )

    _cell(
        root,
        cell_id="p4-footer",
        value="关键源文件: src/abi/interfaces.py │ src/abi/plugins/__init__.py │ "
        "docs/en/plugin_development_guide.md",
        style=FOOTER_TEXT,
        vertex=True,
        x=40,
        y=840,
        w=1200,
        h=30,
    )
    return diagram


def build_page5() -> Element:
    diagram, root = _diagram_root("05-工作流深模块")

    _cell(
        root,
        cell_id="p5-title",
        value="第二期：工作流深模块 / Workflow Deepening",
        style=TITLE_TEXT,
        vertex=True,
        x=400,
        y=20,
        w=560,
        h=40,
    )

    boxes = [
        (
            "p5-adapters",
            "薄 Adapter<br>CLI │ MCP │ HTTP │ Legacy P0/run_viwrap",
            BOX_BLUE,
            80,
            100,
            300,
            70,
        ),
        (
            "p5-coordinator",
            "WorkflowCoordinator<br>prepare() │ dry_run() │ run()<br>隐藏 config → plan → runtime",
            BOX_GREEN,
            470,
            90,
            360,
            90,
        ),
        (
            "p5-result",
            "统一 ABI Result<br>plan │ provenance │ tables │ report │ resume identity",
            BOX_YELLOW,
            920,
            100,
            330,
            70,
        ),
        (
            "p5-catalog",
            "WorkflowCatalog<br>resolve(preset)<br>nodes │ capabilities │ resources",
            BOX_GREEN,
            210,
            280,
            300,
            90,
        ),
        (
            "p5-plugin",
            "Clean Plugin<br>生物学配置 │ sample context │ parser │ internal handlers",
            BOX_ORANGE,
            560,
            280,
            300,
            90,
        ),
        (
            "p5-runtime",
            "Runtime Adapters<br>Local │ HPC │ Nextflow",
            BOX_PURPLE,
            910,
            280,
            260,
            90,
        ),
        (
            "p5-easy",
            "EasyMetaGenome<br>catalog + canonical pipeline_dag.yaml<br>"
            "P0 compatibility 仅映射旧输入/输出",
            BOX_ORANGE,
            160,
            500,
            430,
            100,
        ),
        (
            "p5-viwrap",
            "ViWrap<br>viwrap_compat 作为结果等价 oracle<br>"
            "viral_native 分阶段通过 parity gate 后启用",
            BOX_ORANGE,
            710,
            500,
            430,
            100,
        ),
    ]
    for cid, value, style, x, y, width, height in boxes:
        _cell(
            root,
            cell_id=cid,
            value=value,
            style=style,
            vertex=True,
            x=x,
            y=y,
            w=width,
            h=height,
        )

    for source, target in (
        ("p5-adapters", "p5-coordinator"),
        ("p5-coordinator", "p5-result"),
        ("p5-catalog", "p5-coordinator"),
        ("p5-plugin", "p5-coordinator"),
        ("p5-coordinator", "p5-runtime"),
        ("p5-easy", "p5-plugin"),
        ("p5-viwrap", "p5-plugin"),
    ):
        _cell(root, cell_id=_uid(), style=EDGE, edge=True, source=source, target=target)

    _cell(
        root,
        cell_id="p5-rule",
        value=(
            "深模块验收<br>"
            "• preset 只在 catalog 声明<br>"
            "• transport 不组装 runtime<br>"
            "• plugin 不实现 provenance/resume<br>"
            "• compat/native 使用同一标准表与结果协议"
        ),
        style=CALLOUT,
        vertex=True,
        x=250,
        y=690,
        w=760,
        h=130,
    )

    _cell(
        root,
        cell_id="p5-footer",
        value="关键源文件: src/abi/workflow/catalog.py │ src/abi/workflow/execution.py │ "
        "plugins/*/workflows/catalog.yaml",
        style=FOOTER_TEXT,
        vertex=True,
        x=80,
        y=870,
        w=1200,
        h=30,
    )
    return diagram


def render() -> str:
    global _ID_SEQUENCE
    _ID_SEQUENCE = count(1)
    mxfile = Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "agent": "ABI-docs-generator",
            "version": "24.0.0",
            "type": "device",
        },
    )
    for builder in (build_page1, build_page2, build_page3, build_page4, build_page5):
        mxfile.append(builder())

    rough = tostring(mxfile, encoding="unicode")
    parsed = minidom.parseString(rough)
    pretty = parsed.toprettyxml(indent="  ")
    # Remove extra XML declaration line from minidom and add our own
    lines = pretty.split("\n")
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines)


def main() -> None:
    output = render()

    out_path = Path(__file__).with_name("abi-architecture.drawio")
    out_path.write_text(output, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
