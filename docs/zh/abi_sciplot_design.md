# `abi_sciplot` — ABI 科研图形编译器

> **定位**: `abi_sciplot` 是 ABI 的科研图形编译器 — Agent 负责描述图，ABI 负责验证、渲染、质检和导出。
>
> **核心协议**: `FigureSpec → Validate → Render → Export → Lint → Provenance`

## 1. 动机与边界

### 1.1 为什么需要 `abi_sciplot`

ABI 已有 `src/abi/figures/base.py` (FigureEngine, 587 行)，支持 7 种图形类型（bar, scatter, volcano, heatmap, boxplot, stacked_bar, pca），但存在以下限制：

| 维度 | 现有 FigureEngine | `abi_sciplot` 目标 |
|------|------------------|-------------------|
| 数据模型 | dataclass (无运行时验证) | Pydantic (JSON Schema, 严格验证) |
| 输出格式 | 仅 PNG | PDF + SVG + PNG + TIFF |
| 样式系统 | 硬编码 rcParams | YAML 主题系统 (abi_nature / abi_cell / abi_report) |
| 调色板 | 自由选择 (含 rainbow/jet) | 白名单调色板，禁用 jet/rainbow |
| 统计标注 | 无约束 (可无测试标星号) | StatSpec 强制执行 |
| 可复现性 | 无 provenance | SHA256 + 完整 provenance.json |
| 质量门禁 | 无 | FigureLint (ERROR/WARNING/INFO) |
| 期刊合规 | 无 | Nature 投稿规范检查 |

### 1.2 核心设计原则

1. **Agent 不直接画图** — Agent 只输出 `FigureSpec` YAML/JSON，渲染器执行
2. **每张图必须可追踪** — provenance.json 记录数据 hash、参数、版本
3. **图形质检必须成为硬门禁** — 不合格图不能进入最终报告
4. **样式与数据分离** — 主题/调色板独立于数据映射

### 1.3 第一版不做

| 功能 | 原因 |
|------|------|
| 复杂 network graph | 布局不稳定，审美和解释都容易漂移 |
| circos plot | 实现成本高，容易拖慢主线 |
| 自动选择统计检验 | 风险高，容易制造错误显著性 |
| Agent 自动写 Matplotlib 代码 | 不可控，破坏一致性 |
| R/ggplot2 强依赖 | 增加部署复杂度 |
| Altair 交互式渲染 | P1 后续迭代 |

---

## 2. 总体架构

```text
workflow output / analysis result
        │
        ▼
standard table + metadata
        │
        ▼
FigureSpec.yaml / FigureSpec.json
        │
        ▼
FigureSpecValidator (Pydantic)
        │
        ├── DataValidator (Pandera)
        ├── StatValidator
        ├── ThemeValidator
        └── PaletteValidator
        │
        ▼
Renderer
        ├── MatplotlibRenderer (P0)
        └── AltairRenderer (P1)
        │
        ▼
ExportManager (PDF/SVG/PNG/TIFF)
        │
        ▼
FigureLint (ERROR/WARNING/INFO)
        │
        ▼
ProvenanceWriter (SHA256 + metadata)
        │
        ▼
exports/
        ├── {figure_id}.pdf
        ├── {figure_id}.svg
        ├── {figure_id}.png
        ├── {figure_id}.tiff
        ├── {figure_id}.spec.resolved.yaml
        ├── {figure_id}.provenance.json
        └── {figure_id}.lint.json
```

---

## 3. 仓库结构

```text
abi_layer/
  skills/
    abi_sciplot/
      SKILL.md
      pyproject.toml
      README.md

      abi_sciplot/
        __init__.py

        cli.py
        api.py

        schema/
          __init__.py
          figure_spec.py      # FigureSpec, DataSpec, MappingSpec
          theme_spec.py       # ThemeSpec, FontSpec, AxesSpec
          palette_spec.py     # PaletteSpec, PaletteRegistry
          stat_spec.py        # StatSpec, SignificanceRule
          export_spec.py      # ExportSpec
          provenance_spec.py  # ProvenanceSpec

        validators/
          __init__.py
          figure_spec_validator.py  # Top-level orchestration
          data_validator.py         # Pandera DataFrameSchema
          stat_validator.py         # Statistical annotation checks
          theme_validator.py        # Theme applicability
          palette_validator.py      # Color safety

        renderers/
          __init__.py
          base.py                   # BaseRenderer ABC
          matplotlib_renderer.py    # MatplotlibRenderer
          plots/
            __init__.py
            boxplot_with_points.py
            violin_with_box.py
            scatterplot.py
            ordination_plot.py
            stacked_barplot.py
            heatmap.py
            volcano_plot.py
            lineplot.py

        themes/
          abi_nature.yaml
          abi_cell.yaml
          abi_report.yaml

        palettes/
          colorblind_safe.yaml
          scientific.yaml
          taxonomy.yaml

        lint/
          __init__.py
          figure_lint.py
          rules.py
          report.py

        provenance/
          __init__.py
          writer.py
          hashing.py

        examples/
          alpha_diversity_boxplot/
          volcano_plot/
          taxonomy_stacked_barplot/

        tests/
          test_schema.py
          test_data_validation.py
          test_render_boxplot.py
          test_render_volcano.py
          test_figure_lint.py
          test_cli.py

      docs/
        figure_spec.md
        theme_spec.md
        renderer_contract.md
        figure_lint_rules.md
```

