#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# AutoPlasm Database Downloader
# Downloads full versions of Bakta, geNomad, and mob_suite databases.
# Run this on the cloud server after cloning/pulling the code repository.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RESOURCES_DIR="${PROJECT_ROOT}/resources/autoplasm"

# Mamba root for resolving conda-env executables (mob_suite lives in a env,
# not necessarily the system python3).
MAMBA_ROOT="${ABI_MAMBA_ROOT:-${AUTOPLASM_MAMBA_ROOT:-${PROJECT_ROOT}/.mamba}}"
ANNOTATION_PYTHON="${MAMBA_ROOT}/envs/autoplasm-annotation/bin/python"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------
check_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

log_info "Checking prerequisites..."
check_cmd bakta_db
check_cmd genomad
# mob_suite init is done via Python module, no standalone CLI to check here

mkdir -p "${RESOURCES_DIR}"

# ---------------------------------------------------------------------------
# 1. Bakta Database (FULL version ~30 GB compressed / ~84 GB unpacked)
# ---------------------------------------------------------------------------
BAKTA_DIR="${RESOURCES_DIR}/bakta/db-full"
if [[ -d "${BAKTA_DIR}" && -f "${BAKTA_DIR}/bakta.db" ]]; then
    log_warn "Bakta full database already exists at ${BAKTA_DIR}. Skipping."
else
    if [[ -d "${BAKTA_DIR}" ]]; then
        # A partial/invalid Bakta dir exists (bakta.db missing). Back it up
        # instead of rm -rf, so a transiently-missing marker does not trigger
        # a destructive 30-84 GB re-download.
        BACKUP="${BAKTA_DIR}.bak.$(date +%s)"
        log_warn "Existing Bakta dir is incomplete (missing bakta.db). Moving it aside to ${BACKUP}."
        mv "${BAKTA_DIR}" "${BACKUP}"
    fi
    log_info "Downloading Bakta FULL database (~30 GB compressed, ~84 GB unpacked)..."
    log_info "This will take a while depending on your network speed."
    mkdir -p "${BAKTA_DIR}"
    bakta_db download --output "${BAKTA_DIR}" --type full
    if [[ ! -f "${BAKTA_DIR}/bakta.db" ]]; then
        log_error "Bakta download completed but bakta.db is missing; download may have failed."
        exit 1
    fi
    log_info "Bakta full database download complete."
fi

# ---------------------------------------------------------------------------
# 2. geNomad Database
# ---------------------------------------------------------------------------
GENOMAD_DIR="${RESOURCES_DIR}/genomad/genomad_db"
if [[ -d "${GENOMAD_DIR}" && -f "${GENOMAD_DIR}/genomad_db" ]]; then
    log_warn "geNomad database already exists at ${GENOMAD_DIR}. Skipping."
else
    if [[ -d "${GENOMAD_DIR}" ]]; then
        BACKUP="${GENOMAD_DIR}.bak.$(date +%s)"
        log_warn "Existing geNomad dir is incomplete. Moving it aside to ${BACKUP}."
        mv "${GENOMAD_DIR}" "${BACKUP}"
    fi
    log_info "Downloading geNomad database..."
    mkdir -p "${RESOURCES_DIR}/genomad"
    genomad download-database "${RESOURCES_DIR}/genomad/"
    if [[ ! -f "${GENOMAD_DIR}/genomad_db" ]]; then
        log_error "geNomad download completed but genomad_db is missing; download may have failed."
        exit 1
    fi
    log_info "geNomad database download complete."
fi

# ---------------------------------------------------------------------------
# 3. mob_suite Database
# ---------------------------------------------------------------------------
MOB_DIR="${RESOURCES_DIR}/mob_suite"
# mob_suite usually stores DBs inside its package dir or a default location.
# We trigger the built-in initializer which downloads if missing.
if [[ -f "${MOB_DIR}/.autoplasm_resource_ready" ]]; then
    log_warn "mob_suite database already initialized. Skipping."
else
    log_info "Initializing mob_suite databases..."
    mkdir -p "${MOB_DIR}"
    # Use the autoplasm-annotation env python (where mob_suite is installed)
    # rather than the system python3, which may not have mob_suite importable.
    if [[ -x "${ANNOTATION_PYTHON}" ]]; then
        "${ANNOTATION_PYTHON}" -c "
import mob_suite.mob_init
mob_suite.mob_init.mob_init()
"
    else
        log_warn "autoplasm-annotation env python not found at ${ANNOTATION_PYTHON}; falling back to system python3."
        python3 -c "
import mob_suite.mob_init
mob_suite.mob_init.mob_init()
"
    fi
    # Verify mob_suite BLAST indices exist before touching the ready marker
    # (mob_init can exit 0 while leaving an incomplete DB).
    MOB_BLAST_FOUND=false
    for f in "${MOB_DIR}"/*.nhr "${MOB_DIR}"/*.phr; do
        if [[ -f "$f" ]]; then MOB_BLAST_FOUND=true; break; fi
    done
    if [[ "${MOB_BLAST_FOUND}" == "true" ]]; then
        touch "${MOB_DIR}/.autoplasm_resource_ready"
        log_info "mob_suite database initialization complete."
    else
        log_error "mob_init completed but no BLAST index files found in ${MOB_DIR}; database may be incomplete."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log_info "All databases are ready."
echo ""
echo "Database locations:"
echo "  Bakta (full):  ${BAKTA_DIR}"
echo "  geNomad:       ${GENOMAD_DIR}"
echo "  mob_suite:     ${MOB_DIR}"
echo ""
echo "Disk usage:"
du -sh "${BAKTA_DIR}" 2>/dev/null || true
du -sh "${GENOMAD_DIR}" 2>/dev/null || true
du -sh "${MOB_DIR}" 2>/dev/null || true
