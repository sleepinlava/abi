#!/usr/bin/env bash
# ── ABI Cloud Bootstrap — shared library ──────────────────────────────────
# Common helpers used by 01_envs.sh, 02_databases.sh, 03_verify.sh.
#
# Source this file from the stage scripts:
#   source "$(dirname "${BASH_SOURCE[0]}")/libcommon.sh"
# ───────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Project root resolution ───────────────────────────────────────────────
if [[ -z "${_ABI_LIBCOMMON_LOADED:-}" ]]; then
  _ABI_LIBCOMMON_LOADED=1
  _LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  ABI_PROJECT_ROOT="$(cd "${_LIB_DIR}/../.." && pwd)"
fi

# ── Configuration (overridable via environment) ───────────────────────────
: "${ABI_MAMBA_ROOT:=${ABI_PROJECT_ROOT}/.mamba}"
: "${ABI_RESOURCE_ROOT:=${ABI_PROJECT_ROOT}/resources/autoplasm}"
: "${ABI_LOG_DIR:=${ABI_PROJECT_ROOT}/logs/cloud}"
: "${ABI_RESOURCE_TIMEOUT_SECONDS:=86400}"  # 24h per-database timeout

# Stage-done sentinels live in the log dir.
ENV_SENTINEL="${ABI_LOG_DIR}/.cloud_envs_done"
DB_SENTINEL="${ABI_LOG_DIR}/.cloud_databases_done"

# ── Colour output ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $*"; }

# ── Logging ───────────────────────────────────────────────────────────────
# init_log <stage_name>  →  sets LOG_FILE, tees the script's stdout/stderr.
init_log() {
  local stage="$1"
  mkdir -p "${ABI_LOG_DIR}"
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  LOG_FILE="${ABI_LOG_DIR}/${stage}.${ts}.log"
  # Tee all subsequent output to the log file (FD 3 stays on the terminal).
  exec 3>&1 4>&2
  exec > >(tee -a "${LOG_FILE}") 2>&1
  log_info "Log file: ${LOG_FILE}"
}

# ── Disk precheck ─────────────────────────────────────────────────────────
# require_free_space_gb <min_gb> <path>
require_free_space_gb() {
  local min_gb="$1" path="${2:-${ABI_PROJECT_ROOT}}"
  local avail_kb avail_gb
  avail_kb="$(df -P "${path}" | awk 'NR==2 {print $4}')"
  avail_gb=$((avail_kb / 1024 / 1024))
  if (( avail_gb < min_gb )); then
    log_error "Insufficient disk space on ${path}: ${avail_gb} GB available, ${min_gb} GB required."
    log_error "Attach a larger data disk or set ABI_RESOURCE_ROOT to a larger volume."
    exit 2
  fi
  log_info "Disk check OK: ${avail_gb} GB free on ${path} (need ${min_gb} GB)."
}

# ── Tool availability ─────────────────────────────────────────────────────
require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log_error "$1 is not installed. Install it before continuing."
    exit 1
  fi
}

# ── Sentinel helpers ──────────────────────────────────────────────────────
mark_sentinel()  { mkdir -p "$(dirname "$1")"; touch "$1"; }
check_sentinel() { [[ -f "$1" ]]; }

# ── Atomic download helpers (shell level) ─────────────────────────────────
# atomic_wget <url> <dest> [sha256_expected]
# Downloads to dest.part, optionally verifies sha256, then atomically renames.
atomic_wget() {
  local url="$1" dest="$2" expected_sha="${3:-}"
  local part="${dest}.part"
  if [[ -f "${dest}" && -s "${dest}" ]]; then
    log_info "  Already exists: ${dest}"
    return 0
  fi
  part="${dest}.part"
  rm -f "${part}"
  if command -v wget >/dev/null 2>&1; then
    wget -q --show-progress --tries=3 --timeout=300 --retry-connrefused \
      -O "${part}" "${url}" || { rm -f "${part}"; return 1; }
  elif command -v curl >/dev/null 2>&1; then
    curl -L --retry 3 --max-time 7200 -o "${part}" "${url}" || { rm -f "${part}"; return 1; }
  else
    log_error "Neither wget nor curl found."; return 1
  fi
  if [[ -n "${expected_sha}" ]]; then
    local actual; actual="$(sha256sum "${part}" | cut -d' ' -f1)"
    if [[ "${actual}" != "${expected_sha}" ]]; then
      log_error "  sha256 mismatch for ${dest}: expected ${expected_sha}, got ${actual}"
      rm -f "${part}"
      return 1
    fi
  fi
  mv "${part}" "${dest}"
  log_info "  Downloaded: ${dest}"
}

# atomic_extract_tar <tarball> <dest_dir>
atomic_extract_tar() {
  local tarball="$1" dest="$2"
  local staging="${dest}.staging"
  rm -rf "${staging}"
  mkdir -p "${staging}"
  tar xf "${tarball}" -C "${staging}" || { rm -rf "${staging}"; return 1; }
  rm -rf "${dest}"
  mv "${staging}" "${dest}"
}

# ── Plugin list (all 7 ABI plugins) ───────────────────────────────────────
ABI_PLUGINS=(
  metagenomic_plasmid
  amplicon_16s
  wgs_bacteria
  rnaseq_expression
  metatranscriptomics
  easymetagenome
  viral_viwrap
)

# ── Conda env list (all 18 envs from environments.yaml) ───────────────────
ABI_ENV_NAMES=(
  autoplasm-base autoplasm-qc autoplasm-assembly autoplasm-annotation
  autoplasm-abundance autoplasm-plasmid-detect autoplasm-plasmid-binning
  autoplasm-integronfinder stats autoplasm-visualization autoplasm-nextflow
  abi-qc abi-stats rnaseq amplicon wgs easymeta-p0 easymeta-humann
)

# env_python <env_name>  →  prints the path to the env's python
env_python() { echo "${ABI_MAMBA_ROOT}/envs/$1/bin/python"; }
# env_bin <env_name> <executable>  →  prints path to an executable in the env
env_bin()    { echo "${ABI_MAMBA_ROOT}/envs/$1/bin/$2"; }
