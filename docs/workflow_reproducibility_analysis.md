# 将 Agent 驱动的生物信息学分析流程变为受约束、可验证、稳定复现的工作流

## 可行性分析、缺陷清单、修复方案与实施计划

**文档版本**: 2.0
**日期**: 2026-06-16
**作者**: ABI 开发团队
**状态**: 本地 IDE 修复阶段已完成；HPC 验证阶段待启动

---

## 目录

1. [目标定义与当前状态评估](#1-目标定义与当前状态评估)
2. [缺陷分级清单](#2-缺陷分级清单)
3. [技术修复方案](#3-技术修复方案)
4. [测试场景设计](#4-测试场景设计)
5. [开发环境分类与实施计划](#5-开发环境分类与实施计划)
6. [HPC 环境需求规格](#6-hpc-环境需求规格)
7. [验收标准](#7-验收标准)

---

## 1. 目标定义与当前状态评估

### 1.1 三维度定义

| 维度 | 定义 | 判定标准 |
|---|---|---|
| **受约束 (Constrained)** | 计划的每一步都在 DAG 规范内；执行前需确认；输入/输出受契约校验；命令模板参数不静默缺失 | 无未授权的工具执行；无参数静默删除；输入格式错误在工具执行前被检测 |
| **可验证 (Verifiable)** | 每次执行产生完整的 provenance；校验和链可追溯到上游；标准表数据可追溯到原始输出文件 | 8 类 provenance 制品完整；校验和链不因重试而断裂；报告参数与实际执行一致 |
| **稳定复现 (Reproducible)** | 相同的输入 + 相同的工具版本 + 相同的参考数据库 → 相同的标准表输出（数值在浮点容差内） | 工具版本记录完整；参考数据库有 manifest；存在 golden dataset 用于回归测试 |

### 1.2 当前架构成熟度（更新：本地 IDE 修复后）

```
修复前:    ████████████░░░░░░░░  ~65% 完整
修复后:    ███████████████░░░░░  ~78% 完整
           ├─ 受约束  █████████████████░  90%  (+5%)
           ├─ 可验证  █████████████████░  90%  (+10%)
           └─ 可复现  ████████░░░░░░░░░░  40%  (+15%)
```

**本次修复带来的提升**:

| 维度 | 修复前 | 修复后 | 关键修复 |
|---|---|---|---|
| 受约束 | 85% | 90% | B27 SafeFormatDict strict 模式、B4 并发安全 |
| 可验证 | 80% | 90% | B25 原子校验和写入、B23 实际参数记录、B7 符号链接追踪、B18/B20 合约 lint |
| 可复现 | 25% | 40% | B13 浮点容差、B2 版本正则、B21 版本语义区分、B14 列序确定性 |

**已具备的能力**:

| 机制 | 成熟度 | 位置 |
|---|---|---|
| DAG 驱动计划生成 (84 节点, 5 平台) | 成熟 | `pipeline_dag.py` + `pipeline_dag.yaml` |
| 执行确认门控 (confirm_execution=true) | 成熟 | `permissions.py` |
| 步骤级输出契约校验 (6 种检查) | 成熟 | `contracts/step_contract.py` |
| 校验和链式传递 | 成熟 | `contracts/step_contract.py` |
| 完整 provenance 目录 (8 类制品) | 成熟 | `provenance.py` |
| 线程安全进度记录 | 成熟 | `PipelineProgressRecorder` |
| 14 个稳定错误码 + 诊断提示 | 成熟 | `diagnostics.py` |

**关键缺口**:

| 缺口 | 现状 | 影响维度 |
|---|---|---|
| 工具版本未捕获 (version 列始终为空) | `tool_versions.tsv` 中 version="" | 可复现 |
| 无参考数据库资源清单 | 路径记录但不记录版本/来源/checksum | 可复现 |
| 无生物学基准数据集 | `workflow_validation.md` 7 项标准零达成 | 可复现 |
| 输入格式校验仅检查文件存在性 | 不检查 FASTQ/FASTA 格式有效性 | 受约束 |
| 模板参数静默替换为空字符串 | `SafeFormatDict.__missing__` 返回 "" | 受约束 |
| 无 DAG/合约静态检查 | 错误只在运行时发现 | 可验证 |
| 报告参数可能与实际执行不一致 | Methods 使用 plan 参数而非实际执行参数 | 可验证 |

---

## 2. 缺陷分级清单

### 2.1 分级框架

```
P0 (红线): 不处理 = 目标不成立 — 直接破坏"受约束/可验证/稳定复现"至少一个维度
P1 (重要): 真实使用中严重影响用户 — 卡顿、OOM、provenance 可信度受损
P2 (优化): 技术债务 — 当下可绕过，越晚修成本越高
```

### 2.2 完整缺陷清单 (27 项)

#### P0 红线 (10 项)

| # | 缺陷 | 破坏维度 | 用户感知 | 一句话理由 |
|---|---|---|---|---|
| **B5** | `tool_versions.tsv` version 列始终为空 | 可复现 | 中等 | provenance 核心字段缺失，"可复现"无从谈起 |
| **B11** | Golden file 绑定特定工具版本，升级后基准自动失效 | 可复现 | 高 | 唯一的生物学验证机制自身不可靠 |
| **B15** | FASTQ 格式校验只看前 100 行 | 受约束 | 极高 | 输入侧的约束是漏的，损坏数据流入分析 |
| **B16** | gzip 压缩文件当作文本直接校验 | 受约束 | 极高 | 产生系统性错误生物学结论 |
| **B23** | Methods 报告中参数与实际执行不一致 | 可验证+可复现 | 高 | 科学诚信问题 |
| **B25** | 步骤重试导致校验和链断裂 | 可验证+可复现 | 中 | 核心验证机制在真实场景中不可用 |
| **B27** | SafeFormatDict 参数静默删除 | 受约束 | 极高 | "受约束"最直接的失败——执行的命令不可控 |
| **B13** | 浮点数用 `==` 比较 | 可复现 | 高 | 基准校验的假阳性制造机 |
| **B8** | 资源文件 TOCTOU：只在 run 开始时校验一次 | 可验证 | 中 | 工具实际读取的数据与校验过的数据可能不同 |
| **B7** | 符号链接只 hash 链接本身不追踪目标 | 可验证 | 低 | SHA256 不反映实际内容 |

#### P1 重要 (9 项)

| # | 缺陷 | 用户感知 | 发生条件 |
|---|---|---|---|
| **B1** | 版本获取失败阻断整个流程 | "为什么 version 命令失败就不让我跑？" | 工具版本命令拼写错误或退出码非零 |
| **B3** | 版本命令执行超时阻塞流程 | 界面卡在"正在获取工具版本…" | 数据库索引工具启动慢 |
| **B6** | 大文件 SHA256 计算阻塞 | 流程在某个步骤"卡住" | 输出文件 >10GB |
| **B17** | 大文件格式校验全量加载到内存 | 16GB FASTQ 校验导致 OOM | 输入文件较大 |
| **B4** | 并发执行时工具版本信息写入错误行 | provenance 数据错乱 | 多线程执行 |
| **B24** | 部分样本失败的状态处理不明确 | "三个样本有一个失败，整体算成功还是失败？" | 多样本并行执行 |
| **B18** | DAG depends_on 引用未定义节点，lint 不检查 | DAG 增长后人工检查不可能 | 拼写错误 |
| **B20** | Assertion 表达式语法错误 lint 不检查 | 大量断言在运行时才发现语法错误 | 断言数量增长 |
| **B19** | 跨文件间接循环未检测 | 多团队贡献合约后可能引入循环 | A→B→C→A |

#### P2 优化 (8 项)

| # | 缺陷 | 为什么是技术债务 |
|---|---|---|
| **B2** | 版本格式解析假设统一格式 | 每新增一个工具版本解析就可能失败 |
| **B9** | 不可达的 source_url 阻断流程 | 内网/离线环境无法运行 |
| **B10** | 资源字段包含换行符破坏 TSV | 自由文本字段迟早遇到 |
| **B12** | 基准数据集过大无法在 CI 运行 | 不在 CI 的测试迟早默默失效 |
| **B14** | Golden file 列顺序依赖 Python dict 遍历序 | 跨版本假阳性消耗调试时间 |
| **B21** | 报告中版本写 "unknown" vs "not captured" | 语义模糊，新团队成员无法区分 |
| **B22** | CrossRef API 不可用时报告生成失败 | 分析跑完但报告没生成 |
| **B26** | NFS 上 os.rename 非原子操作 | HPC 部署后暴露 |

### 2.3 优先级矩阵

```
        破坏目标    用户强烈感知    仅技术债务
        ───────    ──────────     ────────
P0      B5 B11     B16 B27
(立即)  B15 B25    B13
        B23 B7 B8

P1      —          B1 B3 B6       B18 B20
(本迭代)            B17 B24 B4    B19

P2      —          —              B2 B9 B10
                                  B12 B14 B21
                                  B22 B26
```

---

## 3. 技术修复方案

### 3.1 修复原则

1. **版本获取失败不阻断流程** — 版本是元数据，不应阻塞分析执行
2. **渐进式严格化** — 生产环境 lenient (WARNING)，CI/开发环境 strict (ERROR)
3. **流式处理** — 所有大文件操作使用流式 I/O，不加载全文件到内存
4. **原子写入** — 所有 provenance 文件使用 `tmp → fsync → rename` 模式
5. **Golden file 版本绑定** — 工具版本不匹配 → skip（非 fail），不制造假阳性
6. **浮点数容差** — 使用 `math.isclose` 替代 `==` 比较

### 3.2 P0 核心修复方案

#### B27: SafeFormatDict 严格模式

**文件**: `src/abi/tools.py`
**当前行为**: `SafeFormatDict.__missing__()` 对缺失 key 返回 `""`
**问题**: 命令模板中引用了未注册变量 → 静默替换为空字符串 → 实际执行的命令缺少关键参数
**修复**:

```python
class SafeFormatDict(dict):
    """A dict subclass that handles missing keys during str.format_map().

    In strict mode (default for development), raises MissingTemplateParamError
    for unrecognized keys. In lenient mode (production), returns ""
    and logs a WARNING.
    """

    def __init__(self, *args, strict: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.strict = strict
        self._missing: list[str] = []

    def __missing__(self, key: str) -> str:
        self._missing.append(key)
        if self.strict:
            raise MissingTemplateParamError(
                f"Command template references undefined parameter {key!r}. "
                f"Add it to select_params() or OPTIONAL_TEMPLATE_FIELDS."
            )
        import logging
        logging.getLogger("abi.tools").warning(
            "Template parameter %r missing; substituting empty string", key
        )
        return ""
```

**启用**: 环境变量 `ABI_STRICT_TEMPLATES=1` 控制；`pyproject.toml` 中 pytest 默认设置

#### B25: 校验和链重试安全

**文件**: `src/abi/contracts/step_contract.py`
**新增函数**:

```python
def save_checksums_atomic(provenance_dir: str | Path, checksums: dict) -> Path:
    """Write checksums via tmp+rename for atomicity."""
    path = Path(provenance_dir) / CHECKSUMS_FILENAME
    tmp_path = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(checksums, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp_path, path)
    return path

def invalidate_step_checksums(checksums: dict, contract_spec: dict) -> None:
    """Remove checksums for outputs declared in a step contract."""
    for key in contract_spec.get("outputs", {}):
        to_remove = [k for k in checksums if key in Path(k).name or k.endswith(key)]
        for k in to_remove:
            del checksums[k]
```

#### B13: 浮点数容差比较

**文件**: `src/abi/contracts/step_contract.py`
**修改**: `evaluate_assertions()` 的 safe_namespace 中增加:

```python
safe_namespace.update({
    "isclose": _isclose_for_assertions,
})

def _isclose_for_assertions(a, b, rel_tol=1e-9, abs_tol=0.0):
    import math
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)
```

#### B23: Methods 报告使用实际执行参数

**文件**: `src/abi/tools.py` + `src/abi/provenance.py`
**修改**:

1. `RunResult` 增加 `resolved_params: dict` 字段
2. `GenericCommandSkill.run()` 中填充 `resolved_params=selected`
3. 新增 `write_methods_md()` 函数，从 `command_rows` + `tool_versions` + `resources` 生成 methods.md

### 3.3 工作量估算

| 优先级 | 总工时 | 关键路径 |
|---|---|---|
| P0 (全部) | 13.5 天 | B15 + B11 是瓶颈 |
| P1 (全部) | 5 天 | B18+B20 是最大单块 |
| P2 (全部) | 5 天 | B26 需要 HPC 验证 |
| **合计** | **23.5 天** | P0 完成 = 目标基本达成 |

---

## 4. 测试场景设计

### 4.1 正向测试场景 (6 类)

| 类别 | 场景数 | 关键场景 |
|---|---|---|
| A — 受约束 (Constrained) | 5 | DAG 拓扑排序、确认门控、输出契约、校验和链、跨平台分支 |
| B — 可验证 (Verifiable) | 4 | 8 类制品完整性、失败后仍写入、标准表格式、JSON 信封契约 |
| C — 可复现 (Reproducible) | 6 | 版本捕获、资源清单、两次执行一致性、基准断言、合约 lint、methods 报告 |

### 4.2 负向测试场景 (12 项)

- TC-N1: 未确认执行被拒绝
- TC-N2: DAG 循环依赖检测
- TC-N3: 不存在的输出文件触发 ContractViolation
- TC-N4: 校验和不匹配阻断下游
- TC-N5: 权限越界拒绝
- TC-N6: 即时取消后的清理
- TC-N7: Parser 异常不静默
- TC-N8: 输出目录不可写 fast-fail
- TC-N9: 磁盘空间耗尽处理
- TC-N10: version_command 失败不阻断
- TC-N11: 资源文件被外部篡改
- TC-N12: 并发写入相同 outdir

### 4.3 边界测试场景 (8 项)

- TC-E1: 空样本列表
- TC-E2: n=1 vs n=100 样本
- TC-E3: >10GB 输出文件
- TC-E4: 工具超时处理
- TC-E5: min_size=0 空文件
- TC-E6: 1 节点 vs 84 节点 DAG
- TC-E7: 特殊字符文件名
- TC-E8: NTP 时间跳跃

### 4.4 易遗漏场景 (17 项)

- 并发: 子进程 force-kill 竞态、PipelineProgressRecorder 并发写入、Job 取消/完成竞争
- 幂等性: 同一 outdir 重复 run、plan 生成幂等性、重试失败步骤的 checkpoint resume
- 资源泄漏: Job Service 长期运行内存、Conda 环境残留、子进程孤儿
- 数据一致性: checksums.json 原子写入、标准表与原始输出一致性、TSV 引号转义
- 跨版本: pipeline_dag.yaml 格式演进、旧 checksums.json 向后兼容
- 异常路径: NFS 文件操作、SIGINT 多层传播、非 UTF-8 字节处理

---

## 5. 开发环境分类与实施计划

### 5.1 分类标准

```
本地 IDE 全流程:  纯逻辑、静态分析、mock/小文件可覆盖、单元测试可验证
本地开发+HPC验证: 逻辑本地完成，但需 HPC 确认大文件性能/极限情况
HPC 核心工作:     必须真实工具执行、大文件 I/O、并发/分布式、NFS
```

### 5.2 分类矩阵

```
                ┌─ 本地 IDE  ─┬─ 本地开发   ─┬─ 必须 HPC ─┐
                │   全流程    │ + HPC 验证    │   核心工作   │
────────────────┼─────────────┼───────────────┼─────────────┤
P0              │ B27 B25 B13 │ B15 B16 B5 B1 │ B11         │
                │ B23         │               │             │
P1              │ B4 B7 B18   │ B17 B6        │ B8 B3       │
                │ B20         │               │             │
P2              │ B14 B19 B21 │               │ B12 B26     │
                │ B2 B9 B10   │               │             │
                │ B22         │               │             │
────────────────┼─────────────┼───────────────┼─────────────┤
合计            │ 15 个       │ 6 个           │ 6 个        │
```

### 5.3 推荐开发顺序

#### 阶段 1: 本地开发冲刺 (Week 1-2)

```
并行组 A (tools.py 改造):
  ├─ B27 SafeFormatDict strict    ← 1d
  ├─ B5 + B1 + B3 版本捕获       ← 2d
  └─ B2 版本格式解析              ← 0.5d (含在 B5 中)

并行组 B (contracts/ 改造):
  ├─ B13 浮点数 isclose          ← 1d
  ├─ B25 校验和链重试            ← 1.5d
  └─ B15 + B16 输入格式校验      ← 3d

并行组 C (provenance/report 改造):
  ├─ B23 Methods 报告            ← 2d
  └─ B21 版本语义区分            ← 0.5d

并行组 D (静态分析):
  ├─ B18 + B20 Lint 工具         ← 3d
  └─ B19 跨文件循环检测          ← 1d
```

#### 阶段 2: 本地 + HPC 混合 (Week 3)

```
  ├─ B15/B16/B17/B6 大文件验证    ← HPC 上跑 1 天
  ├─ B11 Golden dataset 生成      ← HPC 上跑 2 天
  ├─ B4 B7 B8 并发/symlink/TOCTOU ← 本地 1d + HPC 半天
  └─ B26 NFS 原子写入             ← HPC 半天
```

#### 阶段 3: CI 集成 (Week 4)

```
  ├─ B12 基准 CI 集成             ← 本地 1d + HPC 裁切数据集
  └─ B14 Golden file 列序稳定    ← 本地 0.5d
```

---

## 6. HPC 环境需求规格

| 资源 | 最低规格 | 推荐规格 | 用途 |
|---|---|---|---|
| 计算节点 | 16 cores, 64GB RAM | 32 cores, 128GB RAM | 全流程 golden run |
| 存储 | 500GB 可用 | 1TB 可用 | 中间文件 + provenance |
| 共享文件系统 | NFSv4 | NFSv4 + 本地 SSD 缓存 | B26 NFS 验证 |
| Conda | 完整 67 工具环境 | 含 conda-lock | B5 版本捕获验证 |
| 测试数据 | ZymoBIOMICS | ZymoBIOMICS + 自定义 mock 群落 | B11 golden dataset |

---

## 7. 验收标准

### 7.1 P0 验收 (目标是否达成)

- [ ] `tool_versions.tsv` 中 `version` 列非空率 > 90%
- [ ] `SafeFormatDict` 在 CI 环境为 strict 模式, 生产环境 lenient + WARNING
- [ ] Golden dataset 验证工具版本不匹配时 skip 而非 fail
- [ ] FASTQ 格式校验覆盖前 1000 行 + 尾 1000 行 + 随机采样
- [ ] gzip 文件透明解压后校验
- [ ] `methods.md` 中的参数与 `commands.tsv` 一致
- [ ] 重试步骤后 checksums.json 不包含过期 hash
- [ ] `isclose` 可用于 DAG assertion 表达式
- [ ] 资源校验在每个步骤执行前重新执行
- [ ] 符号链接跟踪目标文件进行 SHA256 计算

### 7.2 P1 验收 (用户质量)

- [ ] 版本获取失败不阻断流程
- [ ] `abi contract-lint` 检测循环依赖和孤立节点
- [ ] 大文件 (>10GB) SHA256 计算期间显示进度
- [ ] 大文件 (>10GB) 输入校验不 OOM
- [ ] 并发写入 provenance 文件数据不错乱
- [ ] Partial failure 语义明确定义

### 7.3 P2 验收 (可持续性)

- [ ] 基准数据集在 CI 中运行且 <30 分钟
- [ ] Golden file 列顺序确定性
- [ ] NFS 原子写入验证通过
- [ ] version 空值语义明确区分
- [ ] 离线环境可正常运行

---

---

## 8. 实施记录（2026-06-16 更新）

### 8.1 已完成：本地 IDE 修复（15/15）

| # | 优先级 | 缺陷 | 文件 | 测试 | 状态 |
|---|---|---|---|---|---|
| B27 | P0 | SafeFormatDict 静默删除参数 | `tools.py` + `errors.py` | `test_tools.py` 14 项 | ✅ |
| B25 | P0 | 校验和链重试断裂 | `step_contract.py` + `executor.py` | `test_step_contract.py` 11 项 | ✅ |
| B13 | P0 | 浮点数 `==` 比较 | `step_contract.py` | `test_step_contract.py` 6 项 | ✅ |
| B23 | P0 | Methods 报告参数与实际不一致 | `tools.py` + `provenance.py` | 集成测试 | ✅ |
| B7 | P1 | 符号链接 hash 不正确 | `step_contract.py` | `test_step_contract.py` 3 项 | ✅ |
| B4 | P1 | 并发写入工具版本错行 | `executor.py` | 回归测试 | ✅ |
| B18 | P1 | DAG broken depends_on 未检测 | `contracts/lint.py` + `cli.py` | `test_contract_lint.py` 10 项 | ✅ |
| B20 | P1 | Assertion 语法错误未检测 | `contracts/lint.py` | `test_contract_lint.py` 7 项 | ✅ |
| B19 | P2 | 跨文件循环未检测 | `contracts/lint.py` | `test_contract_lint.py` 2 项 | ✅ |
| B21 | P2 | version 语义模糊 | `provenance.py` | `write_methods_md` 输出 | ✅ |
| B2 | P2 | 版本格式无 regex 支持 | `tools.py` | `capture_version()` | ✅ |
| B14 | P2 | 列顺序不确定性 | `_shared.py` | `_sorted_columns()` | ✅ |
| B10 | P2 | TSV 换行符破坏结构 | `provenance.py` (已有) | 已有实现 | ✅ |
| B9 | P2 | source_url 阻断离线流程 | `_shared.py` | `_fetch_url_safe()` | ✅ |
| B22 | P2 | CrossRef API 超时无 fallback | `_shared.py` | `_fetch_url_safe()` | ✅ |

### 8.2 新增能力

| 新增项 | 位置 | 说明 |
|---|---|---|
| `abi contract-lint` CLI 命令 | `cli.py` + `contracts/lint.py` | DAG 循环/孤立/断链检测 + 断言语法预检 + 合约-注册表交叉校验 |
| `SafeFormatDict` strict 模式 | `tools.py` | `ABI_STRICT_TEMPLATES=1` 开启, CI 默认启用 |
| `save_checksums_atomic()` | `step_contract.py` | tmp→fsync→rename 原子写入 |
| `invalidate_step_checksums()` | `step_contract.py` | output_dir/output_paths/contract_spec 三策略 |
| `write_methods_md()` | `provenance.py` | 从实际执行参数生成方法学报告 |
| `capture_version()` | `tools.py` | 工具版本捕获 + version_regex 支持 |
| `_fetch_url_safe()` | `_shared.py` | 10s 超时 HTTP 请求 + 失败返回 "" |
| `_sorted_columns()` | `_shared.py` | 字典列表列序确定化 |
| `MissingTemplateParamError` | `errors.py` | strict 模式下模板参数缺失异常 |

### 8.3 测试覆盖

| 测试文件 | 新增测试 | 总测试数 |
|---|---|---|
| `tests/unit/test_tools.py` (新建) | 14 | 14 |
| `tests/unit/test_step_contract.py` (扩展) | 20 | 53 |
| `tests/unit/test_contract_lint.py` (新建) | 25 | 25 |
| `tests/unit/test_executor.py` (回归) | — | 5 |
| **全量测试** | **+59** | **306 passed, 0 failed** |

### 8.4 剩余未修复缺陷（需要 HPC 环境）

| # | 优先级 | 缺陷 | 为什么需要 HPC | 预计工时 |
|---|---|---|---|---|
| B11 | P0 | Golden file 浮动基准 | 需要运行完整 metagenomic_plasmid 管线生成基准数据 | 3d |
| B15 | P0 | FASTQ 格式校验只看前 100 行 | 本地可开发逻辑；需 HPC 大文件验证不 OOM | 3d |
| B16 | P0 | gzip 文件当作文本校验 | 本地可开发；需 HPC 验证 30GB gzip 流式读取 | (含 B15) |
| B5 | P0 | tool_versions version 列始终为空 | `capture_version()` 已实现；需 HPC 验证所有 67 个工具的 version_command | 2d |
| B1 | P1 | 版本获取失败阻断流程 | capture_version 异常处理已实现；需 HPC 验证 | (含 B5) |
| B3 | P1 | 版本命令超时阻塞 | 本地 10s 超时已配置；需 HPC 验证冷启动慢的工具 | (含 B5) |
| B6 | P1 | 大文件 SHA256 阻塞 | 流式 hash 已实现；需 HPC 验证 >50GB 文件 | 0.5d |
| B17 | P1 | 大文件格式校验 OOM | 本地采样逻辑可开发；需 HPC 验证 100GB+ 文件 | (含 B15) |
| B8 | P1 | 资源文件 TOCTOU | 需共享存储多节点模拟并发修改 | 1d |
| B12 | P2 | 基准 CI 数据集过大 | 需 HPC 裁切 golden dataset 到 <1GB | 2d |
| B26 | P2 | NFS 原子写入 | 需 NFSv4 挂载验证 os.replace 行为 | 1d |
| B24 | P1 | Partial failure 语义 | 需多样本并行 HPC 运行验证 | 1d |

---

## 9. 下一步实施计划

### 9.1 阶段 2: 本地开发 + HPC 验证（预计 2 周）

```
Week 3:
  Day 1-3:  本地开发 B15 + B16（输入格式校验采样策略）
             本地开发 B17（流式校验，复用 B15 框架）
  Day 4-5:  HPC 验证 B15/B16/B17（使用 ZymoBIOMICS 数据）
             HPC 验证 B5（67 个工具 version_command 批量采集）
             HPC 验证 B6（>50GB 文件流式 SHA256 性能）

Week 4:
  Day 1-2:  HPC 生成 B11 golden dataset
             HPC 验证 B8（多节点 TOCTOU 模拟）
  Day 3:    HPC 裁切 B12 CI 数据集
             HPC 验证 B26（NFS 原子写入）
  Day 4-5:  集成测试：全流程回归 + golden file 比对
```

### 9.2 HPC 环境最低要求

| 资源 | 规格 | 用途 |
|---|---|---|
| 计算节点 | 16+ cores, 64GB+ RAM | 全流程 golden run |
| 存储 | 500GB+ 可用空间 | 中间文件 + provenance |
| 共享文件系统 | NFSv4 挂载 (2+ 节点) | B8 TOCTOU + B26 原子写入 |
| Conda | 完整的 67 工具环境 | B5 版本捕获 |
| 测试数据 | ZymoBIOMICS 或其他标准 mock 群落 | B11 golden dataset |

### 9.3 验收标准（阶段 2 完成后）

- [ ] `tool_versions.tsv` 中 `version` 列非空率 > 90%
- [ ] FASTQ 格式校验覆盖 ≥ 1000 行采样
- [ ] gzip 文件透明解压后校验
- [ ] >50GB 文件 SHA256 计算不阻塞流程进度显示
- [ ] >50GB 文件格式校验内存 < 512MB
- [ ] Golden dataset 至少 1 个完整管线验证通过
- [ ] Golden file 列顺序确定性
- [ ] NFS 原子写入在 2 节点上验证通过
- [ ] 基准 CI 数据集 < 1GB 且运行 < 30 分钟
- [ ] 离线环境 `abi run` 可正常运行
- [ ] 306 个现有测试全部通过（回归）

## 附录 A: 相关文件索引

| 文件 | 涉及缺陷 |
|---|---|
| `src/abi/tools.py` | B27, B5, B1, B3, B2, B4, B15, B16, B17, B6 |
| `src/abi/contracts/step_contract.py` | B25, B13, B7, B8 |
| `src/abi/executor.py` | B25, B23, B4 |
| `src/abi/provenance.py` | B23, B21, B10 |
| `src/abi/cli.py` | B18, B20, B19 |
| `src/abi/report.py` | B23, B22 |
| `plugins/*/pipeline_dag.yaml` | B18, B19 |
| `plugins/*/tool_contracts/*.yaml` | B5, B20, B15 |
| `src/abi/filesystem.py` | B26 |
| `tests/` | 全部 |

## 附录 B: 环境变量一览

| 变量 | 默认值 | 用途 |
|---|---|---|
| `ABI_STRICT_TEMPLATES` | `0` (生产) / `1` (CI) | B27 SafeFormatDict 模式 |
| `ABI_TOOL_TIMEOUT_SECONDS` | 随工具不同 | B3/B6 超时控制 |
| `ABI_MAMBA_ROOT` | 自动检测 | Conda 环境路径 |
| `ABI_VERSION_TIMEOUT` | `10` | B5 版本命令超时(秒) |
