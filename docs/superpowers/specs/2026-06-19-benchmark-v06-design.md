# ABI-Bench v0.6 综合改进设计文档

**日期**: 2026-06-19
**状态**: 设计已批准
**关联**: [[next_development_plan]], [[benchmark]]

## 概述

对 ABI-Bench 进行三层综合改进，从 v0.5 升级到 v0.6：

```
Layer 1: 夹具数据层 — 补全 T31-T35 真实执行夹具
Layer 2: 评分与执行框架层 — 真实输出验证、原生多 Provider、失败分类 v2、统计增强
Layer 3: 新任务模块层 — Figure 验证、渐进修复、跨平台一致性、多 Agent 协作（T36-T47）
```

## Layer 1: 夹具数据层

### 现状
5 个 `*_benchmark/` 目录只有 `config.yaml` 骨架，缺少 assertion 文件、样本数据、和资源文件。T31-T35 任务定义完整但无法实际运行。

### 改动

1. **同步 ABI `data/benchmarks/` → Bench `fixtures/*_benchmark/`**
   - 复制 `expected_assertions.yaml`（5 个插件各有完整断言）
   - 复制 `config.yaml`（更新为可执行配置）
   - 新增 `sample_sheet.tsv`

2. **合成数据生成脚本** — `bench/fixtures/generate_synthetic_data.py`
   - 用 Python/BioPython 按每个插件需求生成最小合成 FASTQ/FASTA
   - metagenomic_plasmid: 已有 RefSeq plasmid 数据（`data/examples/plasmid_refseq_smoke/`）
   - rnaseq_expression: 合成 E. coli lacZ reads（200 reads × 2 conditions）
   - amplicon_16s: 合成 16S V4 扩增子（3 bacterial references）
   - wgs_bacteria: 合成 bacterial genome paired-end reads
   - metatranscriptomics: 合成 transcriptomic RNA-seq reads

3. **迷你资源数据库**
   - 为 plasmid benchmark 生成迷你 Bakta DB（基于 3 个 RefSeq plasmids）
   - 为 rnaseq benchmark 生成迷你 STAR 索引（基于 E. coli lacZ）

### 新增/修改文件

```
bench/fixtures/
  generate_synthetic_data.py          # 统一合成数据生成入口
  plasmid_benchmark/
    config.yaml                       # 更新
    expected_assertions.yaml          # 从 ABI 同步
    sample_sheet.tsv                  # 新增
    data/                             # 合成 FASTQ
  rnaseq_benchmark/                   # 同上结构
  amplicon_benchmark/                 # 同上结构
  wgs_benchmark/                      # 同上结构
  metatranscriptomics_benchmark/      # 同上结构
```

## Layer 2: 评分与执行框架层

### 改动

1. **真实输出验证** (`checks.py` + ~400 行)
   - `check_pipeline_outputs_match_assertions()`: 逐项对照 expected_assertions.yaml 验证
   - `check_per_category_breakdown()`: 按 qc/assembly/annotation 等类别统计通过率
   - `check_output_file_integrity()`: 验证关键输出文件存在且非空
   - `check_assertion_value_in_range()`: 数值范围比较（min/max）
   - `check_assertion_string_contains()`: 字符串包含验证（grep 报告/日志）

2. **Per-plugin 断言加载** (`score_run.py` + ~150 行)
   - 对 `task_type: real_execution` 任务，自动加载 `expected_assertions.yaml`
   - 合并 agent 行为评分 + 输出断言评分

3. **原生多 Provider 支持** (`direct_agent.py` + ~300 行)
   - Anthropic 原生 SDK: `anthropic.Anthropic().messages.create()`
   - Google 原生 SDK: `google.genai.GenerativeModel.generate_content()`
   - 统一调用抽象 `_call_llm(provider, messages, tools)`
   - 保留 openai-compatible 兜底路径

4. **失败分类 v2**
   - 新增 6 种 code: pipeline_crashed, assertion_failed, resource_not_found,
     tool_version_mismatch, output_truncated, partial_completion
   - 从 6 种扩展到 12 种

5. **统计增强** (`compute_statistics.py` + ~200 行)
   - 效应量矩阵: Cohen's d × group pair × task 热力图数据
   - Scaffolding 分解: 按 model tier × task module 拆解
   - Token 效率分析: thinking_tokens / output_tokens 比值
   - 输出 JSON 可直接喂给 abi-sciplot 画图

