# ABI 全流程开发规范

所有行为、插件、传输、文档、打包、Docker 或发布变更都应遵循本流程。目标是建立一条从验收标准到已验证产物的可追踪路径。

## 1. 定义行为与验收标准

修改代码前，先明确：

- 需要改变的用户或系统行为；
- 输入、输出、错误和兼容性预期；
- 该行为所属的架构边界；
- 能证明变更的最小测试；
- 受影响的文档、插件、运行时和发布表面。

不要把无关重构与行为变更混在一起。如果新行为依赖重构，先单独完成并验证结构调整。

## 2. 选择所属边界

| 关注点 | 归属位置 |
| --- | --- |
| Schema、权限、诊断、溯源、契约、标准表格 | ABI 核心层 |
| CLI、MCP、HTTP、模型工具描述 | 薄传输适配器 |
| 生物学选择、工作流步骤、解析器、断言 | 分析插件 |
| 工具到 Conda 环境的映射 | `environments.yaml` 和生成的 `envs/*.yml` |
| Docker 与 CI 打包 | Dockerfile、workflow、包元数据和构建上下文 |
| 科研图形行为 | `abi.sciplot` Schema、渲染器、质检和测试 |

始终遵守“核心层要厚、传输层要薄、插件要干净”的架构原则。

## 3. 实现最小且完整的变更

- 公共 API 应保持类型明确和兼容，除非本次变更明确包含迁移方案。
- 优先使用声明式 DAG、契约、Schema 和表格元数据，避免插件特有样板代码。
- 传输适配器不得包含业务逻辑和生物学逻辑。
- 保持路径、顺序、诊断和序列化输出的确定性。
- 修改 Conda 映射时先更新 `environments.yaml`，再同步生成的 YAML。
- 不要在可复用插件定义中写入特定机器的资源路径。

## 4. 添加回归测试

| 测试层级 | 适用场景 |
| --- | --- |
| `tests/unit/` | 快速、隔离的行为测试和回归测试 |
| `tests/integration/` | 跨组件契约以及适配器与核心层交互 |
| `tests/smoke/` | 已安装工具、真实运行时或代表性工作流 |
| `src/abi/sciplot/tests/` | 图形 Schema、渲染、导出和质检行为 |

测试文件命名为 `test_<feature>.py`，测试函数命名为 `test_<behavior>`。真实工具测试使用 `smoke` 和/或 `requires_tools` 标记。

每个行为修复都应有一个修复前失败、修复后通过的回归测试。断言必须验证用户可见结果，不能只证明函数没有抛出异常。

## 5. 运行与变更风险匹配的质量门禁

### Python 或核心逻辑变更

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/unit/test_affected_feature.py -q
pytest tests/ -v --tb=short
```

完成聚焦单元测试后，再运行受影响的集成测试。仓库 CI 覆盖率门禁为 75%，项目策略要求总覆盖率至少保持在 60%。

### 插件变更

```bash
abi contract-lint --type <analysis_type> --strict
abi plan --type <analysis_type> --config <config.yaml> --sample-sheet <samples.tsv>
abi dry-run --type <analysis_type> --config <config.yaml> --sample-sheet <samples.tsv>
pytest tests/smoke/ -m "smoke and not requires_tools" -q
```

同时运行插件契约、解析器、结果验证测试；工具可用时，还应运行相关真实工具 smoke 或 benchmark。

### Docker、包或 CI 变更

把 CI workflow、Dockerfile、`.dockerignore`、`pyproject.toml`、`environments.yaml` 和 `envs/*.yml` 视为同一个发布表面。

```bash
pytest tests/unit/test_docker_configuration.py -q
docker compose -f docker/docker-compose.yml config --quiet
python -m build
python -m twine check dist/*
```

构建一个代表性镜像，并在镜像内运行 `abi list-types`。默认 sdist 到 wheel 的构建路径必须成功，因为强制进入 wheel 的文件也必须存在于 sdist 和 Docker 上下文中。

### 文档变更

```bash
bash docs/build_docs.sh
```

保持中英文导航、术语、命令和行为说明一致。图形或报告变更需要视觉审查时，应提供截图或生成产物。

### 发布变更

打标签前，更新 `project.version`，并在 `CHANGELOG.md` 添加完全一致的版本标题。随后运行完整 CI、包检查、干净 wheel smoke 和发布身份校验。

不得复用或移动已经发布或远程可见的版本标签。Trusted Publishing 流程和发布后验证详见[发布指南](release.md)。

## 6. 验证运行时与数据契约

执行行为发生变化时，验证完整链路：

1. 计划中的输入和输出路径是确定的。
2. 工具命令使用已注册的可执行程序和环境映射。
3. 实际输出能够解析到计划契约。
4. 校验和与断言被正确记录。
5. 标准表格具有预期 Schema 和行标识。
6. 报告和图形只使用已发布、已验证的结果。

正式发布运行时必须使用严格锁。普通运行时锁只是审计快照，不是发布产物。

## 7. 保持文档和示例可执行

- 优先提供可以从仓库根目录复制执行的命令。
- 明确标记占位路径，不要把 dry-run fixture 描述成生产配置。
- 链接到负责该行为的深入文档，避免重复不稳定的实现细节。
- 公共工作流、命令、配置或策略变化时同步更新中英文。
- 修改快速开始示例后，实际运行对应的 plan 和 dry-run。

## 8. 准备提交与 Pull Request

提交标题使用简洁的祈使句，并带有 `feat:`、`fix:` 或 `docs:` 等范围前缀。每个提交保持聚焦且便于审查。

Pull Request 应说明：

- 用户可见的问题和解决方案；
- 受影响的架构与兼容性边界；
- 验证命令及结果；
- 关联 issue 和迁移说明；
- 未能执行的检查及剩余风险；
- 报告、文档或图形变更所需的截图与产物。

## 9. 完成定义

满足以下条件后，变更才算完成：

- 验收标准已经实现；
- 正确测试层级具有回归覆盖；
- 聚焦且与风险匹配的质量门禁通过；
- 生成环境和构建输入保持同步；
- 中英文文档保持一致；
- 运行时、结果和兼容性风险已经说明；
- Pull Request 记录了准确的命令和结果。

更多内容请参考[组件与架构](components_and_architecture.md)、[开发指南](development.md)、[插件开发指南](plugin_development_guide.md)和[测试指南](testing.md)。
