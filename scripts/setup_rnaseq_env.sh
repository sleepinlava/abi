#!/usr/bin/env bash
# ── ABI rnaseq_expression Environment Setup ───────────────────────────────
# Creates the rnaseq conda/mamba environment with bioinformatics tools and
# installs R/Bioconductor packages (DESeq2) inside it.
#
# Usage:
#   bash scripts/setup_rnaseq_env.sh
#   bash scripts/setup_rnaseq_env.sh --mamba-root /opt/mamba
#   bash scripts/setup_rnaseq_env.sh --dry-run
#
# Design / 设计:
#   - Uses mamba for fast environment resolution
#   - Environment spec: envs/rnaseq.yml
#   - R packages installed via BiocManager (scripts/install_deseq2.R)
#   - Idempotent: skips env creation if already present
#   - Marker file (.abi_deseq2_installed) confirms R packages are ready

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_NAME="${ENV_NAME:-rnaseq}"
MAMBA_ROOT="${MAMBA_ROOT:-$PROJECT_ROOT/.mamba}"
DRY_RUN="${DRY_RUN:-false}"
SKIP_R_PACKAGES="${SKIP_R_PACKAGES:-false}"

# ── Parse CLI arguments ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mamba-root) MAMBA_ROOT="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --skip-r)     SKIP_R_PACKAGES=true; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

ENV_YAML="$PROJECT_ROOT/envs/rnaseq.yml"
INSTALL_R="$PROJECT_ROOT/scripts/install_deseq2.R"

if [[ ! -f "$ENV_YAML" ]]; then
  echo "ERROR: Environment spec not found: $ENV_YAML"
  exit 1
fi

# ── Locate mamba ────────────────────────────────────────────────────────────
MAMBA_BIN=""
if command -v mamba &>/dev/null; then
  MAMBA_BIN="mamba"
elif command -v conda &>/dev/null; then
  MAMBA_BIN="conda"
  echo "WARNING: mamba not found; falling back to conda (slower)"
elif [[ -x "$MAMBA_ROOT/bin/mamba" ]]; then
  MAMBA_BIN="$MAMBA_ROOT/bin/mamba"
else
  echo "ERROR: mamba/conda not found. Install mamba first:"
  echo "  https://mamba.readthedocs.io/en/latest/installation/mamba-installation.html"
  exit 1
fi

echo "── ABI rnaseq_expression Environment Setup ────────────────"
echo "  Environment: $ENV_NAME"
echo "  Spec:        $ENV_YAML"
echo "  Mamba:       $MAMBA_BIN"
echo "  Mamba root:  $MAMBA_ROOT"
echo ""

# ── Create / update conda environment ───────────────────────────────────────
ENV_DIR="$MAMBA_ROOT/envs/$ENV_NAME"
if [[ -d "$ENV_DIR" ]]; then
  echo "Environment '$ENV_NAME' already exists at $ENV_DIR"
  echo "To recreate: mamba env remove -n $ENV_NAME && $0"
else
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] Would create environment: $ENV_NAME"
    echo "[DRY-RUN]   $MAMBA_BIN env create -f $ENV_YAML -p $ENV_DIR"
  else
    echo "Creating environment '$ENV_NAME' ..."
    $MAMBA_BIN env create -f "$ENV_YAML" -p "$ENV_DIR" --yes
    echo "Environment created."
  fi
fi

# ── Install R packages (DESeq2 + companions) ────────────────────────────────
if [[ "$SKIP_R_PACKAGES" == "true" ]]; then
  echo "Skipping R package installation (--skip-r)."
  exit 0
fi

RSCRIPT="$ENV_DIR/bin/Rscript"
if [[ ! -x "$RSCRIPT" ]]; then
  # Fall back to system Rscript if conda env doesn't have R
  if command -v Rscript &>/dev/null; then
    RSCRIPT="$(command -v Rscript)"
    echo "Using system Rscript: $RSCRIPT"
  else
    echo "ERROR: Rscript not found in environment or system PATH."
    echo "Ensure r-base is listed in envs/rnaseq.yml or install R manually."
    exit 1
  fi
fi

cat << 'RCHECK' | "$RSCRIPT" --no-save 2>/dev/null || true
# Pre-flight: check if DESeq2 is already installed
if (requireNamespace("DESeq2", quietly = TRUE)) {
  cat("DESeq2 is already installed (version", as.character(packageVersion("DESeq2")), ")\n")
  quit(status = 0)
}
cat("DESeq2 not yet installed — running BiocManager installer...\n")
RCHECK

# Determine target R library
R_LIB="$ENV_DIR/lib/R/library"
if [[ -d "$R_LIB" ]]; then
  LIB_ARG="--lib $R_LIB"
else
  LIB_ARG=""
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY-RUN] Would run: Rscript $INSTALL_R $LIB_ARG"
else
  echo "Installing DESeq2 R packages..."
  "$RSCRIPT" "$INSTALL_R" $LIB_ARG
  echo "R package installation complete."
fi

echo ""
echo "── Setup complete ──────────────────────────────────────────"
echo "Verify with:"
echo "  abi doctor-agent --type rnaseq_expression"
echo "  $RSCRIPT -e 'library(DESeq2); packageVersion(\"DESeq2\")'"
