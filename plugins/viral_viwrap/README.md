# ViWrap ABI Plugin

This plugin treats ViWrap 1.3.1 as a managed external CLI. ABI validates input,
environments, databases, output-path policy, and disk capacity before execution;
it then records commands and logs and normalizes stable files under
`08_ViWrap_summary_outdir/`. ABI does not rewrite or vendor ViWrap internals.

Use `abi plan --type viral_viwrap --config <config.yaml>` to inspect the plan.
For direct preflight and managed execution, use `check_environment()` and
`run_viwrap()` from `abi.plugins.viral_viwrap`.
