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

`resources.conda_env_dir` points to the shared ViWrap environment collection;
ABI launches `<conda_env_dir>/ViWrap/bin/ViWrap`. ViWrap itself remains a single
black-box external step surrounded by ABI validation, parsing, and reporting.
The future `viral_native` preset is intentionally rejected until its individual
tool stages and result-parity gates are implemented.
