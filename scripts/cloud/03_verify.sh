#!/usr/bin/env bash
# ── ABI Cloud Bootstrap — Stage 3: Verification ───────────────────────────
# Verifies that all conda environments and databases are ready for use.
# Produces a machine-readable JSON summary + a coloured terminal report.
#
# Usage:
#   bash scripts/cloud/03_verify.sh
#   bash scripts/cloud/03_verify.sh --plugin metagenomic_plasmid
#   bash scripts/cloud/03_verify.sh --json   # emit only JSON to stdout
# ───────────────────────────────────────────────────────────────────────────

source "$(dirname "${BASH_SOURCE[0]}")/libcommon.sh"

JSON_ONLY=false
PLUGIN_SUBSET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)    JSON_ONLY=true; shift ;;
    --plugin)  PLUGIN_SUBSET="$2"; shift 2 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

init_log "03_verify"

if [[ -n "${PLUGIN_SUBSET}" ]]; then
  IFS=',' read -ra PLUGINS <<< "${PLUGIN_SUBSET}"
else
  PLUGINS=("${ABI_PLUGINS[@]}")
fi

# ── Environment verification ──────────────────────────────────────────────
envs_ok=0; envs_missing=0
missing_envs=()
for env_name in "${ABI_ENV_NAMES[@]}"; do
  if [[ -d "${ABI_MAMBA_ROOT}/envs/${env_name}" ]]; then
    ((envs_ok++))
  else
    ((envs_missing++))
    missing_envs+=("${env_name}")
  fi
done

# ── Database verification via `abi check-resources` ───────────────────────
declare -A db_status
db_ok=0; db_failed=0; db_manual=0; db_missing=0
abi_bin="$(env_bin autoplasm-base abi 2>/dev/null || echo abi)"

# ── Generate a minimal cloud config pointing resources.root at ABI_RESOURCE_ROOT.
CLOUD_CONFIG="${ABI_LOG_DIR}/cloud_config.yaml"
if [[ ! -f "${CLOUD_CONFIG}" ]]; then
  mkdir -p "${ABI_LOG_DIR}"
  cat > "${CLOUD_CONFIG}" <<EOF
resources:
  root: ${ABI_RESOURCE_ROOT}
EOF
fi

verify_plugin_dbs() {
  local plugin="$1"
  if ! command -v "${abi_bin}" >/dev/null 2>&1 && [[ ! -x "${abi_bin}" ]]; then
    log_warn "abi binary unavailable; cannot check ${plugin} resources."
    return
  fi
  local output
  output="$("${abi_bin}" check-resources --type "${plugin}" \
    --config "${CLOUD_CONFIG}" 2>/dev/null || true)"
  echo "${output}" | while IFS=$'\t' read -r rid status ready; do
    printf "  %-22s %-10s %s\n" "${rid}" "${status}" "${ready}"
  done
}

log_step "Stage 3: Verification"
log_info "Environments: ${envs_ok} ok, ${envs_missing} missing"
if [[ ${envs_missing} -gt 0 ]]; then
  log_warn "Missing environments: ${missing_envs[*]}"
fi

log_info "Databases (per plugin):"
for plugin in "${PLUGINS[@]}"; do
  echo ""
  log_info "→ ${plugin}"
  verify_plugin_dbs "${plugin}"
done

# ── Disk usage ────────────────────────────────────────────────────────────
log_info "Resource root disk usage:"
du -sh "${ABI_RESOURCE_ROOT}" 2>/dev/null || log_warn "  (not found)"

# ── Machine-readable JSON summary ─────────────────────────────────────────
summary_file="${ABI_LOG_DIR}/cloud_verify.$(date +%Y%m%d_%H%M%S).json"
cat > "${summary_file}" <<EOF
{
  "generated_at": "$(date -Iseconds)",
  "mamba_root": "${ABI_MAMBA_ROOT}",
  "resource_root": "${ABI_RESOURCE_ROOT}",
  "environments": {"ok": ${envs_ok}, "missing": ${envs_missing}, "missing_names": [$(printf '"%s",' "${missing_envs[@]}" | sed 's/,$//')]},
  "plugins_checked": [$(printf '"%s",' "${PLUGINS[@]}" | sed 's/,$//')],
  "sentinels": {"envs_done": $(check_sentinel "${ENV_SENTINEL}" && echo true || echo false), "databases_done": $(check_sentinel "${DB_SENTINEL}" && echo true || echo false)}
}
EOF
log_info "JSON summary: ${summary_file}"

if [[ "${JSON_ONLY}" == "true" ]]; then
  cat "${summary_file}"
fi

# ── Exit code: 0 all ok, 2 partial, 1 fatal ───────────────────────────────
if [[ ${envs_missing} -gt 0 ]] && [[ ! -f "${ENV_SENTINEL}" ]]; then
  log_error "Environments not fully installed. Run 01_envs.sh first."
  exit 1
fi
if [[ ! -f "${DB_SENTINEL}" ]]; then
  log_warn "Databases sentinel not found. Run 02_databases.sh, or some DBs may be manual."
  exit 2
fi
log_step "All checks complete."
exit 0
