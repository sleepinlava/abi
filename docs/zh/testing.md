# ABI 测试指南

> **当前状态 (2026-07-06)**: 1364 测试通过, 11 跳过, 3 预存失败, 83% 语句覆盖率, 0 ruff 错误, 0 mypy 错误。

本指南涵盖 ABI 测试基础设施：测试分类、共享 fixtures、基准框架、合约验证、黄金轨迹、冒烟测试、CI/CD 以及插件作者的测试规范。

## 测试分类

ABI 测试按作用域和速度分为四个层级：

| 层级 | 目录 | 用途 | 速度 | 需要工具？ |
|------|------|------|------|-----------|
| **单元测试** | `tests/unit/` | 核心模块的隔离逻辑测试 | < 1秒/个 | 否 |
| **集成测试** | `tests/integration/` | 跨组件测试 (CLI, dry-run, golden traces) | 1-10秒/个 | 否 |
| **冒烟测试** | `tests/smoke/` | 使用合成数据的真实工具执行 | 30秒-5分钟/个 | 是 |
| **基准测试** | `tests/smoke/test_*_benchmark.py` | 对照预期输出的数值级验证 | 30秒-5分钟/个 | 是 |

### 各层级使用场景

- **单元测试**: 用于解析器函数、schema 验证、DAG 逻辑、合约评估。新增解析逻辑或 schema 变更时必须添加。
- **集成测试**: 用于 CLI 参数处理、dry-run 产出验证、跨插件一致性检查。
- **冒烟测试**: 新增工具合约并需要验证真实执行时使用。用 `@pytest.mark.smoke` 标记。
- **基准测试**: 用于已知数据集的端到端管线验证。使用 `abi.testing` 中的 `run_benchmark()`。

## 运行测试

```bash
# 全部测试
pytest tests/ -v --tb=short

# 仅快速测试（跳过真实工具测试）
pytest tests/ -v -m "not requires_tools"

# 仅冒烟测试
pytest tests/ -v -m smoke

# 单个测试文件
pytest tests/unit/test_dag_planner.py -v

# 单个测试函数
pytest tests/unit/test_dag_planner.py::test_build_plan_per_sample -v

# 带覆盖率
pytest tests/ --cov=src/abi --cov-report=term --cov-fail-under=75
```

## 共享 Fixtures

所有 fixtures 定义在 `tests/conftest.py` 中，每个测试文件无需显式导入即可使用。

### `mock_sample`

适用于插件测试的最小有效 `ABISample`：

```python
def test_my_parser(mock_sample):
    assert mock_sample.sample_id == "S1"
    assert mock_sample.platform == "illumina"
    assert mock_sample.group == "treatment"
```

### `mock_sample_context`

由 `mock_sample` 构建的单样本 `ABISampleContext`：

```python
def test_plan_builder(mock_sample_context):
    assert len(mock_sample_context.samples) == 1
    assert mock_sample_context.multi_sample is False
```

### `mock_contract_dict`

用于 lint/test 脚手架的最小有效工具合约字典：

```python
def test_contract_lint(mock_contract_dict):
    assert mock_contract_dict["tool_id"] == "fastp"
    assert mock_contract_dict["execution"]["env_name"] == "abi-qc"
```

### `tmp_project`

包含 `results/`、`logs/`、`provenance/` 和 `tables/` 子目录的临时目录：

```python
def test_output_writer(tmp_project):
    results_dir = tmp_project / "results"
    # 写入输出，验证正确落盘
```

### 添加新 fixtures

将共享 fixtures 添加到 `tests/conftest.py`。插件特定的 fixtures 应放在插件的测试文件或其 `conftest.py` 中。

命名规范：测试替身用 `mock_<thing>`，临时脚手架用 `tmp_<thing>`，需要真实数据的 fixtures 用 `real_<thing>`。

## 插件合约测试

每个插件必须通过 `assert_plugin_contract(plugin)`：

