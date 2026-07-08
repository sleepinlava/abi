# 发布指南

`abi-agent` 是本仓库唯一发布的 PyPI 分发包。

## 发布前检查

打标签或发布前，先运行统一发布检查入口：

```bash
scripts/release_check.sh
```

推送发布候选前，确认 `CHANGELOG.md` 中存在与 `pyproject.toml` 的
`project.version` 完全一致的版本小节；CI 会通过
`scripts/check_release_identity.py` 强制检查这一点。

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

构建 wheel 后，在可行的情况下于干净环境中对已安装命令进行冒烟测试：

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
```

## GitHub Actions

- `ci.yml` 运行 lint、格式检查、mypy、测试和构建检查。
- `release.yml` 构建分发包并为 `v*` 标签创建 GitHub Release。
- `publish-pypi.yml` 通过 PyPI Trusted Publishing 发布 release 产物。
- `opencode.yml` 要求在 GitHub Actions Secrets 中配置
  `DEEPSEEK_API_KEY`；不要把服务商 API key 直接写入 workflow YAML。

发布工作流不应直接上传到 PyPI；发布操作由专用的 PyPI 工作流在 GitHub Release 发布后处理。
