# ABI 工作流可复现性 — 下一步 HPC 验证计划

**日期**: 2026-06-16
**状态**: 本地 IDE 修复阶段完成，HPC 验证阶段待启动

---

## 当前状态

```
306 tests passed, 0 failed
ruff: All checks passed

本地修复完成度:  15/15 (100%)  ← 本地 IDE 全流程缺陷已全部修复
HPC 待验证:      12 个缺陷      ← 需要真实工具执行/大文件/多节点
```

## 修复成果一览

| 维度 | 修复前 | 修复后 | 关键改动 |
|---|---|---|---|
| **受约束** | 85% | 90% | `SafeFormatDict` strict 模式, `abi contract-lint` 命令 |
| **可验证** | 80% | 90% | 校验和原子写入, 实际参数记录, 符号链接追踪 |
| **可复现** | 25% | 40% | 浮点容差, 版本捕获, 列序确定性 |

## HPC 环境需求

| 资源 | 最低规格 |
|---|---|
| 计算节点 | 16+ cores, 64GB+ RAM |
| 存储 | 500GB+ 可用空间 |
| 共享文件系统 | NFSv4 (2+ 节点) |
| Conda | 完整 67 工具环境 |
| 测试数据 | ZymoBIOMICS 或标准 mock 群落 |

## 执行顺序

### 阶段 A: 本地开发（可提前开始，无需 HPC）
1. **B15+B16+B17**: 输入格式校验采样 + gzip 透明读取 + 流式校验 → 预计 3 天
   - 文件: `src/abi/tools.py` (`_validate_input_content`)
   - 测试: 本地 10MB 测试文件即可验证逻辑正确性

### 阶段 B: HPC 批量验证（需要 HPC 到位）
2. **B5 验证**: 67 个工具 `capture_version()` 批量采集 → 半天
3. **B15/B16/B17 验证**: 大文件 (>50GB) 性能 + OOM 测试 → 半天
4. **B6 验证**: >50GB 文件流式 SHA256 性能 → 半天
5. **B11 生成**: 完整 metagenomic_plasmid 管线 golden dataset → 2 天
6. **B8 验证**: 多节点 TOCTOU 模拟 → 半天
7. **B26 验证**: NFS 原子写入 → 半天

### 阶段 C: CI 集成（HPC 验证后）
8. **B12**: 裁切 golden dataset 到 <1GB CI 可用 → 1 天
9. **B24**: 多样本 partial failure 语义测试 → 1 天

## HPC 验证清单

执行时按此清单逐项验证：

- [ ] B5: `tool_versions.tsv` version 列非空率 > 90%
- [ ] B15: FASTQ 格式校验采样 ≥ 1000 行
- [ ] B16: gzip 文件透明解压后校验通过
- [ ] B17: >50GB 文件校验内存 < 512MB
- [ ] B6: >50GB 文件 SHA256 不阻塞进度显示
- [ ] B11: Golden dataset 完整管线验证通过
- [ ] B8: TOCTOU 检测在多节点上触发
- [ ] B26: NFS 原子写入无半截文件
- [ ] B12: CI 数据集 < 1GB, 运行 < 30 分钟
- [ ] B24: Partial failure 状态正确标记
- [ ] B1+B3: version_command 失败/超时不阻断流程
- [ ] 回归: 306 个现有测试全部通过
