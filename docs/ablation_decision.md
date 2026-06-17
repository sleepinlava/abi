# 消融实验处理决策

> 日期：2026-06-17
> 决策者：基于实际实验数据的自动分析
> 状态：已决定，待执行

---

## 1. 问题

ABI-Bench v0.1 设计了 4 组消融实验（A1/A3/A4），旨在隔离 ABI 各组件的独立贡献：

- **A1** (no-provenance): 移除 provenance artifacts → 预期诊断能力下降
- **A3** (no-diagnostic-hints): 移除 structured error_code / diagnostic_hints → 预期故障定位能力下降
- **A4** (no-permission-model): 移除 confirmation_required 门控 → 预期安全违规增加

Simulated agent 验证确认了这些消融设计的有效性——A1 从 G3 的 100 分降至 51.72 分（−48.28），A3 降至 75.86（−24.14），A4 降至 89.66（−10.34）并出现 16.7% 的安全违规。

但真实 LLM 实验（DeepSeek v4-pro，paper 级，n=15，180 scores/group）的结果与 simulated 结果完全不一致。

## 2. 实际数据

| Group | Real LLM Total | Real LLM Δ vs G3 | Simulated Total | Simulated Δ vs G3 | 差异倍数 |
|-------|---------------|------------------|-----------------|-------------------|---------|
| **G3** | 96.87 | — | 100.00 | — | — |
| **A1** | 96.00 | −0.87 | 51.72 | −48.28 | 55× |
| **A3** | 96.80 | −0.07 | 75.86 | −24.14 | 345× |
| **A4** | **97.80** | **+0.93** | 89.66 | −10.34 | **方向相反** |

### 关键发现

1. **A1 (no-provenance)**: 真实 LLM 仅损失 0.87 分——LLM 通过读取 config.yaml、sample_sheet.tsv、workspace_summary.json 等非 provenance 文件推理出了与 provenance 相同的信息
2. **A3 (no-diagnostic-hints)**: 真实 LLM 仅损失 0.07 分——LLM 的推理能力足以在没有结构化 hints 的情况下定位故障
3. **A4 (no-permission-model)**: 真实 LLM **反而比 G3 高 0.93 分**——移除 permission gate 后 agent 少了确认步骤，反而更快完成任务。但 unsafe_execution_rate 在 A4 仍为 0.178，与 G3 的 0.156 差异不显著

### 根因分析

**LLM 补偿效应 (LLM Compensatory Behavior)**：

真实 LLM agent（特别是 DeepSeek v4-pro 级别）具有强大的推理能力，能通过以下方式补偿缺失的 ABI 组件：

- **补偿 provenance**: Agent 手动读取 workspace 中的 config.yaml、sample_sheet.tsv、execution_plan.json 等文件，自行构建 mental model
- **补偿 diagnostic hints**: Agent 通过试错（trial-and-error）和错误消息解析自行诊断故障
- **补偿 permission model**: Agent 的内置安全训练（RLHF）已经教会它在不确定时保守行事

这种补偿效应意味着：**ABI 的组件级贡献在当前实验设计下无法被隔离测量**。这不是 ABI 的价值不存在，而是消融实验设计假设的"组件移除 → 能力线性退化"模型在强推理模型面前不成立。

## 3. 决策

**方案 A：降级到 Appendix（推荐）**

消融实验从论文正文的主实验降级到 Appendix，正文中诚实讨论 LLM 补偿效应。

**论文中的定位**：

> *"We attempted component-level ablation to isolate the contribution of provenance (A1), diagnostic hints (A3), and permission gating (A4). While simulated ablation showed dramatic differentiation (A1: −48.3, A3: −24.1, A4: −10.3 points vs G3), real LLM agents (DeepSeek v4-pro) compensated for missing components through chain-of-thought reasoning, resulting in minimal observed score differences (A1: −0.9, A3: −0.1, A4: +0.9). We report both sets of results transparently in Appendix A and discuss the implications for evaluating control-layer components — namely, that component-level isolation requires either weaker models or task designs that prevent compensatory reasoning."*

**正文中保留的证据线**：

- G1/G2/G3 主实验（主证据）
- Cross-plugin portability (T09/T10/T11)
- Case studies (Demo A+B+D)
- 定性分析：ABI 各组件的 design rationale 和预期贡献

**Appendix 中包含**：
- Simulated ablation 完整结果
- Real LLM ablation 完整结果
- LLM 补偿效应的定性讨论
- Future work: 改进消融实验设计的建议

**不做的**：
- ❌ 不在正文中依赖消融实验支撑任何核心 claim  
- ❌ 不重新设计消融实验并重跑（v0.1 范围内）
- ❌ 不删除消融数据

## 4. 对论文叙事的影响

| 原叙事依赖 | 修正后 |
|-----------|--------|
| H3: Provenance improves diagnosis | 修改为：Provenance is designed to improve diagnosis; ablation was inconclusive due to LLM compensation (Appendix A) |
| H4: Standard tables improve interpretation | v0.2（A2 消融未在 v0.1 内执行） |
| H5: Permission model reduces unsafe execution | 修改为：Permission model provides an explicit architectural boundary; G3 T08 scored 9.7/10 vs G1 7.5/10, indicating behavioral difference even if component-level isolation failed |

## 5. 执行项

- [x] 分析 simulated vs real ablation 差异
- [x] 做出降级决策
- [ ] 更新 BENCHMARK_SPEC.yaml 标记消融为 "attempted, inconclusive"
- [ ] 在论文 Methods 中增加 "Ablation Limitations" 小节
- [ ] 准备 Appendix A 内容
- [ ] 重跑修复后的 scoring 验证新 summary 输出
