# ABI 方案 B 详细执行计划

> 目标期刊: ISMB 2027（主攻）→ Bioinformatics (Oxford)（备选）→ PLOS Comp Bio（保底）
>
> **日期**: 2026-06-17
> **总周期**: 约 6-7 个月（2026.06 → 2027.01）
> **前置文档**: `submission_strategy_analysis.md`（投稿策略分析）

---

## 目录

1. [方案 B 目标定义](#1-方案-b-目标定义)
2. [总时间线](#2-总时间线)
3. [阶段 0：止血修复](#3-阶段-0止血修复)
4. [阶段 1：DAG 可靠性工程](#4-阶段-1dag-可靠性工程)
5. [阶段 2：多 LLM 实验](#5-阶段-2多-llm-实验)
6. [阶段 3：真实执行 Demo](#6-阶段-3真实执行-demo)
7. [阶段 4：Benchmark 加固](#7-阶段-4benchmark-加固)
8. [阶段 5：生态扩展](#8-阶段-5生态扩展)
9. [阶段 6：数据分析与统计](#9-阶段-6数据分析与统计)
10. [阶段 7：论文写作](#10-阶段-7论文写作)
11. [并行化机会](#11-并行化机会)
12. [每周检查点](#12-每周检查点)
13. [资源估算](#13-资源估算)
14. [风险登记册](#14-风险登记册)

---

## 1. 方案 B 目标定义

### 1.1 核心交付

| 交付物 | 目标状态 | 验收标准 |
|--------|---------|---------|
| **多 LLM 实验** | 6+ 模型 × 3 层级 | 脚手架效应在至少 1 对模型间显著（p<0.05 bootstrap） |
| **Benchmark 加固** | 所有 MAJOR 缺陷修复 | claim_preflight 通过、unsafe_execution=0、hidden fixture 完成 |
| **真实执行 Demo** | Demo A + B + D 完成 | metatranscriptomics end-to-end + plasmid 8-tool + 多模型对比 |
| **生态扩展** | 3 个插件 | Amplicon 16S 完成至少 dry-run 验证 |
| **论文** | 完整稿件 | 4 项自洽性检查通过、pre-submission-reviewer 通过 |

### 1.2 非目标（明确不做）

- ❌ 不增加第 4 个插件
- ❌ 不部署公共 leaderboard
- ❌ 不跑全部 43 个工具的真实执行
- ❌ 不重新设计消融实验
- ❌ 不在 benchmark 主评分中加入真实执行任务

### 1.3 关键决策点

| 日期 | 决策 | 条件 |
|------|------|------|
| **2026.08.15** | 脚手架效应是否存在？ | 至少 1 对 weak/strong 模型完成 G1/G3 实验 |
| **2026.09.01** | 3 插件是否至少完成 dry-run？ | Amplicon 16S 插件部署 + dry-run 验证通过 |
| **2026.09.15** | 真实执行结果是否稳定？ | Demo A + B 完成，关键输出表与人类专家 ≥ 90% 一致 |
| **2026.10.01** | 是否冲 ISMB 2027？ | 以上三个条件 + 写作进度 on track |

---

## 2. 总时间线

```
2026 年 6 月 ──── 当前 ────
  Week 4       🔴 阶段 0: 止血修复
               

2026 年 7 月
  Week 1       🔴 阶段 1: DAG 可靠性工程
  Week 2       🔴 阶段 2: 多 LLM 实验 (第一批: Strong tier)
               

  Week 3       🔴 阶段 3: Demo A Week 1（环境准备 + 人工基线）
  Week 4       🔴 阶段 3: Demo A Week 2（故障注入 + 真实执行）

2026 年 8 月
  Week 1       🔴 阶段 3: Demo B Phase 1（数据 + 数据库）
  Week 2       🔴 阶段 3: Demo B Phase 2（人类专家基线）
               

  Week 3       🔴 阶段 3: Demo B Phase 3（故障注入 + Agent 恢复）
  Week 4       🔴 阶段 3: Demo B Phase 4（真实执行 + 验证）
               ⚡ 检查点 1: 脚手架效应评估

2026 年 9 月
  Week 1       🔴 阶段 3: Demo B Phase 5（缓冲） + Demo D 启动
  Week 2       🟡 阶段 5: Amplicon 16S 插件 Week 1-2
               ⚡ 检查点 2: 3 插件 dry-run 验证

  Week 3       🟡 阶段 5: Amplicon 16S Week 3 + 接入 ABI-Bench
  Week 4       🟡 阶段 3: Demo D 收尾
               ⚡ 检查点 3: 真实执行结果稳定性

2026 年 10 月
  Week 1       🟡 阶段 4: Benchmark 加固（结构化评分完善）
               ⚡ 检查点 4: ISMB Go/No-Go

  Week 2-3     🔵 阶段 6: 多 LLM 实验收尾 + 数据聚合
  Week 4       🔵 阶段 6: 统计分析（bootstrap CI + 交互效应 + failure taxonomy）

2026 年 11 月
  Week 1-2     制作 Figure 1-8
  ──── 论文写作 ────
  Week 3       Introduction + Related Work (§1-2)
  Week 4       ABI Architecture + Design (§3-4)

2026 年 12 月
  Week 1-2     ABI-Bench Design (§5) + Experiments + Case Study (§6)
  Week 3       内部审阅 + pre-submission-reviewer
  Week 4       修改 + 最终润色

2027 年 1 月
  🚀 投稿 ISMB 2027
```

---

## 3. 阶段 0：止血修复

**周期**: 3 天（2026.06 Week 4）
**优先级**: 🔴 最高 — 阻塞所有后续工作

### Task 0.1: 修复 unsafe_execution 逻辑（1 天）

**问题**: G3 unsafe_execution_rate=0.156，但 `primary_claim_supported=true`

**步骤**:

1. 检查 `bench/harness/abi_cli.py` 中 `run` 命令的 `confirmation_required` 逻辑
2. 检查 G1/G2/G3 agent profile 中 `abi_run` 的权限配置
3. 检查 `direct_agent.py` 是否在 agent prompt 中正确传达了 `abi_run` 的限制
4. 检查 `score_run.py` 中 T08 的 `check_no_real_execution` 检查逻辑
5. 追踪 unsafe execution 的根因：
   - Agent 是否绕过了 CLI 直接调 shell 执行工具？
   - Agent 是否在 prompt 中擅自设置了 `confirm_execution=true`？
   - T08 的 scoring check 是否正确检测了违规？

**修复方案 A**（如果可以修复）:
- 在 agent profile 中强化 `abi_run` 的禁止规则
- 在 `abi_cli.py run` 中增加二次确认机制
- 重跑 G3 T08 验证 → `unsafe_execution_rate=0`

**修复方案 B**（如果无法完全消除）:
- 诚实报告：`G3_unsafe_execution_zero: false`
- 将 claim 从 "eliminates unauthorized execution" 改为 "reduces unauthorized execution risk"
- 在 §6 中分析违规根因和 LLM agent 的安全局限性

**产出**: 修复后的代码 + 验证通过或诚实报告记录

### Task 0.2: 诚实化 claim 阈值（半天）

**问题**: Plan.md 预设 G3−G1≥20, G3−G2≥12，实际 6.94 和 10.87。summary.json 中 `delta_thresholds_used` 为 5（事后降低）。

**步骤**:

1. 更新 `bench/BENCHMARK_SPEC.yaml`:
```yaml
success_criteria:
  G3_min_total_score: 80
  # Original thresholds (pre-registered):
  G3_minus_G1_original_threshold: 20
  G3_minus_G2_original_threshold: 12
  # Observed thresholds (post-hoc, for reporting):
  G3_minus_G1_observed_delta: 6.94
  G3_minus_G2_observed_delta: 10.87
  # Revised thresholds for claim evaluation:
  G3_minus_G1_min_delta: 5  # post-hoc, see §6.X for justification
  G3_minus_G2_min_delta: 5  # post-hoc, see §6.X for justification
```

2. 更新 `summary.json` 和 `aggregate_scores.py` 中的 `claim_support` 逻辑：
   - 标记 `thresholds_revised_post_hoc: true`
   - 同时报告 `original_thresholds_met: false` 和 `revised_thresholds_met: true`

3. 确定论文叙事用语：
   - ❌ "ABI significantly improves..." 
   - ✅ "ABI moderately improves..." 或 "ABI yields consistent improvement..."

**产出**: 更新后的 SPEC + 论文叙事措辞决策

### Task 0.3: 决定消融实验处理方式（半天）

**问题**: A1/A3/A4 与 G3 无显著差异，与 simulated 结果（A1=51.72）形成巨大反差。

**决策框架**:

| 选项 | 做法 | 风险 |
|------|------|------|
| **A: 降级** | 消融从主实验降级到 Appendix，诚实讨论 LLM 补偿效应 | 审稿人可能认为实验设计有缺陷 |
| **B: 重设计** | 改为对比 "有 ABI CLI" vs "有同样完整的文档但没有 CLI" vs "只有 raw bash" | 需要 3-4 周重新设计和跑实验 |
| **C: 放弃** | 完全移除消融实验，论文聚焦 G1/G2/G3 主实验 | 审稿人可能问"ABI 的哪些组件贡献了优势？" |

**推荐**: 方案 A（降级到 Appendix）

理由：
- 主实验 G1/G2/G3 的信号足够支撑 C1-C4
- 诚实讨论 LLM 补偿效应本身就是有学术价值的发现（"LLM reasoning can compensate for missing structured components"）
- 不增加额外实验时间
- 在 Appendix 中报告 simulated 和 real 消融的对比，作为 interesting negative result

**论文中定位**:
> *"We attempted component-level ablation to isolate the contribution of provenance (A1), diagnostic hints (A3), and permission gating (A4). While simulated ablation showed dramatic differentiation, real LLM agents compensated for missing components through reasoning, resulting in minimal score differences. We report both sets of results transparently and discuss the implications for evaluating control-layer components in the presence of strong reasoning models."*

**产出**: 消融处理决策文档 + Appendix 内容大纲

---

## 4. 阶段 1：DAG 可靠性工程

**周期**: 1 周（2026.07 Week 1）
**优先级**: 🔴 最高 — 必须在 Demo A/B 之前完成，影响真实执行的正确性
**参考**: `demo_plan.md` §6

### 日计划

| 天 | Task | 产出 |
|----|------|------|
| Day 1 | Task 1: 扩展 `abi-plugin.yaml` schema → `WorkflowSpec` 数据类 | `contracts/__init__.py` 更新 |
| Day 2 | Task 2: metatranscriptomics workflow 声明 | `plugins/metatranscriptomics/abi-plugin.yaml` 增加 `workflow` 段 |
| Day 3-4 | Task 3: metagenomic_plasmid 核心子路径 workflow 声明（6-8 个工具） | `plugins/metagenomic_plasmid/abi-plugin.yaml` 增加 `workflow` 段 |
| Day 5 | Task 4: 修改 `infer_dag()` L1/L2/L3 逻辑 | `dag.py` 更新 |
| Day 5 | Task 5: 测试与验证 | 新增 golden case + negative test |

### 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| D1 | 两个插件的 `abi-plugin.yaml` 均包含 `workflow` 段 | `grep -A 5 "workflow:"` |
| D2 | 每个 workflow step 标注了 `citation` | schema 校验 |
| D3 | metatranscriptomics DAG 回归不变（3 步，2 条边） | 现有 golden case 测试 |
| D4 | metagenomic_plasmid 核心子路径 DAG 与人工标注一致 | 新增 ground truth 测试 |
| D5 | L1 ≠ L2 时触发 WARNING | 新增 negative test |
| D6 | `abi plan` 仍在毫秒级完成（无外部网络依赖） | benchmark |

---

## 5. 阶段 2：多 LLM 实验

**周期**: 6-8 周（2026.07 Week 2 → 2026.08 Week 4，与其他阶段并行）
**优先级**: 🔴 最高 — 脚手架效应是方案 B 的核心叙事

### 5.1 模型矩阵

| Tier | 模型 | Provider | 参数量 | 成本估计 | 优先级 |
|------|------|----------|--------|---------|--------|
| **Strong** | DeepSeek v4-pro | DeepSeek | ~685B (MoE) | ~$1.5/run | 🔴 已有数据 |
| **Strong** | GPT-4o | OpenAI | ~200B (估) | ~$2/run | 🔴 第一批 |
| **Strong** | Claude Sonnet 4 | Anthropic | ~200B (估) | ~$2/run | 🔴 第一批 |
| **Medium** | Qwen-72B | 开源/API | 72B | ~$0.5/run | 🟡 第二批 |
| **Medium** | GPT-4o-mini | OpenAI | ~8B (估) | ~$0.3/run | 🟡 第二批 |
| **Medium** | DeepSeek-v3 | DeepSeek | ~685B (MoE) | ~$1/run | 🟢 可选 |
| **Weak** | Qwen-7B | 开源本地 | 7B | ~$0.1/run | 🟡 第二批 |
| **Weak** | DeepSeek-lite | DeepSeek | ~16B (MoE) | ~$0.3/run | 🟡 第二批 |

**目标**: 至少完成 6 个模型（每 tier 2 个）。9 个模型是 stretch goal。

### 5.2 实验矩阵

```
Groups:    G1, G2, G3  (只跑主实验，不跑消融)
Tasks:     MVP 8 个 (T01, T02, T03, T05, T06, T08, T09, T10)
           可选加 T04, T07, T11, T12 (full v0.1 = 12 task)
Replicates: 3
Fixture:   public (主评分) + hidden (T05/T06/T07 防泄漏)

总计:
  MVP: 6 models × 3 groups × 8 tasks × 3 reps = 432 runs
  其中 54 个诊断 runs 需 hidden fixture 重跑
  估计 API 成本: ~$200-300
```

### 5.3 分批执行计划

#### 第一批：Strong Tier（1 周，2026.07 Week 2）

```
模型: GPT-4o + Claude Sonnet 4 (DeepSeek v4-pro 已有数据)
任务: 全部 MVP 8 个 task
产出: Strong tier 3 模型 × 3 groups × 8 tasks × 3 reps = 216 runs
成本: ~$120
```

#### 第二批：Medium + Weak Tier（2 周，2026.07 Week 3-4）

```
模型: Qwen-72B + GPT-4o-mini + Qwen-7B + DeepSeek-lite
任务: 全部 MVP 8 个 task
产出: Medium+Weak tier 4 模型 × 3 groups × 8 tasks × 3 reps = 288 runs
成本: ~$100
```

#### 第三批：Hidden Fixture 重跑（1 周，2026.08 Week 1）

```
模型: 全部 6+ 模型
任务: T05, T06, T07 (仅诊断 task 需 hidden fixture)
产出: 6 models × 3 groups × 3 tasks × 3 reps = 162 runs
成本: ~$50
```

### 5.4 实验执行 SOP

**单模型实验启动**:

```bash
# 1. 配置 .env
export ABI_BENCH_PROVIDER=<provider>
export ABI_BENCH_API_KEY=<key>
export ABI_BENCH_MODEL=<model_id>
export ABI_BENCH_MAX_TOKENS=8000

# 2. 运行 G3（先跑 G3 验证 ABI 可用）
python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public \
  --outdir bench/results/<model>/G3

# 3. 运行 G2
python bench/harness/run_group.py \
  --group G2 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public \
  --outdir bench/results/<model>/G2

# 4. 运行 G1
python bench/harness/run_group.py \
  --group G1 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public \
  --outdir bench/results/<model>/G1

# 5. Hidden fixture 重跑诊断 tasks
for task in T05 T06 T07; do
  for rep in 1 2 3; do
    python bench/harness/run_task.py \
      --group G3 --task $task --replicate $rep \
      --agent-mode direct \
      --experiment-set main --fixture-set hidden \
      --outdir bench/results/<model>/G3
  done
done
```

### 5.5 数据管理

```
bench/results/
  deepseek_v4_pro/   (已有)
  gpt4o/
    G1/T0{1,2,3,5,6,8,9,10}/replicate_{1,2,3}/score.json
    G2/T0{...}/...
    G3/T0{...}/...
  claude_sonnet_4/
    ...
  qwen_72b/
    ...
  ...

模型元数据记录 (per model):
  - model_id, provider, parameter_count
  - API cost per run / total
  - avg_thinking_tokens, median_agent_steps
  - 任何异常或重试
```

### 5.6 脚手架效应分析框架

**主分析**:

```
Mixed-effects model:
  Score ~ Group (G1/G2/G3) × ModelTier (Strong/Medium/Weak) + (1|Task)

Key hypotheses:
  H_scaffold: Group:ModelTier interaction significant
    → ABI benefit differs by model tier
  H_weak: Weak tier G3 − G1 > Strong tier G3 − G1
    → Scaffolding effect confirmed
```

**可视化** (Figure 4):

```
    Total Score
  100 ┤                                    ●G3
      │                          ●G3
   90 ┤              ●G3
      │    ●G1 ●G2
   80 ┤
      │                    ●G1
   70 ┤                        ●G2
      │        ●G1
   60 ┤            ●G2
      │
   50 ┤
      └─────────┼─────────┼─────────
              Strong    Medium     Weak
                 Model Tier
```

**如果脚手架效应不成立**（备选叙事）:
> *"ABI benefit is consistent across model scales — suggesting that the control layer addresses structural challenges in bioinformatics workflows that are independent of model capability."*

这也是一篇好论文的 finding。Null result 在这里是 informative 的。

---

## 6. 阶段 3：真实执行 Demo

**周期**: 7-9 周（2026.07 Week 3 → 2026.09 Week 4，多 LLM 实验并行）
**优先级**: 🔴 最高 — 堵住"从未跑过真实执行"的攻击

### 6.1 Demo A: metatranscriptomics 端到端（2 周）

**叙事角色**: 快速验证 ABI 的 `run` 路径在真实计算中完整可走

#### Week 1: 环境准备 + 人工基线（2026.07 Week 3）

| 天 | 任务 | 产出 |
|----|------|------|
| Day 1-2 | 环境准备：下载 E. coli K-12 MG1655 参考基因组 (NCBI GCF_000005845.2)、构建 STAR 索引、安装 fastp/STAR/featureCounts | 可用的工具环境 |
| Day 3-4 | 人工基线：手动跑 fastp → STAR → featureCounts，保存每个命令的参数、tool_versions.txt、输出文件 | `baseline/gene_expression.tsv` + `baseline/tool_versions.txt` |
| Day 5 | ABI 配置：编写 `config.yaml` + `sample_sheet.tsv`，验证 `abi dry-run` 通过 | 通过 dry-run 的配置 |

#### Week 2: 故障注入 + 真实执行 + 对比（2026.07 Week 4）

| 天 | 任务 | 产出 |
|----|------|------|
| Day 1-2 | 故障注入 1: FASTQ 路径错误 → Agent 通过 diagnostic_hints 修复 → 重新 dry-run 通过 | 故障-恢复轨迹 (≤3 步) |
| Day 3 | 故障注入 2: STAR 索引路径错误 → Agent 修复 → 再次 dry-run 通过 | 故障-恢复轨迹 |
| Day 4 | 真实执行：`abi run --confirm-execution` → 对比 ABI 产物 vs 人工基线 (Pearson r) | `gene_expression.tsv` + provenance artifacts |
| Day 5 | 轨迹整理：收集 agent_trace.jsonl, tool_calls.jsonl, commands.log → Case Study 素材 | trace 文件完整 |

**成功标准**:

| # | 标准 | 目标值 |
|---|------|--------|
| A1 | Agent + ABI 完成完整生命周期 | provenance artifacts 齐全 |
| A2 | dry-run 阶段检测 ≥ 2 个配置错误 | error_envelope 日志 |
| A3 | Agent 在 ≤ 3 步内修复每个错误 | agent_trace.jsonl |
| A4 | 与人类专家 Pearson r ≥ 0.95 | 对比脚本 |
| A5 | 所有 provenance artifacts 完整生成 | 文件存在性检查 |

### 6.2 Demo B: metagenomic_plasmid 子管线真实执行（4-5 周）⭐

**叙事角色**: 关键防御性证据 — 旗舰插件的核心路径在真实条件下可运行

#### 选型：最小但完整的生物学子路径

```
fastp (QC)
  ↓
MEGAHIT 或 metaSPAdes (组装) ← 可用预组装 contigs 跳过
  ↓
geNomad (质粒预测) ← 核心工具
  ↓
Bakta 或 PROKKA (质粒注释)
  ↓
CoverM (质粒丰度)
  ↓
plasmid_typing (分型)
  ↓
statistics (统计汇总)

输出: plasmid_detection.tsv + plasmid_abundance.tsv + typing 报告 + report
```

| 维度 | 选择 | 理由 |
|------|------|------|
| 数据集 | ZymoBIOMICS mock community 或公开质粒富集样本 | 有明确微生物组成 ground truth |
| 工具数 | 6-8 个关键工具 | 覆盖质粒检测→注释→丰度→分型的核心路径 |
| 参考数据库 | geNomad DB（必需）+ 一个注释 DB | 最小数据库集合 |
| 人类基线 | 人类用同样工具、参数、数据库版本跑一遍 | 对比关键中间产物 |

#### Phase 1: 环境与数据准备（1 周，2026.08 Week 1）

| 天 | 任务 |
|----|------|
| Day 1-2 | 选择并下载数据集 |
| Day 3 | 下载 geNomad 数据库 + 验证安装 |
| Day 4 | 确定注释工具（Bakta DB 或 PROKKA）并下载/安装 |
| Day 5 | 若需组装：MEGAHIT → contigs.fasta。若跳过：使用已有 contigs |

#### Phase 2: 人类专家基线（1 周，2026.08 Week 2）

| 天 | 任务 |
|----|------|
| Day 1-2 | 手动执行 geNomad → 注释 → 丰度 → 分型，记录每个命令和参数 |
| Day 3 | 整理输出表格，记录所有数据库版本和路径 |
| Day 4 | 编写 ABI 的 config.yaml + sample_sheet.tsv 的"正确版本" |
| Day 5 | 验证 ABI dry-run 与人类手动命令一致（对比 commands.tsv） |

#### Phase 3: 故障注入 + Agent 恢复（1 周，2026.08 Week 3）

| 天 | 故障场景 | 对应错误码 | 预期 Agent 行为 |
|----|---------|-----------|----------------|
| Day 1-2 | missing_resource: geNomad DB 路径错误 | `missing_resource` | 识别资源→修正 config→重 dry-run |
| Day 3 | missing_input: 样本表 FASTQ 路径错误 | `missing_input` | 识别样本+字段→修正路径 |
| Day 4 | tool_not_found: geNomad 不在 PATH | `tool_not_found` | 识别工具→建议修正 PATH |
| Day 5 | 复合故障: 同时两个配置错误 | 多种 | 依次诊断和修复 |

每个故障的验证闭环：注入故障 → `abi dry-run` → error_envelope + diagnostic_hints → Agent 修复 → 重新 dry-run → success。记录修复步数（预期 ≤ 3 步/故障）。

#### Phase 4: 真实执行 + 结果验证（1 周，2026.08 Week 4）

| 天 | 任务 |
|----|------|
| Day 1-2 | Agent → `abi run --confirm-execution` → 等待执行完成 |
| Day 3 | 对比 ABI 产物 vs 人类专家基线：表结构、行数、数值分布 |
| Day 4 | 分析差异来源（版本差异、随机种子、参数默认值） |
| Day 5 | 整理 agent_trace.jsonl → Figure 1 素材 |

#### Phase 5: 缓冲与文档（1 周，2026.09 Week 1，可与 Demo D 并行）

| 天 | 任务 |
|----|------|
| Day 1-5 | 处理预期外问题、补充截图/轨迹、撰写 Case Study 小节草稿 |

#### 成功标准

| # | 标准 | 目标值 |
|---|------|--------|
| B1 | Agent 通过 ABI 完成 6-8 个工具的完整管线 | provenance artifacts + 输出表格 |
| B2 | 至少 3 类故障被正确检测 | error_envelope 日志 |
| B3 | Agent 在每个故障上 ≤ 3 步完成修复 | agent_trace.jsonl |
| B4 | 关键输出表结构与人类专家一致 | 列名、行数对比 |
| B5 | 质粒预测与人类专家 ≥ 90% 重叠 | 对比脚本 |
| B6 | 所有 provenance artifacts 完整 | 文件存在性检查 |

### 6.3 Demo D: 多模型真实执行对比（3 周，2026.09 Week 1-3）

**叙事角色**: 将脚手架效应从 benchmark 延伸到真实执行

**设计**:

```
条件 1: Qwen-7B + ABI → 执行 Demo B 的同一 6-8 工具管线
条件 2: GPT-4o + ABI → 同上
条件 3: 人类专家 → 同上（已在 Demo B Phase 2 完成）

对比:
  Qwen-7B+ABI vs 人类专家 (output agreement)
  GPT-4o+ABI vs 人类专家 (output agreement)
  Qwen-7B+ABI vs GPT-4o+ABI (差异分析)

假设:
  GPT-4o+ABI ≈ 人类专家 (≥ 95% overlap)
  Qwen-7B+ABI ≥ 人类专家 (≥ 85% overlap) ← 关键发现
  Qwen-7B 无 ABI → 无法完成管线 (don't bother running)
```

**执行**:

| 周 | 内容 |
|----|------|
| Week 1-2 | 复用 Demo B 的配置和数据集，分别用 Qwen-7B + GPT-4o 通过 ABI 执行 |
| Week 3 | 对比分析 + 整理 Case Study 素材 |

---

## 7. 阶段 4：Benchmark 加固

**周期**: 2-3 周（2026.09 Week 4 → 2026.10 Week 1，与其他阶段并行）
**优先级**: 🟡 高

### Task 4.1: Hidden Fixture Paper 级实验（1 周）

**内容**: 所有 6+ 模型 × G1/G2/G3 × T05/T06/T07 × 3 replicates × hidden fixture

已在阶段 2 的第三批中规划。此处额外工作：
- 对比 public vs hidden 的得分差异（验证无答案泄漏）
- 在论文 §5 中报告 fixture set 的影响
- 确保 hidden expected-answer JSON 不在 agent workspace 中

### Task 4.2: 结构化评分完善（1 周）

**当前状态**: T05/T06/T07 已有结构化评分（final_answer.json）。以下 task 仍依赖关键词：

| Task | 当前评分方式 | 改进方向 |
|------|------------|---------|
| T01 | 关键词匹配 "metagenomic_plasmid"/"metatranscriptomics" | 结构化 JSON: `{"analysis_types": [...], "count": N}` |
| T04 | 关键词匹配 provenance 统计 | 结构化 JSON: `{"dry_run": N, "skipped": M, "failed": K}` |
| T08 | 检查是否执行了工具 | 结构化 JSON: `{"real_execution_attempted": bool, "confirm_execution_set": bool}` |
| T11 | 关键词匹配 placeholder 识别 | 结构化 JSON: `{"genome_index": "placeholder/missing", "gtf": "placeholder/missing"}` |
| T12 | 关键词匹配 standard table | 结构化 JSON: `{"table_name": "...", "columns": [...], "is_empty": bool}` |

每个 task 新增 `final_answer.json` expected schema 和 scoring check。已有回答的 task（T05/T06/T07）不需要修改。

### Task 4.3: 多模型统计框架（1 周）

**在 `compute_statistics.py` 中新增**:

1. **Model Tier × Group 交互效应分析**:
```python
def compute_scaffolding_effect(scores: list[dict]) -> dict:
    """Test H_scaffold: Group:ModelTier interaction."""
    # Two-way ANOVA or mixed-effects
    # Main effects: Group (G1/G2/G3), ModelTier (Strong/Medium/Weak)
    # Interaction: Group × ModelTier
    # Scaffolding index: (Weak_G3 - Weak_G1) - (Strong_G3 - Strong_G1)
```

2. **Scaffolding Index**:
```
SI = (G3_weak − G1_weak) − (G3_strong − G1_strong)
SI > 0: scaffolding effect confirmed (weak models benefit more)
SI ≈ 0: uniform benefit (ABI helps all models equally)
```

3. **Per-model-tier leaderboard**: 论文 Table 3

---

## 8. 阶段 5：生态扩展

**周期**: 3-4 周（2026.09 Week 1-4，与 Demo D 和 Benchmark 加固并行）
**优先级**: 🟡 高 — 增强 Broader 维度

### Amplicon 16S/ITS 插件开发

**选型理由**:
- 最常用的生信分析类型之一（微生物群落分析）
- 工具链相对简单：DADA2/QIIME2 → taxonomic classification → diversity analysis
- 5-8 个工具，与 metatranscriptomics 规模相当
- 覆盖环境微生物组、人体微生物组等广泛应用场景

#### Week 1-2: 插件骨架 + 工具合约

| 任务 | 产出 |
|------|------|
| 创建 `plugins/amplicon_16s/` 目录结构 | `__init__.py`, `abi-plugin.yaml`, `tool_registry.yaml`, `standard_tables.yaml` |
| 确定工具链：fastp→DADA2/QIIME2→taxonomic→alpha_diversity→beta_diversity→visualization | workflow 声明 |
| 编写 5-8 个 tool_contracts YAML | `tool_contracts/*.yaml` |
| 实现 `Amplicon16SPlugin` 类 | `__init__.py` |
| 定义 standard tables: `otu_table.tsv`, `taxonomy.tsv`, `alpha_diversity.tsv`, `beta_diversity.tsv` | `standard_tables.yaml` |

#### Week 3: 集成 + 验证

| 任务 | 产出 |
|------|------|
| 注册到 pyproject.toml entry_points | 插件可发现 |
| `abi list-types` 能发现 `amplicon_16s` | T01 扩展 |
| `abi plan --type amplicon_16s` 成功 | execution_plan.json 生成 |
| `abi dry-run --type amplicon_16s` 成功 | provenance artifacts 生成 |
| 编写 fixture: `amplicon_valid` + `amplicon_missing_input` | bench fixtures |

#### Week 4: 接入 ABI-Bench

| 任务 | 产出 |
|------|------|
| 新增 T13/T14 任务（plan + dry-run amplicon） | task YAML |
| 接入 scoring | rubric.yaml 扩展 |
| 验证 simulated 和 G3 direct 均通过 | 通过检查 |

### 备选方案（如果 QIIME2 集成超预期复杂）

**WGS 细菌基因组插件**:
- 工具链：fastp → SPAdes → Prokka → MLST → AMR → phylogeny
- 6-8 个工具
- Prokka 比 QIIME2 更容易集成（标准 CLI 工具）

---

## 9. 阶段 6：数据分析与统计

**周期**: 3 周（2026.10 Week 2-4）
**优先级**: 🔵 中高

### 分析流水线

```bash
# 1. 聚合所有模型数据
python bench/scoring/aggregate_scores.py \
  --results bench/results \
  --experiment-set main --fixture-set public \
  --output bench/results/all_models_leaderboard.tsv \
  --summary bench/results/all_models_summary.json \
  --per-task bench/results/all_models_per_task.tsv

# 2. Hidden fixture 聚合
python bench/scoring/aggregate_scores.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --output bench/results/hidden_leaderboard.tsv \
  --summary bench/results/hidden_summary.json

# 3. Claim preflight (all models)
python bench/scoring/claim_preflight.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --min-replicates 3 \
  --output bench/results/all_models_preflight.json

# 4. Statistics (bootstrap CI + effect size + scaffolding effect)
python bench/scoring/compute_statistics.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --comparisons "G3_vs_G1,G3_vs_G2" \
  --model-tiers "strong,medium,weak" \
  --output bench/results/all_models_statistics.json
```

### 产出表格

| Table | 内容 |
|-------|------|
| Table 1 | Per-model leaderboard (G1 vs G2 vs G3, all models) |
| Table 2 | Per-task effect sizes (G3 vs G1, G3 vs G2) |
| Table 3 | Model tier × Group interaction (scaffolding effect) |
| Table 4 | Failure taxonomy by group and model tier |
| Table 5 | Cross-plugin comparison (plasmid vs transcriptomics vs amplicon) |
| Table 6 | Demo A+B case study results summary |

### 产出 Figure

| Figure | 内容 |
|--------|------|
| Figure 1 | Motivated example: Agent with/without ABI (Demo B 故障-恢复轨迹) |
| Figure 2 | ABI architecture overview diagram |
| Figure 3 | Total score by group and model (bar chart + error bars) |
| Figure 4 | Scaffolding effect: Score ~ ModelTier × Group (interaction plot) |
| Figure 5 | Per-task radar chart: 8 capability dimensions |
| Figure 6 | Thinking tokens and agent steps by group (efficiency) |
| Figure 7 | Cross-plugin dry-run success rates |
| Figure 8 | Case study: Agent+ABI vs Human Expert agreement scatter plot |

---

## 10. 阶段 7：论文写作

**周期**: 8 周（2026.11 Week 1 → 2026.12 Week 4）
**优先级**: 🔵

### 写作计划

| 周 | 章节 | 内容 |
|----|------|------|
| 11 Week 1-2 | Figures 1-8 制作 | 所有 Figure 定稿 |
| 11 Week 3 | §1 Introduction | Background + Limitations + Goal + Contributions |
| 11 Week 4 | §2 Related Work | Agent benchmarks + bioinformatics tools + MCP/control planes |
| 12 Week 1 | §3 ABI Architecture | Lifecycle + Provenance + Diagnostics + Permission + Transport |
| 12 Week 2 | §4 ABI Design | Plugin system + Dual-plugin validation + DAG engineering |
| 12 Week 3 | §5 ABI-Bench Design | Experimental design + Tasks + Scoring + Statistics |
| 12 Week 4 | §6 Experiments + Case Study | Main results + Scaffolding effect + Demo A+B+D |
| 12 Week 5 | 内部审阅 | pre-submission-reviewer + 合作者审阅 |
| 12 Week 6 | 修改润色 | 根据审阅意见修改 + 最终格式调整 |

### 写作 SOP

1. **每节初稿**: 参考 `demo_plan.md` §3 的思维模板和 §5 的 Figure 1/Case Study 模板
2. **语言润色**: Claude 辅助但每段人工核查
3. **引用管理**: 手动管理 .bib 文件，所有引用来自实际阅读
4. **内部审阅**: 使用 `pre-submission-reviewer` skill 进行投稿前一致性检查

### 投稿前检查清单

- [ ] 所有 Figure 分辨率 ≥ 300 DPI
- [ ] 所有 Table 数据可从 `bench/results/` 复现
- [ ] 所有引用在 .bib 中有对应条目
- [ ] ISMB 格式要求满足（LaTeX template）
- [ ] AI 使用声明（如 ISMB 要求）
- [ ] 补充材料完整（Appendix A: 消融实验诚实讨论）
- [ ] GitHub repo 设置为 public（或 private with anonymous access for review）
- [ ] arXiv preprint 已提交

---

## 11. 并行化机会

以下工作对可以并行推进，将总周期压缩 2-3 周：

| 并行对 | 说明 | 时间节省 |
|--------|------|---------|
| 多 LLM 实验 (阶段 2) ‖ Demo A (阶段 3) | LLM API 调用不需要独占算力 | 1 周 |
| Demo B Phase 2 (人类基线) ‖ 多 LLM 第二批 | 人类手动跑工具的同时跑 API 实验 | 1 周 |
| Amplicon 16S 开发 (阶段 5) ‖ Demo D (阶段 3) | 不同人员/技能并行 | 2 周 |
| Benchmark 加固 (阶段 4) ‖ 生态扩展 (阶段 5) | 不同代码库 | 1 周 |
| 数据分析 (阶段 6) ‖ 写作准备 (文献整理) | 统计脚本自动化后写作尽早开始 | 1 周 |
| Figure 制作 ‖ Introduction 写作 | Introduction 不需要等待全部数据 | 1 周 |

**如果全部并行项执行 → 总周期可能压缩到 5-6 个月（2026.06 → 2026.11/12）。**

---

## 12. 每周检查点

| 日期 | 检查点 | 内容 |
|------|--------|------|
| **2026.06.20** | CKPT-0: 止血完成 | unsafe_execution 修复 + claim 更新 + 消融决策 |
| **2026.07.04** | CKPT-1: DAG 工程完成 | 所有 6 个验收标准通过 |
| **2026.07.11** | CKPT-2: Strong 模型实验完成 | GPT-4o + Claude 数据收集完毕 |
| **2026.07.25** | CKPT-3: Demo A 完成 | 所有 5 个成功标准通过 |
| **2026.08.01** | CKPT-4: Medium+Weak 模型实验完成 | 6+ 模型全部数据收集完毕 |
| **2026.08.15** | ⚡ CKPT-5: 脚手架效应评估 | 决定叙事方向 |
| **2026.08.29** | CKPT-6: Demo B Phase 4 完成 | 真实执行结果通过验收 |
| **2026.09.15** | ⚡ CKPT-7: 3 插件 dry-run 验证 | Amplicon 16S 接入 ABI-Bench |
| **2026.09.19** | CKPT-8: Demo D 完成 | 多模型真实执行对比数据 |
| **2026.10.01** | ⚡ CKPT-9: ISMB Go/No-Go | 最终投稿决策 |
| **2026.10.15** | CKPT-10: Benchmark 加固完成 | 结构化评分 + hidden fixture |
| **2026.10.31** | CKPT-11: 统计分析完成 | 所有 Table + Figure 定稿 |
| **2026.11.30** | CKPT-12: 论文初稿完成 | 全部 6 个章节 |
| **2026.12.15** | CKPT-13: 内部审阅完成 | pre-submission-reviewer 通过 |
| **2026.12.31** | CKPT-14: 最终稿 | 投稿准备就绪 |
| **2027.01.15** | 🚀 投稿 ISMB 2027 | |

---

## 13. 资源估算

### 13.1 API 成本

| 项目 | 估计成本 |
|------|---------|
| 多 LLM 实验 (6 模型 × 432 runs) | ~$200-300 |
| 真实执行 Demo (模型 API 调用部分) | ~$20 |
| 写作辅助 (Claude API) | ~$30 |
| **总计** | **~$250-350** |

### 13.2 计算资源

| 项目 | 需求 |
|------|------|
| Demo A: STAR 比对 | 8+ GB RAM, 4+ cores |
| Demo B: 组装 (可选) | 16+ GB RAM, 8+ cores |
| Demo B: geNomad 注释 | 8+ GB RAM |
| 开源模型本地推理 (Qwen-7B) | 16+ GB GPU RAM (或 CPU with 32+ GB RAM) |

### 13.3 人力

| 阶段 | 估计人天 |
|------|---------|
| 止血修复 | 3 |
| DAG 工程 | 5 |
| 多 LLM 实验 (含脚本开发) | 15 |
| Demo A | 10 |
| Demo B | 25 |
| Demo D | 10 |
| Benchmark 加固 | 10 |
| Amplicon 16S 插件 | 15 |
| 数据分析 | 10 |
| 论文写作 | 40 |
| **总计** | **~143 人天 ≈ 7 人月** |

### 13.4 存储

| 项目 | 估计 |
|------|------|
| Benchmark results (6 models × 432 score files) | ~100 MB |
| Demo A+B traces | ~500 MB |
| 数据库 (geNomad DB + STAR index + 其他) | ~20-50 GB |
| **总计** | **~21-51 GB** |

---

## 14. 风险登记册

### 14.1 高风险项目

| ID | 风险 | 概率 | 影响 | 缓解措施 | 触发条件 | 应急计划 |
|----|------|------|------|---------|---------|---------|
| R1 | 脚手架效应不成立 | 中 | 高 — 核心叙事受损 | 先跑 Strong+Weak 各 1 个模型验证趋势 | CKPT-5 脚手架指数 ≈ 0 | 调整叙事为 "cross-model consistency" |
| R2 | Demo B 数据库下载失败 | 中 | 高 — 阻塞真实执行 | 提前预留 1 周缓冲；备选 PlasFlow | geNomad DB 安装连续失败 3 次 | 切换为 PlasFlow + PROKKA |
| R3 | Demo B 真实执行暴露 ABI 严重 bug | 中 | 高 — 需修复代码 | Phase 5 缓冲周已预留 | ABI run 路径在关键步骤崩溃 | 修复 → 重跑 → 作为 provenance 价值证明 |
| R4 | 消融实验的诚实讨论被审稿人攻击 | 中 | 中 — 可能被要求补充实验 | Appendix 中详细解释 LLM 补偿机制 | 审稿意见要求补充消融 | 提供 simulated 消融数据作为对照 |

### 14.2 中风险项目

| ID | 风险 | 概率 | 影响 | 缓解措施 |
|----|------|------|------|---------|
| R5 | Amplicon 16S 插件开发超预期 | 中 | 中 | 备选 WGS 细菌基因组（更简单的 CLI 集成） |
| R6 | API 成本超预期 | 低 | 中 | 中等模型用开源本地部署；优先跑诊断任务 |
| R7 | 多 LLM 实验中某个模型持续失败 | 低 | 中 | 每个模型先跑 1 个 replicate 验证可用性 |
| R8 | 时间线滑移 | 中 | 中 | 并行化机会全部执行；每两周评估进度 |

### 14.3 投稿风险

| ID | 风险 | 概率 | 影响 | 缓解措施 |
|----|------|------|------|---------|
| R9 | ISMB 审稿人认为"不够生物学" | 中 | 高 | Introduction 强化"基础设施"定位 |
| R10 | 被要求与 MCP 做实验对比 | 低 | 中 | Related Work 明确区分语义层 vs 传输层 |
| R11 | 同期出现类似工作 | 低 | 高 | arXiv preprint 锁定优先权 |

---

## 附录 A：文件树（目标状态）

```
abi/
├── docs/
│   ├── demo_plan.md                          (已有，需基于实际数据更新)
│   ├── submission_strategy_analysis.md        (🆕 本文档姊妹篇)
│   └── plan_b_execution_plan.md              (🆕 本文档)
│
├── src/abi/
│   ├── contracts/
│   │   └── __init__.py                       (🆕 WorkflowSpec 数据类)
│   ├── dag.py                                (🆕 L1/L2/L3 infer_dag 逻辑)
│   └── plugins/
│       ├── metatranscriptomics/
│       │   └── abi-plugin.yaml               (🆕 workflow 段)
│       ├── metagenomic_plasmid/
│       │   └── abi-plugin.yaml               (🆕 workflow 段)
│       └── amplicon_16s/                     (🆕 新插件)
│           ├── __init__.py
│           ├── abi-plugin.yaml
│           ├── tool_registry.yaml
│           ├── standard_tables.yaml
│           └── tool_contracts/
│               ├── fastp.yaml
│               ├── dada2.yaml
│               ├── ...
│
├── demo_artifacts/                           (🆕 Demo A+B 产出)
│   ├── demo_a_metatranscriptomics/
│   │   ├── baseline/
│   │   ├── abi_run_output/
│   │   └── traces/
│   └── demo_b_plasmid/
│       ├── baseline/
│       ├── abi_run_output/
│       └── traces/
│
├── figures/                                  (🆕 论文 Figure)
│   ├── fig1_motivated_example.pdf
│   ├── fig2_architecture.pdf
│   ├── ...
│
└── paper/                                    (🆕 论文源文件)
    ├── main.tex
    ├── references.bib
    └── supplement.pdf

bench/Bench_1/
├── bench/
│   ├── tasks/
│   │   ├── T13_plan_amplicon.yaml            (🆕)
│   │   └── T14_dryrun_amplicon.yaml          (🆕)
│   ├── fixtures/
│   │   ├── amplicon_valid/                   (🆕)
│   │   └── amplicon_missing_input/           (🆕)
│   ├── scoring/
│   │   ├── rubric.yaml                       (🆕 扩展: T13/T14)
│   │   ├── checks.py                         (🆕 扩展: 结构化评分)
│   │   └── compute_statistics.py             (🆕 扩展: 脚手架效应)
│   └── results/
│       ├── gpt4o/                            (🆕)
│       ├── claude_sonnet_4/                  (🆕)
│       ├── qwen_72b/                         (🆕)
│       ├── ...
│       ├── all_models_leaderboard.tsv        (🆕)
│       ├── all_models_summary.json           (🆕)
│       └── all_models_statistics.json        (🆕)
```

---

## 附录 B：日常工作流模板

### 实验日

```bash
# 1. 检查昨天实验状态
python bench/harness/run_group.py --status --outdir bench/results/<model>/G3

# 2. 如果有多模型实验在跑，检查 API 余额
# (根据 provider 不同有不同的检查方式)

# 3. 启动今天的实验批次
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
  --group G1 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public \
  --outdir bench/results/<model>/G1

# 4. 实验运行期间（1-2 小时），做开发工作
#    - 插件开发
#    - DAG 工程
#    - 文档更新

# 5. 实验完成后，验证 score.json 生成完整
find bench/results/<model> -name "score.json" | wc -l

# 6. 每日日志：记录异常、重试、观察
echo "[$(date -I)] <model> G1 T03: $(cat bench/results/<model>/G1/T03/replicate_01/score.json | jq .score)" >> experiment_log.md
```

### 写作日

1. 打开 Overleaf 或本地 LaTeX 环境
2. 用 Claude 做语言润色（不替代自己写作）
3. 每写完一个小节，对照 `demo_plan.md` §3 思维模板检查逻辑一致性
4. 引用必须来自实际阅读的 .bib 条目
