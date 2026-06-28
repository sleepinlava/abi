# ABI Cloud Bootstrap

Rebuild the full ABI project environment and download all required databases on a
generic Linux cloud host. The bootstrap is split into three stages so you can run
them independently, resume after a failure, and verify the result.

## Quick start

```bash
# 1. Clone the repo (or copy it to the cloud host)
git clone <repo-url> abi && cd abi

# 2. Install all 18 conda environments + ABI Python package + R/DESeq2
bash scripts/cloud/01_envs.sh

# 3. Download all auto-fetchable databases (~200 GB; see disk requirements)
bash scripts/cloud/02_databases.sh

# 4. Verify everything is ready
bash scripts/cloud/03_verify.sh
```

## Disk requirements

| Component | Size |
|-----------|------|
| Conda environments (18) | ~15–20 GB |
| Databases (Tier-1, all plugins) | ~180–220 GB |
| **Total** | **~200–240 GB** |

`02_databases.sh` prechecks free space and exits early if < 250 GB is available.
Attach a data disk and point `ABI_RESOURCE_ROOT` at it:

```bash
export ABI_RESOURCE_ROOT=/data/abi_dbs
export ABI_MAMBA_ROOT=/data/.mamba
```

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ABI_MAMBA_ROOT` | `<repo>/.mamba` | Conda/mamba env root |
| `ABI_RESOURCE_ROOT` | `<repo>/resources/autoplasm` | Database root |
| `ABI_LOG_DIR` | `<repo>/logs/cloud` | Log + sentinel directory |
| `ABI_RESOURCE_TIMEOUT_SECONDS` | `86400` (24h) | Per-database download timeout |

## Stage scripts

### `01_envs.sh` — Conda environments

Installs micromamba (if no mamba/conda found), regenerates `envs/*.yml` from
`environments.yaml`, creates all 18 environments, installs the ABI package
(`pip install -e ".[dev,report,mcp]"`), and sets up the `rnaseq` env + DESeq2.

```bash
bash scripts/cloud/01_envs.sh --dry-run                      # preview
bash scripts/cloud/01_envs.sh --env autoplasm-base,stats      # subset only
bash scripts/cloud/01_envs.sh --mamba-root /data/.mamba       # custom root
```

### `02_databases.sh` — Databases

Downloads Tier-1 (auto-fetchable) databases via `abi setup-resources` for all 7
plugins. Tier-2 manual databases (CARD, COPLA, abricate, blast, plasme, plasx,
plasmidhostfinder, easymetagenome host/humann, viral_viwrap db_dir, organism-
specific STAR indexes) are written to `logs/cloud/manual_databases_required.txt`
with step-by-step fetch instructions.

```bash
bash scripts/cloud/02_databases.sh --plugin metagenomic_plasmid   # one plugin
bash scripts/cloud/02_databases.sh --tier 1                        # auto only
bash scripts/cloud/02_databases.sh --dry-run
```

### `03_verify.sh` — Verification

Runs `abi check-resources` per plugin, checks environment directories, reports
disk usage, and writes a machine-readable JSON summary to `logs/cloud/`.

```bash
bash scripts/cloud/03_verify.sh --json   # emit only JSON to stdout
```

Exit codes: `0` = all ok, `2` = partial (manual DBs pending), `1` = fatal
(environments missing).

## Files

```
scripts/cloud/
├── libcommon.sh        # shared helpers: logging, atomic download, sentinels
├── 01_envs.sh          # stage 1 — conda environments
├── 02_databases.sh     # stage 2 — database download
├── 03_verify.sh        # stage 3 — verification
└── README.cloud.md     # this file
```

## Resuming after failure

Each stage writes a sentinel to `logs/cloud/` (`.cloud_envs_done`,
`.cloud_databases_done`) on success. Re-running a stage is idempotent: installed
environments are updated, already-downloaded databases are skipped. To force a
re-download of a single database, remove its directory under
`ABI_RESOURCE_ROOT` and re-run stage 2.

---

# ABI 云端重建引导（中文）

在通用 Linux 云主机上重建完整的 ABI 项目环境并下载全部所需数据库。引导
流程分为三个阶段，可独立运行、断点续跑、并验证结果。

## 快速开始

```bash
git clone <仓库地址> abi && cd abi
bash scripts/cloud/01_envs.sh        # 安装 18 个 conda 环境 + ABI + R/DESeq2
bash scripts/cloud/02_databases.sh   # 下载全量数据库（约 200 GB）
bash scripts/cloud/03_verify.sh      # 校验
```

## 磁盘要求

conda 环境约 15–20 GB，数据库约 180–220 GB，**共需约 200–240 GB**。
数据盘挂载后用环境变量指向：

```bash
export ABI_RESOURCE_ROOT=/data/abi_dbs
export ABI_MAMBA_ROOT=/data/.mamba
```

## 配置变量

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `ABI_MAMBA_ROOT` | `<repo>/.mamba` | conda 环境根目录 |
| `ABI_RESOURCE_ROOT` | `<repo>/resources/autoplasm` | 数据库根目录 |
| `ABI_LOG_DIR` | `<repo>/logs/cloud` | 日志与哨兵目录 |
| `ABI_RESOURCE_TIMEOUT_SECONDS` | `86400`（24小时） | 单库下载超时 |

## 断点续跑

每个阶段成功后在 `logs/cloud/` 写入哨兵。重跑是幂等的：已装环境会更新，
已下载数据库会跳过。如需重新下载单个数据库，删除其在
`ABI_RESOURCE_ROOT` 下的目录后重跑阶段 2 即可。