---

## 4. 模块职责划分

| 模块 | 职责 | 输入 | 输出 | 必须程度 |
|------|------|------|------|----------|
| **FigureSpec** | 描述图形语义 | YAML / JSON | Pydantic model | P0 |
| **ThemeSpec** | 控制字体、尺寸、线宽、DPI | YAML | theme object | P0 |
| **PaletteRegistry** | 管理安全调色板 | palette name | color list / colormap | P0 |
| **DataValidator** | 检查数据列、类型、缺失值 | table + mapping | validation report | P0 |
| **StatValidator** | 检查统计检验和显著性标注 | stat spec | validation report | P0 |
| **Renderer** | 将 FigureSpec 渲染成图 | validated spec | matplotlib figure | P0 |
| **ExportManager** | 统一导出多格式 | figure + spec | PDF/SVG/PNG/TIFF | P0 |
| **FigureLint** | 检查投稿级规范 | exported figure + metadata | lint report | P0 |
| **ProvenanceWriter** | 记录复现信息 | spec + runtime metadata | provenance.json | P0 |

---

## 5. `FigureSpec` 协议 (v0.1.0)

### 5.1 Python Pydantic 模型

```python
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field


class DataSpec(BaseModel):
    table: Path
    format: Literal["csv", "tsv", "parquet"] = "tsv"
    required_columns: list[str] = Field(default_factory=list)


class MappingSpec(BaseModel):
    x: Optional[str] = None
    y: Optional[str] = None
    hue: Optional[str] = None
    label: Optional[str] = None
    group: Optional[str] = None
    value: Optional[str] = None


class SignificanceRule(BaseModel):
    padj_lt: Optional[float] = None
    pvalue_lt: Optional[float] = None
    abs_log2fc_gt: Optional[float] = None


class StatSpec(BaseModel):
    test: Optional[str] = None
    correction: Optional[str] = None
    pvalue_column: Optional[str] = None
    fold_change_column: Optional[str] = None
    significance_rule: Optional[SignificanceRule] = None


class StyleSpec(BaseModel):
    theme: str = "abi_nature"
    palette: str = "colorblind_safe"
    width_mm: float = 90
    height_mm: float = 70
    dpi: int = 300


class LabelSpec(BaseModel):
    title: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    legend_title: Optional[str] = None


class ExportSpec(BaseModel):
    output_dir: Path
    basename: str
    formats: list[Literal["pdf", "svg", "png", "tiff"]] = ["pdf", "svg", "png"]
    transparent: bool = False


class ProvenanceSpec(BaseModel):
    workflow_name: Optional[str] = None
    abi_version: Optional[str] = None
    input_data_role: Optional[str] = None


class FigureSpec(BaseModel):
    schema_version: str = "0.1.0"
    figure_id: str
    figure_type: Literal[
        "boxplot_with_points",
        "violin_with_box",
        "scatterplot",
        "ordination_plot",
        "stacked_barplot",
        "heatmap",
        "volcano_plot",
        "lineplot",
    ]
    data: DataSpec
    mapping: MappingSpec
    statistics: Optional[StatSpec] = None
    style: StyleSpec = Field(default_factory=StyleSpec)
    labels: LabelSpec = Field(default_factory=LabelSpec)
    export: ExportSpec
    provenance: ProvenanceSpec = Field(default_factory=ProvenanceSpec)
```

### 5.2 YAML 示例 (volcano_plot)

```yaml
schema_version: "0.1.0"
figure_id: "rnaseq_volcano_plot"
figure_type: "volcano_plot"

data:
  table: "deseq2_results.tsv"
  format: "tsv"
  required_columns:
    - "gene_id"
    - "log2FoldChange"
    - "padj"

mapping:
  x: "log2FoldChange"
  y: "padj"
  label: "gene_id"

statistics:
  test: "DESeq2 Wald test"
  correction: "Benjamini-Hochberg"
  pvalue_column: "padj"
  fold_change_column: "log2FoldChange"
  significance_rule:
    padj_lt: 0.05
    abs_log2fc_gt: 1.0

style:
  theme: "abi_nature"
  palette: "colorblind_safe"
  width_mm: 90
  height_mm: 75
  dpi: 300

labels:
  x_label: "log2 fold change"
  y_label: "-log10 adjusted p-value"
  legend_title: "Significance"

export:
  output_dir: "results/figures/rnaseq_volcano_plot"
  basename: "rnaseq_volcano_plot"
  formats:
    - "pdf"
    - "svg"
    - "png"
    - "tiff"
  transparent: false

provenance:
  workflow_name: "rnaseq_expression"
  abi_version: "0.2.0"
  input_data_role: "DESeq2 differential expression result"
```

