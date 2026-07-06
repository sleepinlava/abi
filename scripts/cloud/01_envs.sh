#!/usr/bin/env bash
# ── ABI Cloud Bootstrap — Stage 1: Conda environments ─────────────────────
# Installs all 18 conda/mamba environments + the ABI Python package + the
# rnaseq R/DESeq2 companion packages.
#
# Usage:
#   bash scripts/cloud/01_envs.sh                     # install everything
#   bash scripts/cloud/01_envs.sh --dry-run           # show what would happen
#   bash scripts/cloud/01_envs.sh --env autoplasm-base,stats  # subset only
#   bash scripts/cloud/01_envs.sh --mamba-root /data/.mamba   # custom root
#
# Environment overrides:
#   ABI_MAMBA_ROOT        mamba env root (default: <repo>/.mamba)
#   ABI_LOG_DIR           log directory (default: <repo>/logs/cloud)
# ───────────────────────────────────────────────────────────────────────────

source "$(dirname "${BASH_SOURCE[0]}")/libcommon.sh"

DRY_RUN=false
ENV_SUBSET=""
SKIP_RNASEQ_R=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)    DRY_RUN=true; shift ;;
    --env)        ENV_SUBSET="$2"; shift 2 ;;
    --mamba-root) ABI_MAMBA_ROOT="$2"; export ABI_MAMBA_ROOT; shift 2 ;;
    --skip-r)     SKIP_RNASEQ_R=true; shift ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

init_log "01_envs"

# ── Determine which envs to install ───────────────────────────────────────
if [[ -n "${ENV_SUBSET}" ]]; then
  IFS=',' read -ra ENVS_TO_INSTALL <<< "${ENV_SUBSET}"
else
  ENVS_TO_INSTALL=("${ABI_ENV_NAMES[@]}")
fi

log_step "Stage 1: Install ${#ENVS_TO_INSTALL[@]} conda environment(s)"
log_info "Project root : ${ABI_PROJECT_ROOT}"
log_info "Mamba root   : ${ABI_MAMBA_ROOT}"
log_info "Envs         : ${ENVS_TO_INSTALL[*]}"
[[ "${DRY_RUN}" == "true" ]] && log_warn "DRY RUN — no changes will be made."

# ── Locate or install micromamba/mamba ────────────────────────────────────
MAMBA_BIN=""
for cand in micromamba mamba conda; do
  if command -v "${cand}" >/dev/null 2>&1; then MAMBA_BIN="${cand}"; break; fi
done
if [[ -z "${MAMBA_BIN}" ]]; then
  log_info "No mamba/micromamba/conda found. Installing micromamba..."
  if [[ "${DRY_RUN}" != "true" ]]; then
    curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest \
      | tar -xvj -C "${ABI_MAMBA_ROOT}/.." bin/micromamba 2>/dev/null \
      || { log_error "micromamba install failed."; exit 1; }
    MAMBA_BIN="micromamba"
    export MAMBA_ROOT_PREFIX="${ABI_MAMBA_ROOT}"
  fi
fi
log_info "Using: ${MAMBA_BIN}"
if [[ "${MAMBA_BIN}" == "micromamba" ]]; then export MAMBA_ROOT_PREFIX="${ABI_MAMBA_ROOT}"; fi

# ── Regenerate envs/*.yml from environments.yaml (ensure consistency) ─────
log_step "Regenerating envs/*.yml from environments.yaml"
if [[ "${DRY_RUN}" != "true" ]]; then
  python "${ABI_PROJECT_ROOT}/scripts/emit_env_yamls.py" \
    || log_warn "emit_env_yamls.py failed; using existing envs/*.yml"
fi

# ── Install ABI Python package (core + dev + report + mcp) ────────────────
log_step "Installing ABI Python package"
if [[ "${DRY_RUN}" != "true" ]]; then
  pip install -e "${ABI_PROJECT_ROOT}[dev,report,mcp]" \
    || log_warn "pip install -e failed; continuing (envs may still be usable)"
fi

# ── Create/update each conda environment ──────────────────────────────────
created=0; skipped=0; failed=0
for env_name in "${ENVS_TO_INSTALL[@]}"; do
  env_yaml="${ABI_PROJECT_ROOT}/envs/${env_name}.yml"
  env_prefix="${ABI_MAMBA_ROOT}/envs/${env_name}"
  if [[ ! -f "${env_yaml}" ]]; then
    log_warn "  ${env_name}: env file not found (${env_yaml}); skipping."
    ((++failed)); continue
  fi
  if [[ -d "${env_prefix}" ]]; then
    log_info "  ${env_name}: already exists, updating..."
    if [[ "${DRY_RUN}" != "true" ]]; then
      "${MAMBA_BIN}" env update -p "${env_prefix}" -f "${env_yaml}" -y \
        || { log_error "  ${env_name}: update failed."; ((++failed)); continue; }
    fi
    ((++skipped))
  else
    log_info "  ${env_name}: creating..."
    if [[ "${DRY_RUN}" != "true" ]]; then
      "${MAMBA_BIN}" env create -p "${env_prefix}" -f "${env_yaml}" -y \
        || { log_error "  ${env_name}: create failed."; ((++failed)); continue; }
    fi
    ((++created))
  fi
done

# ── rnaseq companion R packages (DESeq2 etc.) ─────────────────────────────
if [[ " ${ENVS_TO_INSTALL[*]} " == *" rnaseq "* ]] && [[ "${SKIP_RNASEQ_R}" != "true" ]]; then
  log_step "Setting up rnaseq environment + DESeq2 R packages"
  if [[ "${DRY_RUN}" != "true" ]]; then
    bash "${ABI_PROJECT_ROOT}/scripts/setup_rnaseq_env.sh" \
      --mamba-root "${ABI_MAMBA_ROOT}" \
      || log_warn "setup_rnaseq_env.sh failed; rnaseq R companions not installed."
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────
log_step "Stage 1 complete"
echo "  Created : ${created}"
echo "  Updated : ${skipped}"
echo "  Failed  : ${failed}"
if [[ "${failed}" -gt 0 ]]; then
  log_warn "Some environments failed to install. Check the log: ${LOG_FILE}"
  exit 1
fi
if [[ "${DRY_RUN}" != "true" ]]; then
  mark_sentinel "${ENV_SENTINEL}"
  log_info "Sentinel written: ${ENV_SENTINEL}"
fi
