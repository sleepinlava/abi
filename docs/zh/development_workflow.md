# ABI 全流程开发规范

本文定义从需求进入到发布完成的统一开发流程。目标是让每次变更都可追踪、可复现、可审查、可回滚，并持续维护 ABI 的“厚核心、薄传输、清洁插件”架构。

## 1. 需求与设计

1. 写清问题、用户可观察行为、验收标准和非目标。
2. 确认归属：通用生命周期、权限、诊断和溯源属于 Core；CLI、MCP、HTTP 和 provider 只做适配；生物学选择、解析和报告解释属于插件。
3. 对兼容性、数据格式、运行环境、安全或发布有影响时，在实现前记录设计决定和迁移方案。
4. 将大变更拆为可独立验证的纵向切片，不把无关重构混入功能或缺陷修复。

## 2. 分支与工作区

- 从最新 `master` 创建主题分支，推荐 `feat/`、`fix/`、`docs/` 或 `chore/` 前缀。
- 开工前运行 `git status --short`，保留并避开其他开发者未提交的修改。
- 禁止提交 `.key`、令牌、数据库、运行结果、缓存和本地环境文件。
- 依赖和工具环境以 `pyproject.toml`、`environments.yaml` 与 `envs/*.yml` 为准，不能只修本机环境。

## 3. 实现规则

- 面向 Python 3.10–3.13，公共 API 必须有类型标注；使用四空格和 100 字符行宽。
- 修改最小的正确边界，保持 Core、transport 和 plugin 职责分离。
- 行为变更必须带回归测试；错误路径、边界输入和兼容行为与正常路径同等重要。
- 插件声明、DAG、工具注册、schema、报告元数据和 Python 入口必须同步更新。
- 修改 `environments.yaml` 后重新生成并审查 `envs/*.yml`。Docker 上下文必须包含 `docker/`、所需环境 YAML、`integrations/`、插件定义和运行脚本。
- 用户可见行为、配置或接口变化应同步更新中英文文档；不记录无法由命令验证的状态数字。

## 4. 分层验证

先运行最快且最相关的检查，失败时在当前层修复，再扩大范围。

### Python 与核心逻辑

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/unit/test_<feature>.py -q
pytest tests/ -v --tb=short -m "not requires_tools"
pytest tests/ src/abi/sciplot/tests/ --cov=src/abi --cov-branch --cov-fail-under=75
```

### 插件与工作流

```bash
abi contract-lint --type <analysis_type> --strict
abi dry-run --type <analysis_type> --outdir /tmp/abi-dry-run \
  --log-dir /tmp/abi-dry-run-log --no-check-files --no-progress
```

工具依赖型测试标记为 `smoke` 和/或 `requires_tools`，在匹配的 Conda 环境或专用执行机运行。不得为了通过普通 CI 而静默删除真实工具验证。

### Docker

```bash
pytest tests/unit/test_docker_configuration.py -q
docker compose -f docker/docker-compose.yml config --quiet
docker build -f docker/Dockerfile.amplicon -t abi-amplicon:latest .
docker run --rm abi-amplicon:latest list-types
```

至少构建一个受影响的代表镜像；环境定义变化时构建所有受影响镜像。自动 CI 不构建约 15 GB 的 plasmid 镜像，须通过手动 workflow 验证。Dockerfile 中每个 `COPY` 源都应存在且不能被 `.dockerignore` 排除；`pyproject.toml` 强制纳入 wheel 的文件（尤其是 `environments.yaml` 和 `integrations/`）必须同时进入 sdist 和每个 Docker `/app` 构建上下文。修改 `integrations/**` 必须触发 Docker workflow。

PR 的非推送构建使用单平台、`load: true` 和稳定的 `abi-<plugin>:latest` 标签，以便随后执行 `abi list-types`。provenance 与 SBOM 会产生 manifest list，不能与本地 Docker exporter 的 load 模式同时启用，因此只允许在 registry push 时生成。`docker/.condarc` 中 `conda-forge`、`bioconda` 使用 `custom_channels`；`defaults` 必须使用指向 `pkgs/main`、`pkgs/r` 的 `default_channels`。修改镜像地址时先验证 repodata 端点返回成功。

registry 推送默认生成 `linux/amd64,linux/arm64` 多架构镜像；RNA-seq 暂时仅生成 `linux/amd64`，因为 R/DESeq2 环境在 QEMU arm64 下会出现 `Exec format error`。只有原生 arm64 构建及容器内 `abi list-types` 冒烟测试均成功后，才可恢复该架构。

### 文档与包

```bash
bash docs/build_docs.sh
python scripts/check_release_identity.py
python -m build
python -m twine check dist/*
tar -tf dist/abi_agent-*.tar.gz | grep environments.yaml
```

发布变更还要在干净虚拟环境使用 `[mcp]` extra 安装 wheel，运行 `abi list-types`、`autoplasm --help`、所有内置插件的 dry-run，以及 Claude Code、OpenCode、Codex 三个平台的 `abi agent install`/`doctor`。wheel 环境的 `bin` 目录必须在 `PATH` 中，doctor 必须成功初始化 safe MCP server。Claude Code 与 Codex plugin manifest 的版本必须和 `project.version` 一致。

## 5. 提交与 Pull Request

- 使用简洁祈使句和 Conventional Commit 范围，如 `fix: preserve Docker build inputs`。
- 每个提交只表达一个可审查意图；提交前检查密钥、生成物和调试输出。
- PR 说明根因、方案、兼容性或配置影响、关联 issue，以及实际运行的验证命令与结果。
- 无法运行的检查必须写明原因和残余风险，不能用“应该通过”替代证据。
- 报告、文档或图形变更附生成物或截图；CI 全绿且审查意见关闭后方可合并。

## 6. CI 失败处理

1. 记录失败 check、运行链接和最小错误片段，区分 GitHub Actions 与外部检查。
2. 优先本地复现并定位根因，确认失败是否与当前差异相关。
3. 添加能捕获根因的回归测试，再实施聚焦修复；禁止只重跑来掩盖确定性失败。
4. 按“聚焦检查 → 完整质量门”复验，再查看远端 check。
5. 对网络、平台、缓存或第三方服务偶发失败，记录证据、重试策略和残余风险。
6. Docker 矩阵应逐层排查：工作流 exporter、镜像源/环境求解、包安装、镜像导出、容器 smoke test；修复前一层后必须继续等待真实构建完成，不能把“不再快速失败”视为通过。

## 7. 发布与回滚

1. 确认版本、tag、包元数据、changelog 以及 Claude Code/Codex plugin manifest 一致。
2. 质量门通过后生成 wheel 和 sdist，执行 `twine check` 与独立 wheel smoke test。
3. 发布 GitHub Release 后再由受保护环境发布 PyPI 和容器镜像，不能从未验证的本地构建直接发布。
4. 发布后验证 PyPI 安装、CLI 入口、文档站点和容器拉取/启动。
5. 出现回归时提交可审查的修复或 revert，并记录影响范围；不改写共享分支历史。

## 8. 完成定义

工作只有在实现和回归测试完成、相关分层验证通过、配置与中英文文档同步、PR 证据完整、CI 通过且发布影响已处理后才算完成。无法完成的项目必须在交付说明中列为未验证项和残余风险。