### 5.3 FigureSpec 必须迁移路径

现有 ABI `FigureSpec` (dataclass) → 新 `abi_sciplot` FigureSpec (Pydantic):

| 现有字段 | 新字段 | 变化 |
|---------|--------|------|
| `id` | `figure_id` | 名 |
| `type` | `figure_type` | 改名 + 更丰富类型 |
| `source_table` | `data.table` | 嵌套到 data |
| `x` | `mapping.x` | 嵌套到 mapping |
| `y` | `mapping.y` | 嵌套到 mapping |
| `label` | `mapping.label` | 嵌套 |
| `color` | `mapping.hue` | 改名 |
| `group` | `mapping.group` | 嵌套 |
| `figsize` | `style.width_mm` / `style.height_mm` | 英寸→毫米 |
| `dpi` | `style.dpi` | 提高默认到 300 |
| `required` | (FigureLint 处理) | 移到质检层 |
| `colormap` | `style.palette` | 通过 palette 注册表 |
| `top_n` | (渲染器参数) | 保留在渲染器 |
| `sort_by` | (渲染器参数) | 保留在渲染器 |

---

## 6. `ThemeSpec` 设计

### 6.1 主题定义 (`abi_nature.yaml`)

```yaml
theme_name: "abi_nature"

figure:
  width_single_column_mm: 90
  width_double_column_mm: 180
  default_width_mm: 90
  default_height_mm: 70
  dpi: 300

font:
  family: "Arial"
  fallback:
    - "Helvetica"
    - "DejaVu Sans"
  base_size_pt: 7
  title_size_pt: 8
  label_size_pt: 7
  tick_size_pt: 6
  legend_size_pt: 6

axes:
  linewidth_pt: 0.6
  show_top_spine: false
  show_right_spine: false
  grid: false

lines:
  linewidth_pt: 0.8
  marker_size_pt: 3

legend:
  frame: false
  location: "best"

export:
  raster_dpi: 300
  vector_formats:
    - "pdf"
    - "svg"
  raster_formats:
    - "png"
    - "tiff"
```

### 6.2 三大主题

| 主题 | 用途 | 风格 |
|------|------|------|
| **abi_nature** | 论文投稿图 | 克制、紧凑、适合单栏/双栏 |
| **abi_cell** | 多 panel 机制图和组图 | 字号略大、panel label 清晰 |
| **abi_report** | HTML / PDF 自动报告 | 更强调可读性，不追求极限紧凑 |

### 6.3 技术实现

主题加载器将 YAML 转换为 Matplotlib `rcParams` 字典：

```python
def theme_to_rcparams(theme: ThemeSpec) -> dict:
    """Convert a ThemeSpec to matplotlib rcParams."""
    return {
        "font.family": theme.font.family,
        "font.size": theme.font.base_size_pt,
        "axes.titlesize": theme.font.title_size_pt,
        "axes.labelsize": theme.font.label_size_pt,
        "xtick.labelsize": theme.font.tick_size_pt,
        "ytick.labelsize": theme.font.tick_size_pt,
        "legend.fontsize": theme.font.legend_size_pt,
        "axes.linewidth": theme.axes.linewidth_pt,
        "axes.spines.top": theme.axes.show_top_spine,
        "axes.spines.right": theme.axes.show_right_spine,
        "axes.grid": theme.axes.grid,
        "lines.linewidth": theme.lines.linewidth_pt,
        "lines.markersize": theme.lines.marker_size_pt,
        "legend.frameon": theme.legend.frame,
        "figure.dpi": theme.figure.dpi,
        "savefig.dpi": theme.export.raster_dpi,
    }
```

**依据**: Matplotlib 可通过 `rcParams` 和 style sheets 统一控制图形样式，适合做固定科研绘图主题。

---

## 7. `PaletteRegistry` 设计

### 7.1 调色板白名单

```yaml
qualitative:
  colorblind_safe_8:
    type: "categorical"
    max_categories: 8
    colors:
      - "#0072B2"  # blue
      - "#E69F00"  # orange
      - "#009E73"  # bluish green
      - "#CC79A7"  # reddish purple
      - "#56B4E9"  # sky blue
      - "#D55E00"  # vermillion
      - "#F0E442"  # yellow
      - "#000000"  # black

sequential:
  viridis:
    type: "continuous"
    source: "matplotlib"

  batlow:
    type: "continuous"
    source: "scientific_colour_maps"

diverging:
  vik:
    type: "diverging"
    source: "scientific_colour_maps"
```

