# ABI 投稿策略与增量分析

> 基于 idea-evaluator + tech-paper-template + vibe-research-workflow 三框架交叉分析
>
> **日期**：2026-06-17
> **状态**：综合评估完成，待执行
> **相关文档**：`demo_plan.md`（投稿总体计划）、`plan_b_execution_plan.md`（方案 B 执行计划）

---

## 目录

1. [项目资产全景](#1-项目资产全景)
2. [idea-evaluator 重新评估（基于实际实验数据）](#2-idea-evaluator-重新评估)
3. [投稿策略：三层梯队](#3-投稿策略三层梯队)
4. [四项增量分析](#4-四项增量分析)
5. [组合效应：各层级投稿可行性](#5-组合效应各层级投稿可行性)
6. [推荐路线：方案 B](#6-推荐路线方案-b)
7. [风险与应对](#7-风险与应对)
8. [最终判断](#8-最终判断)

---

## 1. 项目资产全景

### 1.1 两个仓库一个故事

```
abi/ (ABI 系统, 32,500 行 Python)       bench/Bench_1/ (ABI-Bench, 已有真实 LLM 数据)
    │                                         │
    ├── 71 工具合约, 84 节点 DAG               ├── G3=96.87, G1=89.93, G2=86.00 ✓
    ├── 7+ LLM provider 工具描述器             ├── G3−G1=6.94, G3−G2=10.87
    ├── MCP/CLI/HTTP 三传输层                  ├── 消融: A1=96.0, A3=96.8, A4=97.8 ≈ G3
    ├── 14 码诊断 + 三级权限 + 完整溯源         ├── G3 unsafe_execution_rate=0.156
    ├── 双插件跨域验证（质粒 + 转录组）          ├── Bootstrap CI 稳定 (n=3 main / n=15 paper)
    ├── 论文骨架已通过 4 项自洽性检查            ├── primary_claim_supported=true (需修正)
    └── 投稿计划完整（ISMB 2027 为主目标）       └── 完整 harness/scoring/statistics 管线
```

### 1.2 核心优势

| 资产 | 强度 | 说明 |
|------|------|------|
| **Broader（跨域通用性）** | ★★★★★ | 双插件 + 7 LLM provider + 3 传输层，是论文最强的维度 |
| **工程完整性** | ★★★★★ | 从 CLI 到 MCP 到 HTTP Job Service，从 scoring 到 statistics，全部落地 |
| **方法论严谨性** | ★★★★ | 吸收 7 个标杆基准的方法论（GAIA/SWE-bench/AgentBench/StableToolBench/BioCoder/LAB-Bench/BixBench） |
| **Higher（定量改善）** | ★★★★ | ABI 确有改善（bootstrap CI 下限 > 0），但效应量中等（delta≈7-11） |
| **Stronger（鲁棒性）** | ★★★ | 消融实验失败降低了这个维度的分数 |

### 1.3 核心弱点

| 弱点 | 严重程度 | 影响 |
|------|---------|------|
| 效应量低于预设阈值（6.94 vs 20） | 高 | 主 claim 需从 "significant" 降级为 "moderate" |
| 消融实验失败（A1/A3/A4 ≈ G3） | 高 | 无法证明组件级贡献，消融需降级到 Appendix |
| G3 unsafe_execution ≠ 0 | 高 | 与自身安全 claim 矛盾，需修复或诚实报告 |
| 仅有单一模型 (DeepSeek v4-pro) | 中 | 审稿人会质疑结论是否依赖模型选择 |
| 仅有 dry-run 评估 | 中 | 没有真实执行证明 `abi run` 路径可用 |
| 仅有 2 个插件 | 低 | 对 ISMB 足够，对 NeurIPS D&B 偏少 |

---

## 2. idea-evaluator 重新评估

### 2.1 论文类型定位

**Mixed — New Problem/Setting + Cross-domain Technique**

- **New Problem/Setting**: 确立"agent-operability of bioinformatics workflows"作为一级设计关注点——这不是已有问题的新解法，而是一个新的 framing
- **Cross-domain Technique**: 将数据库系统的控制平面（plan→dry-run→execute 分离）、编译器的错误分类体系、软件工程的 provenance tracking 移植到 Agent-生物信息学接口

### 2.2 致命缺陷审计（基于 2026-06-17 实验数据）

| # | 缺陷 | 严重程度 | 状态 | 防御 |
|---|------|----------|------|------|
| 1 | 消融实验失败 — A1/A3/A4 ≈ G3 | MAJOR | 🆕 | 降级到 Appendix，诚实讨论 LLM 补偿效应 |
| 2 | 效应量低于预设阈值 — delta=6.94 vs 预设 20 | MAJOR | 🆕 | 论文报告原始阈值和实际值，claim 从 "significant" 降级为 "moderate" |
| 3 | G3 unsafe_execution ≠ 0 — 违反安全 claim | MAJOR | 🆕 | 修复代码或诚实报告限制 |
| 4 | 缺少多模型验证 — 仅 DeepSeek v4-pro | MAJOR | 需补充 | 方案 B 中补充 6+ 模型 |
| 5 | 与 MCP/通用工具调用框架的差异化 | MAJOR | 持续 | 定位为"语义控制平面"而非"传输协议" |

**零 CRITICAL 缺陷。五个 MAJOR 缺陷，其中 3 个是新发现的（基于实际实验数据）。**

### 2.3 五维度雷达

| 维度 | 评分 | 证据 | 提升路径 |
|------|------|------|---------|
| **Broader**（跨域通用性） | **8** | 双插件 + 7 LLM provider + MCP/CLI/HTTP 三传输层 | 增加第 3 个插件 → 9；5+ 插件 → 10 |
| **Higher**（有效性提升） | **7** | G3 优于 G1/G2，bootstrap CI 下限 > 0 | 多模型验证 + 脚手架效应 → 8 |
| **Stronger**（鲁棒性） | **6** | 消融实验失败，无法证明组件级贡献 | 重新设计消融或降级叙事 |
| **Faster**（效率） | **5** | thinking tokens 减少 ~40%，但效应量小 | 次要辅助指标 |
| **Cheaper**（成本） | **5** | 权限门控防止未授权计算 | 次要辅助指标 |

**主导叙事**: Broader(8) + Higher(7) = 跨域通用性 + 定量改善

### 2.4 范式转变探测

| 探测维度 | 答案 | 核心理由 |
|---------|------|---------|
| 第一性原理 | **Yes** | 挑战"暴露 CLI 就够了"的假设——Agent 需要的是语义控制平面而非原始工具访问 |
| 房间里的大象 | **Partial** | Agent 操作生信工具的不可靠性是真实问题，但社区尚未形成共识 |
| 技术周期 | **Yes** | LLM Agent 能力 2024-2025 年才成熟，此前不可能实现 |
| 汉明法则 | **Partial** | 若脚手架效应成立（弱模型+ABI ≈ 强模型−ABI），则 Yes。当前效应量不足以单独改变领域优先级 |

**总分: 5/8 — Disruptive potential: possible**

### 2.5 Verdict

**Accept with Revisions**

五个 MAJOR 缺陷但零 CRITICAL。修正实验设计 + 补充多模型验证 + 诚实化叙事 → 可达 Strong Accept。

---

## 3. 投稿策略：三层梯队

### 3.1 投稿层级总览

| Tier | Venue | 类型 | 难度 | 当前可行性 | 方案 B 后可行性 |
|------|-------|------|------|----------|---------------|
| **Tier 1A** | NeurIPS D&B | ML 会议 | 极高 | ❌ 不够 | ⚠️ 40-50% |
| **Tier 1B** | ISMB/ECCB | 生信会议 | 高 | ⚠️ 需要 Demo | ✅ 60-70% |
| **Tier 2A** | Bioinformatics (Oxford) | 生信期刊 (IF~6) | 中高 | ✅ 接近 | ✅ 85%+ |
| **Tier 2B** | PLOS Comp Bio | 计算生物学期刊 | 中 | ✅ 可投 | ✅ 90%+ |
| **Tier 3** | BMC Bioinformatics | 生信期刊 | 中低 | ✅ 保底 | ✅ 95%+ |

### 3.2 各 Venue 匹配度分析

#### ISMB/ECCB（首要目标）

| 因素 | 评估 |
|------|------|
| **领域匹配度** | ★★★★★ 生信社区理解 sample sheet/FASTQ/database 这些领域对象 |
| **双插件优势** | ★★★★★ 质粒+转录组在生信社区天然引起共鸣 |
| **效应量要求** | ★★★★ 不如 ML 会议苛刻，"一个方法让 agent 少犯 30% 错误"有实际意义 |
| **竞争程度** | ★★★ 中等。ISMB 有专门的 methodology/tool 类别 |
| **截止日期** | ≈2027 年 1 月（7 个月余量） |
| **接受率** | ~20-25%（全文） |

#### Bioinformatics (Oxford)（备选）

| 因素 | 评估 |
|------|------|
| **领域匹配度** | ★★★★★ 生信顶刊之一 |
| **方法论友好度** | ★★★★★ 对 provenance/reproducibility 叙事高度友好 |
| **审稿周期** | ★★★★ 滚动投稿，2-4 月 |
| **IF** | ~6 |
| **接受率** | ~15-20% |

#### PLOS Comp Bio（保底）

| 因素 | 评估 |
|------|------|
| **基础设施/工具友好度** | ★★★★★ 非常欢迎 benchmark/methodology |
| **效应量要求** | ★★★★★ 更看重 methodology soundness |
| **审稿友善度** | ★★★★★ 审稿标准相对宽松 |
| **接受率** | ~30-40% |

### 3.3 投稿决策树

```
2026.06-08  修复 MAJOR 缺陷 + Demo A + Demo B + 多 LLM 实验
2026.09-12  写作
                │
2027.01     投稿 ISMB 2027
                ├── Accept → 🎉
                ├── Major Revision → 修改，2 月重投
                └── Reject → 2027.03 转投 Bioinformatics (Oxford)
                                 ├── Accept → 🎉
                                 └── Reject → 2027.06 转投 PLOS Comp Bio
```

### 3.4 并行发表

| 发表物 | 时间 | 投入 |
|--------|------|------|
| **JOSS 软件论文** | 与主论文同步 | 1-2 周。满足 JOSS 标准（PyPI + CI + 文档完整） |
| **arXiv preprint** | 投稿 ISMB 前 | 锁定优先权，获取社区反馈 |

---

## 4. 四项增量分析

### 4.1 多 LLM + 不同参数量对照

**核心叙事机会："Scaffolding Effect"（脚手架效应）**

假设实验结果符合预期——弱模型从 ABI 中获益更大：

```
                    G1 (README+Shell)    G3 (ABI Control Layer)     Δ
GPT-4o                   92                    97                  +5
Claude Sonnet 4          90                    96                  +6
DeepSeek v4-pro          89                    97                  +8
Qwen-72B                 72                    88                 +16  ←
DeepSeek-v3-lite         55                    78                 +23  ←
Qwen-7B                  38                    71                 +33  ← 脚手架效应
```

如果这个图成立，论文叙事从"ABI 有帮助"变为：

> **"ABI enables weaker LLMs to perform bioinformatics workflows at a level comparable to much stronger models operating without structured guidance."**

**实验规模**：

| 模型层级 | 模型数 | MVP 任务数 | Replicates | 总 Run | 估计 API 成本 |
|---------|--------|-----------|-----------|--------|-------------|
| Strong (GPT-4o, Claude Sonnet, DeepSeek-v4) | 3 | 8 | 3 | 72 | ~$150 |
| Medium (GPT-4o-mini, Haiku, Qwen-72B) | 3 | 8 | 3 | 72 | ~$50 |
| Weak (Qwen-7B, DeepSeek-lite, LLaMA-8B) | 3 | 8 | 3 | 72 | ~$30 |
| **总计** | **9** | | | **216** | **~$230** |

**边际价值**: ★★★★★（四项增量中最高）

### 4.2 改进 Benchmark 测试

| 改进项 | 边际价值 | 投入 | 优先级 |
|--------|---------|------|--------|
| Hidden fixture paper 级实验 | ★★★★★ | 1 周 | 🔴 最高 |
| 修复 unsafe_execution 逻辑一致性 | ★★★★★ | 1-2 天 | 🔴 最高 |
| T01/T04/T08/T11/T12 关键词评分 → 结构化评分 | ★★★★ | 1-2 周 | 🟡 高 |
| 多模型统计方法（交互效应分析） | ★★★★ | 1 周 | 🟡 高 |
| 增加 2-3 个诊断任务变体 | ★★★ | 1 周 | 🟢 中 |

**边际价值**: ★★★★

### 4.3 真实任务执行测试

`demo_plan.md` 中已详细规划 Demo A+B。在此基础增加：

**🆕 Demo D：多模型真实执行对比（3 周）**
```
用 1 strong (GPT-4o) + 1 weak (Qwen-7B) 模型分别通过 ABI 执行同一管线
对比: weak+ABI vs strong+ABI vs strong+manual (人类专家)
→ 证明: weak+ABI 能达到 strong+manual 的 90%+ 结果质量
```

**边际价值**: ★★★★★（四项增量中最关键，堵住最大漏洞）

### 4.4 分析工作流生态

| 插件 | 工具数 | 开发时间 | 叙事价值 | 优先级 |
|------|--------|---------|---------|--------|
| Amplicon 16S/ITS | 5-8 | 3-4 周 | ★★★★★ 最常用生信分析 | 🔴 |
| WGS 细菌基因组 | 6-10 | 4-5 周 | ★★★★★ 临床微生物学 | 🔴 |
| RNA-seq (标准) | 4-6 | 2-3 周 | ★★★★ 最常见转录组 | 🟡 |
| scRNA-seq | 6-8 | 5-6 周 | ★★★ | 🟢 |
| Variant Calling | 4-6 | 3-4 周 | ★★★ | 🟢 |

**方案 B 目标**: 3 个插件（metagenomic_plasmid + metatranscriptomics + Amplicon 16S）

**边际价值**: ★★★★

---

## 5. 组合效应：各层级投稿可行性

### 方案 A：最小增量（+2-3 月）

```
多 LLM:        3 个模型 (strong + medium + weak)，每层 1 个
Benchmark:     修复 unsafe_execution + hidden fixture + 结构化评分完善
真实执行:      Demo A + Demo B（按 demo_plan.md 原计划）
生态:          保持 2 个插件

总时间: 从当前 +3 个月 → 2026.09 可开始写作
投稿: ISMB 2027 (2027.01 截止)
把握: ISMB 70-80%
叙事: "ABI moderately improves agent reliability across analysis types and LLM scales"
```

### 方案 B：中等增量（+4-5 月）⭐ 推荐

```
多 LLM:        6+ 个模型 (strong×3 + medium×2 + weak×2)
Benchmark:     修复 + hidden fixture + 结构化评分 + 多模型统计
真实执行:      Demo A + Demo B + Demo D（多模型真实执行对比）
生态:          3 个插件 (新增 Amplicon 16S)

总时间: 从当前 +5 个月 → 2026.11 可开始写作
投稿: ISMB 2027 (时间紧张但可行) 或 Bioinformatics (滚动投稿)
把握: ISMB 60-70%, Bioinformatics 85%+
叙事: "Scaffolding effect: ABI enables weaker models to match stronger models without ABI"
```

### 方案 C：完全增量（+8-10 月）

```
多 LLM:        9+ 个模型
Benchmark:     公共 leaderboard (HF Space) + 社区贡献指南 + 外部 submission
真实执行:      3 插件 × 2 数据集各一次端到端
生态:          5+ 个插件

额外: 与至少 1 个 alternative agent-bioinformatics 方案的系统对比
      跨时间稳定性验证
      GitHub stars > 200 + external contributors

总时间: +10 个月 → 2027.04
投稿: NeurIPS 2027 D&B (2027.05-06 截止)
把握: 50-60%
```

---

## 6. 推荐路线：方案 B

### 6.1 选择理由

1. **ISMB 2027 时间窗口刚好**：5 个月执行 + 2 个月写作 + 2 个月缓冲 = 2027.01 截止
2. **脚手架效应是 ISMB 审稿人无法忽视的 finding**：生信社区非常关心"能否用便宜模型做可靠分析"
3. **3 插件覆盖生信日常 60%+ 场景**：质粒/耐药基因 + 转录组功能分析 + 微生物群落——有说服力
4. **真实执行堵住了最大漏洞**：没有审稿人能攻击"你从来没跑过真实执行"
5. **不过度承诺**：不需要公共 leaderboard 或社区采纳，在可控范围内交付

### 6.2 方案 B 成功后的论文叙事

**四大贡献**：

| # | 贡献 | 对应章节 |
|---|------|---------|
| C1 | 确立 **agent-operability** 作为 AI 时代科学软件的一级设计关注点 | §1-2 |
| C2 | 提出 **ABI**：四支柱语义控制平面（生命周期 + 溯源 + 诊断 + 权限） | §3-4 |
| C3 | 设计 **ABI-Bench**：首个严格隔离控制层贡献的受控基准测试 | §5 |
| C4 | 实验验证：跨 6+ 模型、3 插件、含真实执行案例研究 | §6 |

**核心发现（Expected Key Findings）**：

1. **Main effect**: ABI moderately improves agent operability (G3−G1=7-11, bootstrap CI > 0)
2. **Scaffolding effect**: ABI benefit increases as model capability decreases (significant model tier × group interaction)
3. **Cross-plugin portability**: Same ABI interface works across 3 analysis types without plugin-specific adaptation
4. **Real execution viability**: Agent+ABI completes 8-tool plasmid pipeline with results within 90% of human expert
5. **Efficiency**: ABI reduces agent thinking tokens by ~40% and agent steps by ~20%

---

## 7. 风险与应对

### 7.1 技术风险

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 脚手架效应不成立（所有模型从 ABI 获益相近） | 中 | 中 | 调整叙事为"cross-model consistency of ABI benefit"——这仍然有价值 |
| Demo B 数据库下载/安装失败 | 中 | 高 | geNomad DB 有备选 (PlasFlow 无外部 DB)，预留 1 周缓冲 |
| 新插件开发超预期（QIIME2 集成复杂） | 中 | 中 | 备选：WGS 细菌基因组（SPAdes+Prokka 更直接） |
| API 成本超预期 | 低 | 中 | 优先跑诊断任务（差异化最大），中等模型用开源本地部署 |
| 真实执行暴露 ABI bug | 中 | 高 | 修复本身就是 provenance+diagnostics 价值的证明 |

### 7.2 投稿风险

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| ISMB 审稿人认为"不够生物学" | 中 | 高 | Introduction 强化"基础设施"定位；引用 ISMB 以往工具类论文 |
| 审稿人攻击"只在 1 个模型上做了 3 个 replicates" | 低（方案 B 解决了） | 高 | 方案 B 有 7 个模型 × 3 replicates |
| 被要求与 MCP 做实验对比 | 低 | 中 | Related Work 明确区分：MCP=传输协议，ABI=语义控制平面 |
| 同期出现类似工作 | 低 | 高 | arXiv preprint 锁定优先权 |

### 7.3 范围蔓延风险

**v0.1 绝不做的**：

- ❌ 不增加第二个新的分析类型（方案 B 只增 1 个，共 3 个）
- ❌ 不部署公共 leaderboard（放到 v0.2）
- ❌ 不追求社区采纳（放到 v0.2）
- ❌ 不跑全部 43 个工具的真实执行（Demo B 严格 6-8 个）
- ❌ 不追求 NeurIPS D&B（除非 ISMB 被拒且有足够时间）

---

## 8. 最终判断

**当前论文的最强叙事不应该是"We built a better agent"，而应该是：**

> *"We show that a structured semantic control plane can amplify LLM agent capability in bioinformatics — enough that a 7B-parameter model with ABI approaches the performance of a frontier model without it. This has immediate practical implications for making AI-assisted bioinformatics accessible, affordable, and auditable."*

**方案 B 把这个叙事从"可能"变为"可证明"。**

**投稿路径**：
- **主攻**: ISMB 2027（≈2027.01 截止）
- **备选**: Bioinformatics (Oxford)（滚动投稿）
- **保底**: PLOS Computational Biology（滚动投稿）

**并行发表**：JOSS 软件论文

---

## 附录：相关文件索引

| 文件 | 内容 |
|------|------|
| `demo_plan.md` | 投稿总体计划（2026-06-14，部分内容需基于实际实验数据更新） |
| `plan_b_execution_plan.md` | 方案 B 详细执行计划（本文档的姊妹篇） |
| `workflow_reproducibility_analysis.md` | 工作流可复现性分析与缺陷分类 |
| `workflow_validation.md` | 科学生物学验证计划 |
| `../bench/Bench_1/Plan.md` | ABI-Bench 执行计划（1321 行完整规格） |
| `../bench/Bench_1/NEXT_DEVELOPMENT_PLAN.md` | ABI-Bench 阶段开发记录（P1-P6） |
| `../bench/Bench_1/bench/results/` | 评分输出（leaderboard, summary, statistics） |
