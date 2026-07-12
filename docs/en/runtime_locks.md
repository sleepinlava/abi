# Release-ready runtime locks

`abi lock-runtime` snapshots the current Conda environments, registered tools,
databases, and host runtime. A normal invocation is an audit snapshot and may
contain gaps. Use `--strict` only for a release candidate.

The canonical cloud resource layout has one top-level root:

```text
/root/autodl-tmp/resources/
├── autoplasm/              # plasmid, metagenome, amplicon, and EasyMeta data
├── star_index/             # RNA-seq STAR index
├── NC_000913.3.gtf         # RNA-seq annotation
└── viwrap/                 # ViWrap databases
```

Create a production candidate with the full database profile:

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

Strict validation rejects missing or undeclared Conda environments, omitted or
failed package snapshots, unresolved required/default-enabled tools, non-ready
workflow-level resources, non-ready resources belonging to those tools, and a
missing or dirty Git identity. Resource rows outside this release scope are
written with `release_required: false`. Add `--require-all-tools` when the release
claims every optional registered capability; it promotes those tools and their
resources into the release scope. It is invalid without `--strict`.

The runtime lock contains both global audit counts and an explicit `release`
block. Use `release.blocking_missing_tools` and `release.not_ready_resources` as
the authoritative certification summary; global missing counts can include
optional tools and resources outside the selected analysis scope.

On the ABI cloud development machine, use the idempotent release helper:

```bash
scripts/cloud/prepare_release_lock.sh
```

The helper uses `ABI_RUNTIME_RESOURCE_ROOT` for the canonical top-level root.
Do not substitute the bootstrap variable `ABI_RESOURCE_ROOT`, which denotes the
`autoplasm/` database directory in the older download scripts.

The helper establishes the canonical resource links, builds in a staging
directory, validates the candidate, writes SHA-256 checksums, and atomically
publishes an immutable
version-and-commit-qualified directory under `/root/autodl-tmp/runtime-locks`.
It refuses to replace existing resource paths. Repeated runs verify the existing
checksum manifest and succeed without changing the published lock.

The helper currently certifies the six provisioned cloud workflows and excludes
`viral_viwrap`. ViWrap requires its own multi-environment installation and
database bundle; include it only after those resources have been provisioned and
validated explicitly with `--type viral_viwrap`.