### 7.2 颜色规则

| 场景 | 默认策略 |
|------|---------|
| **分类变量 ≤ 8 类** | `colorblind_safe_8` |
| **分类变量 9–20 类** | 警告，允许扩展 palette |
| **分类变量 > 20 类** | ERROR，要求合并低丰度类别 |
| **连续变量** | `viridis` 或 Scientific Colour Maps |
| **发散变量** | diverging palette，必须指定中心值 |
| **taxonomy barplot** | top N + Others，不允许 50 类硬画 |

**依据**: Fabio Crameri 的 Scientific Colour Maps 强调感知均匀、色觉缺陷友好和黑白打印可读性，适合作连续变量和发散变量配色的来源。

---

## 8. `DataValidator` 设计

### 8.1 验证步骤

```text
1. 文件存在检查 — data.table 必须存在
2. 格式检测 — TSV/CSV/Parquet
3. 列存在检查 — required_columns + mapping 引用的所有列
4. 类型检查 — 数值列是否确实为数值
5. 缺失值检查 — NaN/NA 比例 (≤20% 警告, >50% 报错)
6. 分类数量检查 — categorical column 类别数 vs palette 上限
```

### 8.2 技术选择

使用 **Pandera** `DataFrameSchema` 做表格级验证，因为 Pandera 支持对 DataFrame 的列、索引和字段约束进行 schema 检查。

```python
import pandera as pa

def build_schema(spec: FigureSpec) -> pa.DataFrameSchema:
    """Build a Pandera schema from a FigureSpec."""
    columns = {}
    mapping_cols = [spec.mapping.x, spec.mapping.y, spec.mapping.hue,
                    spec.mapping.label, spec.mapping.group, spec.mapping.value]
    for col in spec.data.required_columns:
        columns[col] = pa.Column(str, nullable=True)
    for col in mapping_cols:
        if col and col not in columns:
            columns[col] = pa.Column(str, nullable=True)
    return pa.DataFrameSchema(columns, coerce=True)
```

### 8.3 验证输出

```json
{
  "status": "error",
  "errors": [
    {
      "rule": "DATA002",
      "message": "Mapping column 'missing_column' does not exist in input table.",
      "column": "missing_column",
      "available_columns": ["gene_id", "log2FoldChange", "padj", "baseMean"]
    }
  ]
}
```

---

## 9. `StatValidator` 设计

### 9.1 规则

| 规则 ID | 检查内容 | 等级 |
|---------|---------|------|
| STAT001 | 有显著性星号必须有统计检验声明 | ERROR |
| STAT002 | 多组比较必须声明多重检验校正 | ERROR |
| STAT003 | pvalue_column 必须在 data.required_columns 或 mapping 中 | ERROR |
| STAT004 | significance_rule 的阈值必须在合理范围 (padj 0–1) | WARNING |

### 9.2 核心逻辑

```python
def validate_statistics(spec: FigureSpec, has_significance_markers: bool) -> list[LintFinding]:
    findings = []
    if has_significance_markers and not spec.statistics:
        findings.append(LintFinding(
            rule="STAT001",
            level="ERROR",
            message="Significance markers present but no statistical test declared."
        ))
    if spec.statistics and spec.statistics.test:
        n_groups = _count_groups(spec)
        if n_groups > 2 and not spec.statistics.correction:
            findings.append(LintFinding(
                rule="STAT002",
                level="ERROR",
                message=f"Multiple groups ({n_groups}) compared without multiple-testing correction."
            ))
    return findings
```

---

## 10. 渲染器设计

### 10.1 BaseRenderer 接口

```python
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass


@dataclass
class RenderResult:
    figure_id: str
    output_files: list[Path]
    lint_report_path: Path
    provenance_path: Path


class BaseRenderer(ABC):
    @abstractmethod
    def supports(self, figure_type: str) -> bool: ...

    @abstractmethod
    def render(self, spec: FigureSpec) -> RenderResult: ...
```

### 10.2 MatplotlibRenderer

```python
class MatplotlibRenderer(BaseRenderer):
    SUPPORTED_TYPES = frozenset({
        "boxplot_with_points",
        "violin_with_box",
        "scatterplot",
        "ordination_plot",
        "stacked_barplot",
        "heatmap",
        "volcano_plot",
        "lineplot",
    })

    def __init__(self, theme: ThemeSpec, palette_registry: PaletteRegistry):
        self._theme = theme
        self._palette_registry = palette_registry

    def supports(self, figure_type: str) -> bool:
        return figure_type in self.SUPPORTED_TYPES

    def render(self, spec: FigureSpec) -> RenderResult:
        # 1. Apply theme via rcParams
        # 2. Load data via DataValidator
        # 3. Dispatch to plot function
        # 4. ExportManager saves files
        # 5. ProvenanceWriter records metadata
        # 6. FigureLint checks result
        # 7. Return RenderResult
        ...
```