```python
from abi.testing import assert_plugin_contract
from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin


def test_plugin_contract():
    plugin = RNASeqExpressionPlugin()
    assert_plugin_contract(plugin)
```

`assert_plugin_contract` 验证：

1. 插件实现了 `ABIPlugin`（必需）— 检查全部 9 个强制方法/属性：
   `plugin_id`、`display_name`、`description`、`report_title`、`load_config`、
   `build_plan`、`registry`、`table_schemas`、`parse_outputs`、`write_report`

2. 如果插件实现了 `ABIDryRunPlugin`（可选）— 检查 `execute_dry_run`

3. 如果插件实现了 `ABIInitializablePlugin`（可选）— 检查 `root`

全部 5 个内置插件均有合约测试。运行方式：

```bash
pytest tests/ -k "contract" -v
```

## 基准测试框架

`abi.testing.benchmark` 提供统一的数值级管线验证框架。全部 5 个插件均有基于此框架的基准测试。

### `BenchmarkAssertion`

对管线输出的单个断言：

| 字段 | 类型 | 描述 |
|------|------|------|
| `step_id` | `str` | DAG 步骤名称 (如 `"fastp"`, `"star_align"`) |
| `table` | `str` | 相对于 result_dir 的输出表路径 |
| `column` | `str` | 要检查的列，或 `""` 用于文件级检查 |
| `condition` | `str` | 比较方式：`"exists"`、`">"`、`">="`、`"<="`、`"contains"`、`"between"` |
| `expected` | `Any` | 期望值。对于 `"between"`：`[min, max]` |
| `description` | `str` | 人类可读的描述 |

支持的 condition 类型：

| Condition | 含义 | expected 格式 |
|-----------|------|--------------|
| `exists` | 文件或列存在 | `true`/`false` 或列名 |
| `>` | 大于 | 数值 |
| `>=` | 大于等于 | 数值 |
| `<=` | 小于等于 | 数值 |
| `contains` | 字符串包含 | 字符串 |
| `between` | 范围检查 | `[min, max]` |

### `BenchmarkResult`

`run_benchmark()` 返回：

```python
@dataclass
class BenchmarkResult:
    plugin_id: str
    passed: int        # 通过的断言数
    failed: int        # 失败的断言数
    total: int         # 总断言数
    assertions: list[BenchmarkAssertion]
    failures: list[BenchmarkAssertion]
    errors: list[str]
```

### 编写基准测试

基准测试遵循以下模式：

```python
from pathlib import Path
import pytest
from abi.testing.benchmark import BenchmarkResult, run_benchmark


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_rnaseq_expression_benchmark(tmp_path):
    result = run_benchmark(
        plugin_id="rnaseq_expression",
        dataset_path=Path("data/benchmarks/rnaseq_expression"),
        outdir=tmp_path / "results",
    )

    assert result.total > 0, "未定义断言"
    assert result.passed >= result.total * 0.8, (
        f"基准测试失败: {result.passed}/{result.total} 通过\n"
        + "\n".join(f"  - {f.description}" for f in result.failures)
    )
```

### 基准测试配置

每个基准测试数据集位于 `data/benchmarks/<plugin_id>/` 中：

```
data/benchmarks/rnaseq_expression/
  expected_assertions.yaml    # BenchmarkAssertion 字典列表
  config.yaml                 # 运行所需的插件配置
  samples.tsv                 # 包含基准数据路径的样本表
```

## 黄金轨迹 (Golden Traces)

黄金轨迹是预先录制的执行计划，捕获已知输入的预期 DAG 输出。它们支持 DAG 规划器的确定性回归测试。

黄金轨迹位于 `tests/fixtures/golden_traces/`，通过集成测试重放：

```bash
pytest tests/integration/test_golden_traces.py -v
```

### 创建新的黄金轨迹

