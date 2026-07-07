# 发布指南

`abi-agent` 是本仓库唯一发布的 PyPI 分发包。

## 发布前检查

打标签或发布前，先运行统一发布检查入口：

```bash
scripts/release_check.sh
```

该脚本运行与 CI 一致的质量门：

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ --cov=src/abi --cov-fail-under=75 --cov-report=term-missing:skip-covered -q --tb=short

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
abi export-openai-tools --type metatranscriptomics --format json
abi install-skills --target /tmp/abi-smoke-skills
abi-mcp --help 2>/dev/null || python -m abi.mcp.server --help 2>/dev/null || true
```

## GitHub Actions

- `ci.yml` 运行 lint、格式检查、mypy、测试和构建检查。
- `release.yml` 构建分发包并为 `v*` 标签创建 GitHub Release。
- `publish-pypi.yml` 通过 PyPI Trusted Publishing 发布 release 产物。

发布工作流不应直接上传到 PyPI；发布操作由专用的 PyPI 工作流在 GitHub Release 发布后处理。