### 10.3 Plot function 统一接口

每个 plot function 的签名：

```python
def plot_volcano(
    spec: FigureSpec,
    data: pd.DataFrame,
    theme: ThemeSpec,
    palette: PaletteRegistry,
) -> plt.Figure:
    """Return a matplotlib Figure. Do NOT save files here."""
    ...
```

**规则**:
1. plot function 只负责画图
2. 不负责读文件
3. 不负责保存文件
4. 不负责写 provenance
5. 不负责 lint

### 10.4 P0 图形类型实现顺序

| 顺序 | 图形类型 | 输出目标 |
|------|---------|---------|
| 1 | **boxplot_with_points** | 分组箱线图 + 散点覆盖 |
| 2 | **scatterplot** | 普通散点图 |
| 3 | **ordination_plot** | PCA / PCoA / NMDS |
| 4 | **stacked_barplot** | 分类组成堆叠图 |
| 5 | **heatmap** | 矩阵热图 |
| 6 | **volcano_plot** | 火山图 |
| 7 | **violin_with_box** | 小提琴图 + 内嵌箱线 |

### 10.5 与现有 FigureEngine 的关系

`abi_sciplot` 不是替换 `FigureEngine`，而是提供更严格的上层。迁移路径：

```text
Phase 4a: abi_sciplot 独立运行 (新代码，不影响现有系统)
Phase 4b: ABI report 系统调用 abi_sciplot API (替代直接调用 FigureEngine)
Phase 4c: FigureEngine 标记 deprecated，全部迁移到 abi_sciplot
```

---

## 11. `ExportManager` 设计

### 11.1 导出格式

| 格式 | 类型 | 用途 | 默认 DPI |
|------|------|------|---------|
| PDF | 矢量 | 期刊投稿 (图文混排) | — |
| SVG | 矢量 | Web 展示、Illustrator 编辑 | — |
| PNG | 栅格 | 预览、快速查看 | 300 |
| TIFF | 栅格 | 期刊投稿 (照片类) | 300 |

### 11.2 导出命名规则

```text
{export.output_dir}/
  {export.basename}.pdf
  {export.basename}.svg
  {export.basename}.png
  {export.basename}.tiff
  {export.basename}.spec.resolved.yaml
  {export.basename}.provenance.json
  {export.basename}.lint.json
```

### 11.3 实现

```python
class ExportManager:
    def __init__(self, spec: FigureSpec):
        self._spec = spec

    def export(self, fig: plt.Figure) -> list[Path]:
        output_paths = []
        outdir = self._spec.export.output_dir
        outdir.mkdir(parents=True, exist_ok=True)
        basename = self._spec.export.basename

        for fmt in self._spec.export.formats:
            path = outdir / f"{basename}.{fmt}"
            if fmt in ("pdf", "svg"):
                fig.savefig(path, format=fmt, bbox_inches="tight",
                           transparent=self._spec.export.transparent)
            else:
                fig.savefig(path, format=fmt, dpi=self._spec.style.dpi,
                           bbox_inches="tight",
                           transparent=self._spec.export.transparent)
            output_paths.append(path)
        return output_paths
```

**依据**: Matplotlib `savefig` 支持保存当前图为图像或矢量图，文件格式可包括 PNG、PDF、SVG 等。

---

## 12. `FigureLint` 设计

### 12.1 Lint 等级

| 等级 | 含义 | 是否阻断 |
|------|------|---------|
| **ERROR** | 图形可能误导、不可复现或不符合硬规范 | **阻断** |
| **WARNING** | 图形可用但不够理想 | 不阻断 |
| **INFO** | 建议优化项 | 不阻断 |

### 12.2 第一版规则表

| 规则 ID | 检查内容 | 等级 |
|---------|---------|------|
| **FIG001** | 必须有 `figure_id` | ERROR |
| **FIG002** | 必须有 `figure_type` | ERROR |
| **FIG003** | 图形类型必须在白名单中 | ERROR |
| **DATA001** | 输入表必须存在 | ERROR |
| **DATA002** | mapping 中引用的列必须存在 | ERROR |
| **DATA003** | x/y 映射列不能全为空 | ERROR |
| **DATA004** | 数值列不能全为 NA | ERROR |
| **STAT001** | 显著性星号必须有统计检验 | ERROR |
| **STAT002** | 多组比较必须声明多重检验校正 | ERROR |
| **STYLE001** | 不允许使用 `rainbow` / `jet` | ERROR |
| **STYLE002** | 分类变量超过 palette 上限 | WARNING/ERROR |
| **STYLE003** | 字号小于 5 pt | ERROR |
| **EXPORT001** | PNG/TIFF 低于 300 dpi | ERROR |
| **EXPORT002** | 没有 PDF 或 SVG 矢量格式 | WARNING |
| **LABEL001** | x/y 轴标签缺失 | WARNING |
| **LABEL002** | 图例缺失 (多组时) | WARNING |
| **PROV001** | 缺少 provenance.json | ERROR |
| **PROV002** | 缺少输入数据 hash | ERROR |