1. 对目标配置执行 dry-run：
   ```bash
   abi dry-run --type my_plugin --config my_config.yaml --outdir /tmp/golden
   ```

2. 复制执行计划到 `tests/fixtures/golden_traces/`：
   ```bash
   cp /tmp/golden/execution_plan.json tests/fixtures/golden_traces/my_plugin_golden.json
   ```

3. 在 `tests/integration/test_golden_traces.py` 中添加测试：
   ```python
   def test_my_plugin_golden_trace():
       expected = load_golden_trace("my_plugin_golden.json")
       actual = build_plan(...)
       assert_plans_match(expected, actual)
   ```

## 冒烟测试

冒烟测试使用合成数据执行真实的生物信息学工具，以验证工具合约、解析器和输出合约的端到端正确性。

### 冒烟测试规范

- 用 `@pytest.mark.smoke` 和 `@pytest.mark.requires_tools` 标记
- 在测试中生成合成输入数据（不提交 FASTQ 文件）
- 使用小数据量（500-1000 条 reads）以提高速度
- 验证关键输出产物的存在（文件、目录）
- 验证解析器输出具有预期的列和非平凡值
- 使用 `tmp_path` 清理（pytest 自动清理）

### 冒烟测试示例

```python
import pytest
from pathlib import Path
from abi.plugins.amplicon_16s import Amplicon16SPlugin


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_amplicon_smoke(tmp_path):
    plugin = Amplicon16SPlugin()
    # 生成合成 reads...
    # 运行管线...
    # 验证输出...
    assert (tmp_path / "tables" / "asv_table.tsv").exists()
```

在没有生物信息学工具的环境中跳过冒烟测试：

```bash
pytest tests/ -v -m "not requires_tools"
```

## CI/CD 管线

ABI 只保留四个 GitHub Actions workflow：CI、Docker、Release 和受信 PyPI publisher。

### `ci.yml` — 每次推送和 PR 时运行

| 步骤 | Python 版本 |
|------|------------|
| `ruff check` | 3.10, 3.11, 3.12, 3.13 |
| `ruff format --check` | 3.10, 3.11, 3.12, 3.13 |
| `mypy src/abi/` | 3.10, 3.11, 3.12, 3.13 |
| `pytest tests/` | 3.10, 3.11, 3.12, 3.13 |
| `pytest --cov --cov-fail-under=75` | 仅 3.12 |
| Sphinx 文档构建 | 仅 3.12 |
| Wheel 构建 + 冒烟测试 | 仅 3.12 |

3.12 构建使用默认的 `python -m build` 路径：源码树 → sdist → wheel。因此，wheel 中配置为 `force-include` 的文件也必须进入 sdist，尤其是根目录 `environments.yaml`。

### `docker.yml` — 在相关 PR 和 release tag 上构建插件镜像

- PR 构建加载单个 `linux/amd64` 镜像，标签为 `abi-<plugin>:latest`，随后在容器中运行 `abi list-types`。
- 本地 `load: true` 构建关闭 provenance 和 SBOM；registry push 才启用二者。attestation 产生的 manifest list 无法由本地 Docker exporter 加载。
- 构建输入包含 `docker/.condarc`、`environments.yaml`、生成的 `envs/*.yml`、插件、配置、脚本、数据、示例和 golden traces，不能被 `.dockerignore` 排除。
- PR 自动构建 amplicon、RNA-seq、WGS 和 metatranscriptomics；大型 plasmid 镜像仅手动构建。
- registry 推送默认多架构；RNA-seq 在 R/DESeq2 环境通过原生 arm64 构建和冒烟验证前仅发布 `linux/amd64`。
- packaging、环境、Dockerfile、ignore 文件或 Docker workflow 变更必须运行 `pytest tests/unit/test_docker_configuration.py -q`。

### `release.yml` — 为 `v*` 标签构建并创建 GitHub Release

### `release.yml` 与 `publish-pypi.yml` — Release 与发布

