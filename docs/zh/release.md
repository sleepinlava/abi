# 发布指南

`abi-agent` 是本仓库唯一发布的 PyPI 分发包。

## 发布前检查

打标签或发布前，先运行统一发布检查入口：

```bash
scripts/release_check.sh
```

推送发布候选前，确认 `CHANGELOG.md` 中存在与 `pyproject.toml` 的
`project.version` 完全一致的版本小节；CI 会通过
`scripts/check_release_identity.py` 强制检查这一点。该脚本也要求 Claude Code
和 Codex plugin manifest 的版本与 `project.version` 完全一致。

版本必须同时不存在于 PyPI 和远端 Git tag。tag 与 PyPI 版本都是不可变发布身份，推送后不能移动或复用。如果 tag 指向与包元数据不一致的提交，应放弃该版本并继续递增。`1.5.4` 因 tag 对应 `1.5.3` 元数据而未发布，下一有效版本为 `1.5.5`。

脚本默认会在 `/tmp` 下创建 POSIX 临时目录，并在测试前导出
`TMPDIR`、`TMP` 和 `TEMP`。这样可以避免 WSL/Windows 挂载的临时目录破坏
权限敏感测试的 `chmod` 语义。可通过 `ABI_RELEASE_TMPDIR` 或
`ABI_RELEASE_TMP_ROOT` 覆盖位置。

该脚本运行与 CI 一致的质量门：

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
python -m pytest tests/ src/abi/sciplot/tests/ -v --tb=short \
  --strict-markers -m "not requires_tools" --capture=no \
  --cov=src/abi --cov-branch --cov-report=term-missing:skip-covered \
  --cov-report=xml --cov-report=json:coverage.json --cov-fail-under=75
python scripts/check_module_coverage.py --coverage coverage.json

python -m build
abi query --type metagenomic_plasmid --what stages
```

构建 wheel 后，使用 `[mcp]` extra 安装，并在可行的情况下于干净环境中对
已安装命令进行冒烟测试：

```bash
abi list-types
abi query --type metagenomic_plasmid --what stages
abi query --type rnaseq_expression --what tools
autoplasm --help
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
abi doctor-agent --type metatranscriptomics
abi export-tools --type metatranscriptomics --format json
abi install-skills --target /tmp/abi-smoke-skills
abi query --type amplicon_16s --what stages
abi query --type wgs_bacteria --what tools
abi query --type easymetagenome --what stages
abi dry-run --type viral_viwrap --config examples/config_minimal.yaml --profile dry_run 2>/dev/null || echo "ViWrap smoke skipped (requires external CLI)"
abi-mcp --help 2>/dev/null || python -m abi.mcp.server --help 2>/dev/null || true
for platform in claude-code opencode codex; do
  abi agent install "$platform" --scope project --project-dir "/tmp/abi-release-agent-$platform"
  abi agent doctor "$platform" --scope project --project-dir "/tmp/abi-release-agent-$platform"
done
```

执行时应将干净 wheel 环境的 `bin` 目录加入 `PATH`，因为 doctor 会校验已安装的
`abi-mcp` 入口。`integrations/` 属于发布输入，必须同时进入两种分发包和每个
Docker `/app` 上下文；该目录变化必须经过 Docker workflow。

## GitHub Actions

- `ci.yml` 运行 lint、格式检查、mypy、测试和构建检查。
- `docker.yml` 在相关 PR 上构建并冒烟测试插件镜像；仅 tag 或获准的手动发布推送生成带 provenance、SBOM 的镜像，PR 本地 load 明确关闭 attestation。发布镜像默认多架构，但 RNA-seq 在其 R/DESeq2 环境通过原生 arm64 构建与冒烟测试前仅发布 `linux/amd64`。
- `release.yml` 构建分发包、为 `v*` tag 创建 GitHub Release，并发出 published event。
- `publish-pypi.yml` 下载 Release 原始产物，并通过 PyPI Trusted Publishing 发布。PyPI OIDC 身份绑定该文件名，因此它是必需 workflow。

`.github/workflows/` 不保留可选 bot 或重复发布 workflow；必需集合严格为 `ci.yml`、`docker.yml`、`release.yml` 和 `publish-pypi.yml`。

唯一正常的自动发布链为：

```text
已验证 master 提交 → v<version> tag → 可复用 CI 质量门
→ 构建并冒烟测试 wheel/sdist → 携带原始产物的 GitHub Release
→ 顶层 release.published event 启动 publish-pypi.yml
→ 下载 Release 产物 → PyPI Trusted Publishing
```

不能把 `publish-pypi.yml` 作为 reusable workflow 调用：PyPI 不支持父 workflow 的 OIDC Build Config URI。`release.published` 是唯一自动发布触发器。恢复操作使用 `workflow_dispatch` 并输入已有 GitHub Release tag，不能本地重新构建。重命名 publisher 前必须先更新 PyPI Trusted Publisher 配置。

合并 packaging 或容器变更前，必须看到默认 sdist→wheel 构建和所有适用 Docker 矩阵 job 成功。PR Docker 门禁必须覆盖构建、本地 load 和容器内 `abi list-types`，仅 BuildKit 初始化或 Conda 求解成功不算完成。plasmid 镜像因体积原因不进入自动 PR 构建；影响它的容器发布必须先通过手动 workflow dispatch 验证。

## 发布后验证

发布完成后，核对 GitHub Release 与 PyPI 版本、Trusted Publishing provenance 和文件哈希；在干净环境安装 wheel，并运行 `abi list-types`、`autoplasm --help` 和代表性插件 dry-run。容器 tag 需要从 GHCR 拉取并执行 `abi list-types`。发布交接中记录 Release、PyPI、release workflow、publish job 和 container workflow 链接。