### 新增/修改文件

```
bench/scoring/
  checks.py               # +400 行
  score_run.py             # +150 行
  rubric.yaml              # +60 行
  compute_statistics.py    # +200 行

bench/harness/
  direct_agent.py          # +300 行
  run_task.py              # +30 行

bench/docs/
  failure_cases.md         # 更新: v2 分类体系
```

## Layer 3: 新任务模块层

### T36-T38: Figure 验证模块

| 任务 | 名称 | 插件 | 分值 |
|------|------|------|------|
| T36 | 验证 Figure 输出 | metagenomic_plasmid | 12 |
| T37 | 诊断图表问题 | rnaseq_expression | 10 |
| T38 | 图表与数据一致性 | amplicon_16s | 14 |

核心能力: agent 使用 abi-sciplot lint + 数据对照验证科学图表。

### T39-T41: 渐进修复模块

| 任务 | 名称 | 插件 | 分值 |
|------|------|------|------|
| T39 | 单步失败修复 | wgs_bacteria | 12 |
| T40 | 多步失败修复 | metagenomic_plasmid | 15 |
| T41 | 资源自配置 | rnaseq_expression | 14 |

核心能力: agent 从 provenance 诊断失败、修改配置、恢复执行。

### T42-T44: 跨平台一致性模块

| 任务 | 名称 | 分值 |
|------|------|------|
| T42 | 对比 local vs Nextflow 计划 | 10 |
| T43 | 对比 Docker vs local 输出 | 12 |
| T44 | 验证 provenance 完整性 | 8 |

核心能力: agent 验证同一 pipeline 在不同运行时下的输出一致性。

### T45-T47: 多 Agent 协作模块

| 任务 | 名称 | 分值 |
|------|------|------|
| T45 | Planner + Reviewer 协作 | 12 |
| T46 | 交叉验证（不同模型视角） | 14 |
| T47 | 零样本跨插件知识传递 | 10 |

核心能力: 多角色协作、跨模型不确定性评估、跨插件知识传递。

### 新增文件清单

```
bench/tasks/
  T36_figure_validation.yaml
  T37_figure_diagnosis.yaml
  T38_figure_data_consistency.yaml
  T39_single_step_recovery.yaml
  T40_multi_step_recovery.yaml
  T41_resource_self_config.yaml
  T42_local_vs_nextflow_diff.yaml
  T43_docker_vs_local_output_diff.yaml
  T44_provenance_completeness_audit.yaml
  T45_planner_reviewer_collaboration.yaml
  T46_cross_model_verification.yaml
  T47_zero_shot_plugin_transfer.yaml

bench/fixtures/
  figure_validation/              
  partial_failure_wgs/            
  partial_failure_plasmid/        
  missing_resources_rnaseq/       
  dual_platform_results/          
```

## 优先级

```
P0 (必须): Layer 1 夹具数据 → T31-T35 可运行
P1 (核心): Layer 2 评分框架 → 原生 SDK + 断言验证 + 失败分类 v2
P2 (扩展): Layer 3 T36-T41 → Figure + 渐进修复
P3 (远景): Layer 3 T42-T47 → 跨平台 + 多 Agent
```

## 预估改动量

| 层级 | 新增行数 | 修改行数 | 新文件数 |
|------|---------|---------|---------|
| Layer 1 | ~800 | ~200 | 25+ |
| Layer 2 | ~1100 | ~500 | 1-2 |
| Layer 3 | ~1500 | ~100 | 16+ |
| **总计** | **~3400** | **~800** | **42+** |

## 不做什么（明确边界）

1. 不修改 ABI 核心代码（仅同步夹具数据）
2. 不新增 ABI 插件（benchmark 仅使用现有 5 个插件）
3. 不做大规模真实数据库下载（迷你合成数据）
4. T42-T44 跨平台一致性任务不要求实际 Docker/Nextflow 运行（检查静态输出）
5. 不在 v0.6 中引入真实 HPC 执行任务

## 成功标准

1. T31-T35 在 simulated 模式下全部通过（夹具数据完整）
2. T36-T47 的 task YAML 定义完整且 scoring checks 通过 validation
3. 新增 check 函数有对应单元测试
4. Anthropic/Google 原生 SDK 分支在至少 1 个 task 上验证通过
5. `claim_preflight.py` 对 v0.6 任务集通过完整性检查