Release workflow 创建已验证的 GitHub Release；其 published event 以顶层 workflow 方式启动 `publish-pypi.yml`，下载并发布这些原始产物。PyPI Trusted Publishing 的 OIDC 策略绑定该文件名，且不支持 reusable-workflow caller 身份。

## 测试编写规范

### 文件命名

- 测试文件：`test_<feature>.py`
- 测试函数：`test_<behavior>`
- 示例：`tests/unit/test_dag_planner.py::test_build_plan_per_sample`

### 代码质量门禁

所有测试在提交前必须通过这些门禁：

```bash
ruff check src/ tests/        # 0 错误
ruff format --check src/ tests/  # 236 文件已格式化
mypy src/abi/ --ignore-missing-imports  # 0 错误
pytest tests/ -v --tb=short   # 1364+ 通过
```

### 隔离性

- 使用 `tmp_path`（pytest 内置）实现文件系统隔离 — 切勿写入项目目录
- 使用 `mock_sample` 和 `mock_sample_context` fixtures 共享测试数据 — 避免重复构建样本
- 不要依赖测试执行顺序 — 每个测试应可独立运行

### 插件的合约测试

每个新插件应至少包含：

```python
def test_plugin_contract():
    """插件满足 ABIPlugin 协议。"""
    from abi.testing import assert_plugin_contract
    plugin = MyPlugin()
    assert_plugin_contract(plugin)


def test_registry_loads():
    """工具注册表 YAML 解析无错误。"""
    plugin = MyPlugin()
    registry = plugin.registry()
    assert len(registry.tools) > 0


def test_build_plan():
    """build_plan() 对默认配置返回有效的 ExecutionPlan。"""
    plugin = MyPlugin()
    plan = plugin.build_plan(...)
    assert len(plan.steps) > 0
    # 验证步骤顺序
    tool_ids = [s.step_id for s in plan.steps]
    assert tool_ids[0] == "qc_fastp"  # QC 始终最先
```

### 基准测试阈值

基准测试应达到以下目标：

| 阶段 | 阈值 | 适用场景 |
|------|------|---------|
| **开发中** | ≥ 70% 断言通过 | 插件正在积极开发 |
| **稳定** | ≥ 80% 断言通过 | 插件解析器已验证 |
| **发布** | ≥ 85% 断言通过 | 插件候选发布 |

## 覆盖率

CI 强制最低 60% 行覆盖率（当前：83%）。覆盖率基线通过以下方式维持：

- 所有解析器函数的单元测试
- CLI 和 dry-run 路径的集成测试
- 全部 7 个插件的合约测试

本地检查覆盖率：

```bash
pip install pytest-cov
pytest tests/ --cov=src/abi --cov-report=html
# 打开 htmlcov/index.html
```

## 测试故障排查

### 测试因"tool not found"失败

确保 conda 环境已设置且工具在 PATH 上：

```bash
abi check-resources --type <plugin_id>
```

### 基准测试断言失败

1. 检查 `expected_assertions.yaml` — 期望值是否仍然正确？
2. 工具输出格式是否已变更？重新运行并更新期望值。
3. 检查工具版本是否变更 — 某些工具在不同版本间会改变输出格式。

### Contract-lint 显示 `output_dir.exists()` 错误

这是静态合约分析的已知限制 — `output_dir` 在 lint 期间不在作用域内。
运行时合约执行正常工作。这不影响执行。

### 测试隔离问题

如果测试相互干扰，请确保：
- 每个测试使用唯一的 `tmp_path`
- 没有测试修改全局状态（`os.environ`、模块级变量、`sys.path`）
- 需要真实工具的测试标记了 `@pytest.mark.requires_tools`

## 参见

- `docs/zh/plugin_development_guide.md` — 如何构建插件代码
- `docs/zh/development.md` — 源码树和 SDK 参考
- `CLAUDE.md` — 项目命令和架构
