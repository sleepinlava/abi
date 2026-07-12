# 可发布的运行时锁

`abi lock-runtime` 会记录当前 Conda 环境、已注册工具、数据库和主机运行时。
普通调用是允许包含缺口的审计快照；只有发布候选才应使用 `--strict`。

云端统一采用一个顶层资源根：

```text
/root/autodl-tmp/resources/
├── autoplasm/              # 质粒、宏基因组、Amplicon 和 EasyMeta 数据
├── star_index/             # RNA-seq STAR 索引
├── NC_000913.3.gtf         # RNA-seq 注释
└── viwrap/                 # ViWrap 数据库
```

使用完整数据库 profile 生成生产候选：

```bash
abi lock-runtime \
  --output-dir /root/autodl-tmp/runtime-locks/candidate \
  --prefix abi-production \
  --mamba-root /root/autodl-tmp/.mamba \
  --resource-root /root/autodl-tmp/resources \
  --conda-executable /root/autodl-tmp/miniconda3/bin/conda \
  --db-profile full \
  --strict
```

严格验收会拒绝缺失或未声明的 Conda 环境、缺失或失败的包清单、未解析的
required/default-enabled 工具、工作流级资源及这些工具对应的非就绪资源，以及
缺失或 dirty 的 Git 身份。发布范围外的资源行会明确记录
`release_required: false`。如果发布版本声称支持所有可选注册工具，再增加
`--require-all-tools`，把这些工具及其资源提升到发布范围；该参数必须与
`--strict` 一起使用。

在 ABI 云端开发机上使用幂等发布助手：

```bash
scripts/cloud/prepare_release_lock.sh
```

该助手使用 `ABI_RUNTIME_RESOURCE_ROOT` 表示统一顶层资源根。不要用旧下载脚本中的
`ABI_RESOURCE_ROOT` 替代；后者表示 `autoplasm/` 数据库目录。

该脚本会建立统一资源链接、在 staging 目录生成并严格验收候选、写入
SHA-256，最后原子发布到
`/root/autodl-tmp/runtime-locks` 下带版本和 commit 的不可变目录。脚本不会覆盖
已有资源路径。重复运行会验证已有 SHA-256，并在不修改正式 lock 的情况下成功。

该助手当前认证云端已经部署的六类流程，不包含 `viral_viwrap`。ViWrap 需要独立的
多环境安装和数据库包；完成这些资源的部署与验证后，才能通过显式
`--type viral_viwrap` 将其纳入正式锁。