### 12.3 Lint 输出

```json
{
  "figure_id": "rnaseq_volcano_plot",
  "status": "passed",
  "errors": [],
  "warnings": [
    {
      "rule": "LABEL001",
      "message": "Figure title is empty."
    }
  ],
  "info": [
    {
      "rule": "EXPORT001",
      "message": "Raster export uses 300 dpi."
    }
  ]
}
```

---

## 13. `ProvenanceWriter` 设计

### 13.1 记录内容

1. 输入数据路径 + SHA256
2. FigureSpec 完整内容 (resolved)
3. ABI 版本
4. Python 版本
5. Matplotlib / Seaborn / Pandas 版本
6. Renderer 名称
7. Theme 名称
8. Palette 名称
9. 统计检验信息
10. 时间戳

### 13.2 `provenance.json` 示例

```json
{
  "figure_id": "rnaseq_volcano_plot",
  "created_at": "2026-06-19T00:00:00Z",
  "abi_version": "0.2.0",
  "skill": "abi_sciplot",
  "skill_version": "0.1.0",
  "renderer": "matplotlib",
  "renderer_version": "3.10.9",
  "python_version": "3.10.13",
  "input_table": "deseq2_results.tsv",
  "input_sha256": "a1b2c3d4e5f6...",
  "theme": "abi_nature",
  "palette": "colorblind_safe",
  "statistical_test": "DESeq2 Wald test",
  "multiple_testing_correction": "Benjamini-Hochberg",
  "packages": {
    "matplotlib": "3.10.9",
    "pandas": "2.1.4",
    "numpy": "1.26.2",
    "seaborn": "0.13.0"
  }
}
```

---

## 14. CLI 设计

### 14.1 命令一：验证 spec

```bash
abi-sciplot validate --spec figure.yaml
```

```json
{
  "status": "ok",
  "figure_id": "rnaseq_volcano_plot",
  "errors": [],
  "warnings": []
}
```

### 14.2 命令二：渲染图形

```bash
abi-sciplot render --spec figure.yaml
```

```json
{
  "status": "ok",
  "figure_id": "rnaseq_volcano_plot",
  "outputs": [
    "results/figures/rnaseq_volcano_plot/rnaseq_volcano_plot.pdf",
    "results/figures/rnaseq_volcano_plot/rnaseq_volcano_plot.svg",
    "results/figures/rnaseq_volcano_plot/rnaseq_volcano_plot.png",
    "results/figures/rnaseq_volcano_plot/rnaseq_volcano_plot.tiff"
  ],
  "provenance": "results/figures/rnaseq_volcano_plot/rnaseq_volcano_plot.provenance.json",
  "lint": "results/figures/rnaseq_volcano_plot/rnaseq_volcano_plot.lint.json"
}
```

### 14.3 命令三：单独质检

```bash
abi-sciplot lint --spec figure.yaml --figure figure.png
```

### 14.4 命令四：列出支持图形

```bash
abi-sciplot list-plot-types
```

---

## 15. Python API

```python
from abi_sciplot import (
    load_spec,
    validate_spec,
    render_figure,
    lint_figure,
)

# Load and validate
spec = load_spec("figure.yaml")
errors = validate_spec(spec)

# Render
result = render_figure(spec)
print(result.output_files)    # [Path(".../volcano.pdf"), ...]
print(result.lint_report)     # Path(".../lint.json")
print(result.provenance_file) # Path(".../provenance.json")

# Lint post-hoc
lint_result = lint_figure(spec, "figure.png")
if lint_result.errors:
    raise RuntimeError(f"Figure failed lint: {lint_result.errors}")
```

---

## 16. ABI Tool Contract 集成

