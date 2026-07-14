# ViWrap ABI Plugin

The `viwrap_compat` workflow preset treats ViWrap 1.3.1 as a managed external
CLI. ABI validates input, environments, databases, output-path policy, and disk
capacity before execution;
it then records commands and logs and normalizes stable files under
`08_ViWrap_summary_outdir/`. ABI does not rewrite or vendor ViWrap internals.

Use the unified ABI entry points; plugin Python helpers are implementation
details.

```bash
abi plan --type viral_viwrap --config viwrap.yaml
abi check --type viral_viwrap --config viwrap.yaml --engine hpc
abi run --type viral_viwrap --config viwrap.yaml --engine hpc \
  --scheduler slurm --partition compute --confirm-execution
```

`resources.conda_env_dir` points to the shared ViWrap environment collection.
ABI launches an explicit `executable` when configured, otherwise it uses
`<conda_env_dir>/ViWrap/bin/ViWrap`. ViWrap itself remains a single black-box
external step surrounded by ABI validation, parsing, and reporting.
The compatibility helper `run_viwrap(config)` delegates to the same canonical
ABI DAG. It preserves the requested `out_dir` and legacy return/log fields while
adding `abi_result_dir` and `abi_outputs` references to the standard ABI bundle.
The `artifact_manifest` entry in `abi_outputs` points to a versioned manifest
that inventories raw ViWrap files and links them to ABI standard tables and row
counts. The legacy `artifact_manifest.json` is an exact alias of that canonical
manifest.
When `outdir` is omitted, that bundle is written to the configured `log_dir` or
to `<out_dir>.abi_logs`. Legacy `viwrap.*` log aliases always remain in
`log_dir`, including when the standard ABI bundle uses a separate `outdir`.

The future `viral_native` preset is intentionally rejected until its individual
tool stages and result-parity gates are implemented.