```json
{
  "tool_name": "abi_sciplot.render",
  "description": "Render a publication-grade scientific figure from a validated FigureSpec.",
  "input_schema": {
    "type": "object",
    "properties": {
      "spec_path": {"type": "string", "description": "Path to FigureSpec YAML or JSON"},
      "output_dir": {"type": "string", "description": "Override output directory"},
      "strict": {"type": "boolean", "description": "Fail on lint WARNING in addition to ERROR"}
    },
    "required": ["spec_path"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "status": {"type": "string", "enum": ["ok", "error"]},
      "figure_id": {"type": "string"},
      "output_files": {"type": "array", "items": {"type": "string"}},
      "lint_report": {"type": "string"},
      "provenance_file": {"type": "string"},
      "errors": {"type": "array", "items": {"type": "string"}},
      "warnings": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

---

## 17. 各 ABI 插件图形模板

### 17.1 `amplicon_16s`

| 分析步骤 | 图形类型 | 模板文件 |
|---------|---------|---------|
| alpha diversity | boxplot_with_points | `alpha_diversity_boxplot.yaml` |
| beta diversity | ordination_plot | `pcoa_plot.yaml` |
| taxonomy composition | stacked_barplot | `taxonomy_barplot.yaml` |
| differential abundance | volcano_plot | `differential_abundance.yaml` |
| sample distance | heatmap | `distance_heatmap.yaml` |

### 17.2 `rnaseq_expression`

| 分析步骤 | 图形类型 | 模板文件 |
|---------|---------|---------|
| sample PCA | ordination_plot | `rnaseq_pca.yaml` |
| differential expression | volcano_plot | `rnaseq_volcano.yaml` |
| expression matrix | heatmap | `expression_heatmap.yaml` |
| gene expression by group | boxplot_with_points | `gene_boxplot.yaml` |
| MA plot | scatterplot | `ma_plot.yaml` |

### 17.3 `wgs_bacteria`

| 分析步骤 | 图形类型 | 模板文件 |
|---------|---------|---------|
| assembly QC | scatterplot | `assembly_qc.yaml` |
| coverage-GC profile | scatterplot | `coverage_gc_scatter.yaml` |
| AMR profile | stacked_barplot / heatmap | `amr_profile.yaml` |
| SNP distance matrix | heatmap | `snp_distance_heatmap.yaml` |

### 17.4 `metagenomic_plasmid`

| 分析步骤 | 图形类型 | 模板文件 |
|---------|---------|---------|
| contig length distribution | boxplot_with_points | `contig_length_distribution.yaml` |
| coverage-GC | scatterplot | `plasmid_coverage_gc.yaml` |
| plasmid quality summary | bar | `plasmid_quality_summary.yaml` |
| mobility / replicon profile | stacked_barplot | `plasmid_feature_profile.yaml` |

---

## 18. 测试体系

### 18.1 测试类型

| 测试 | 工具 | 目的 | 必须程度 |
|------|------|------|----------|
| **schema test** | pytest | FigureSpec 是否能解析 valid/invalid YAML | P0 |
| **data validation test** | pytest + Pandera | 数据列和类型是否正确 | P0 |
| **renderer unit test** | pytest | 每种图能否生成 matplotlib Figure | P0 |
| **export test** | pytest | 是否生成 PDF/SVG/PNG/TIFF | P0 |
| **lint test** | pytest | 不合格图是否被拦截 | P0 |
| **image regression test** | pytest-mpl | 图形样式是否意外变化 | P1 |
| **CLI test** | pytest | 命令行是否稳定 | P0 |

### 18.2 测试策略

每个图形类型的测试必须覆盖：

1. **Happy path** — 有效 spec + 有效数据 → 图形生成
2. **Missing data** — 输入表不存在 → DATA001 ERROR
3. **Missing column** — mapping 引用不存在的列 → DATA002 ERROR
4. **Bad palette** — 使用 jet/rainbow → STYLE001 ERROR
5. **No statistics** — 有显著性标记无 stat spec → STAT001 ERROR

---

## 19. CI/CD 门禁

### 19.1 Pull Request 检查

```bash
ruff check abi_sciplot/
mypy abi_sciplot/
pytest abi_sciplot/tests/ -v
pytest --mpl abi_sciplot/tests/
abi-sciplot validate --spec examples/volcano_plot/figure.yaml
abi-sciplot render --spec examples/volcano_plot/figure.yaml
abi-sciplot lint --spec examples/volcano_plot/figure.yaml
```

### 19.2 CI 失败条件

| 条件 | 是否失败 |
|------|----------|
| 代码格式错误 | 是 |
| 类型检查失败 | 是 |
| schema 测试失败 | 是 |
| 任一 P0 图形无法渲染 | 是 |
| 使用禁用 palette | 是 |
| 显著性标注缺失统计信息 | 是 |
| 无 provenance | 是 |
| 无 PDF/SVG 输出 | 是 |
| PNG/TIFF DPI 不达标 | 是 |

---

## 20. Agent 使用协议

### 20.1 Agent 输入 (接收自 workflow)

```json
{
  "task": "generate_publication_figure",
  "workflow": "rnaseq_expression",
  "plot_goal": "volcano plot for differential expression result",
  "input_table": "results/deseq2/deseq2_results.tsv",
  "columns": ["gene_id", "baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj"]
}
```

### 20.2 Agent 输出 (FigureSpec YAML)

Agent 只能输出 FigureSpec，不能输出 Matplotlib/Seaborn 代码。这是硬约束。

---

## 21. 开发阶段

| Phase | 内容 | 预计时间 | 可本地验证 |
|-------|------|---------|-----------|
| **Phase 0** | 包骨架 + CLI + pyproject.toml | 0.5 天 | ✅ |
| **Phase 1** | FigureSpec Pydantic + 验证器 | 1 天 | ✅ |
| **Phase 2** | DataValidator (Pandera) | 0.5 天 | ✅ |
| **Phase 3** | Theme + Palette 系统 | 0.5 天 | ✅ |
| **Phase 4** | MatplotlibRenderer + P0 plots | 2 天 | ✅ |
| **Phase 5** | ExportManager (4 格式) | 0.5 天 | ✅ |
| **Phase 6** | FigureLint (17 规则) | 1 天 | ✅ |
| **Phase 7** | ProvenanceWriter | 0.5 天 | ✅ |
| **Phase 8** | 测试 + CI + Examples | 1 天 | ✅ |
| **Phase 9** | 接入 ABI plugin workflow | 1 天 | ✅ |
| **Total** | | **8 天** | 全部 ✅ |

---

## 22. 最小可发布版本 (v0.1.0)

### 22.1 必须包含

| 能力 | 是否必须 |
|------|----------|
| FigureSpec schema (Pydantic) | 是 |
| ThemeSpec (3 主题) | 是 |
| PaletteRegistry (白名单) | 是 |
| DataValidator (Pandera) | 是 |
| MatplotlibRenderer | 是 |
| boxplot_with_points | 是 |
| scatterplot | 是 |
| stacked_barplot | 是 |
| heatmap | 是 |
| volcano_plot | 是 |
| violin_with_box | 是 |
| ordination_plot | 是 |
| PDF/SVG/PNG/TIFF 导出 | 是 |
| FigureLint (17 规则) | 是 |
| ProvenanceWriter | 是 |
| CLI (4 命令) | 是 |
| pytest 测试 (>80% 覆盖) | 是 |
| 示例 FigureSpec (≥3) | 是 |

### 22.2 Definition of Done

1. **所有 P0 图形类型可从 FigureSpec 渲染。**
2. **所有图形至少输出 PDF、SVG、PNG。**
3. **PNG/TIFF 默认 300 dpi。**
4. **所有图形输出 provenance.json。**
5. **所有图形输出 lint.json。**
6. **无统计信息时不能显示显著性星号。**
7. **禁用 rainbow / jet。**
8. **缺失输入列时直接失败。**
9. **CI 全部通过。**
10. **每个图形类型都有一个可运行 example。**

---

## 23. 后续迭代 (P1/P2)

| 功能 | 优先级 | 预计版本 |
|------|--------|---------|
| AltairRenderer (交互式) | P1 | v0.2.0 |
| pytest-mpl 图像回归 | P1 | v0.2.0 |
| NetworkRenderer (网络图) | P2 | v0.3.0 |
| CircosRenderer (环形图) | P2 | v0.3.0 |
| 自动 figure panel 排版 | P2 | v0.4.0 |

---

## 24. 核心判断

**先做"规范化静态科研图"，再做"复杂交互图"。**

ABI 当前最需要的不是花哨的可视化，而是：

1. **自动报告稳定** — 每个插件生成的图风格一致
2. **图形风格一致** — 同一主题、同一配色体系
3. **结果可复现** — provenance 记录所有参数
4. **论文叙事可信** — 统计标注必须有检验支撑
5. **不同插件共用同一套图形标准** — 而非每个插件手写 matplotlib

`abi_sciplot` 的核心不是 Matplotlib，也不是 Seaborn，而是这套协议：

```text
FigureSpec → Validate → Render → Export → Lint → Provenance
```

---

## 参考资料

1. [matplotlib.pyplot.savefig — Matplotlib documentation](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html)
2. [Customizing Matplotlib with style sheets and rcParams](https://matplotlib.org/stable/users/explain/customizing.html)
3. [Nature — Final submission guidelines](https://www.nature.com/nature/for-authors/final-submission)
4. [JSON Schema — Pydantic Docs](https://pydantic.dev/docs/validation/latest/concepts/json_schema/)
5. [DataFrame Schemas — Pandera documentation](https://pandera.readthedocs.io/en/latest/dataframe_schemas.html)
6. [pytest-mpl documentation](https://pytest-mpl.readthedocs.io/)
7. [Scientific colour maps — Fabio Crameri](https://www.fabiocrameri.ch/colourmaps/)
8. [Vega-Altair: Declarative Visualization in Python](https://altair-viz.github.io/)
