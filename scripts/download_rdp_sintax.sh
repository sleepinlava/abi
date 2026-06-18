#!/usr/bin/env bash
# ── ABI RDP SINTAX Taxonomy Database Downloader ──────────────────────────
# Downloads the RDP 16S rRNA training set formatted for vsearch SINTAX.
#
# The RDP training set is ~50 MB compressed, ~200 MB decompressed.
# Source: https://www.drive5.com/sintax/
#
# Usage:
#   bash scripts/download_rdp_sintax.sh                     # default output
#   bash scripts/download_rdp_sintax.sh --output /path/db   # custom dir
#   bash scripts/download_rdp_sintax.sh --dry-run           # check only
#
# Output:
#   <output>/rdp_16s_v16.fa          — FASTA with SINTAX taxonomy headers
#   <output>/rdp_16s_v16.fa.gz        — compressed archive (kept for reference)

set -euo pipefail

OUTPUT_DIR="${PWD}/data/taxonomy"
DRY_RUN=false
RDP_URL="https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

FASTA_FILE="$OUTPUT_DIR/rdp_16s_v16.fa"
GZ_FILE="$OUTPUT_DIR/rdp_16s_v16.fa.gz"
MARKER_FILE="$OUTPUT_DIR/.abi_rdp_sintax_downloaded"

if [[ -f "$FASTA_FILE" ]]; then
  echo "RDP SINTAX database already exists: $FASTA_FILE"
  echo "To re-download: rm $FASTA_FILE && $0"
  exit 0
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY-RUN] Would download:"
  echo "  URL:    $RDP_URL"
  echo "  To:     $GZ_FILE"
  echo "  Decomp: $FASTA_FILE"
  exit 0
fi

echo "── ABI RDP SINTAX Database Download ───────────────────────"
echo "  Source: $RDP_URL"
echo "  Target: $FASTA_FILE"

mkdir -p "$OUTPUT_DIR"

# ── Download ──────────────────────────────────────────────────────────────
if command -v wget &>/dev/null; then
  echo "Downloading with wget..."
  wget -q --show-progress -O "$GZ_FILE" "$RDP_URL" || {
    echo "ERROR: Download failed. Check network or try manually:"
    echo "  wget $RDP_URL -O $GZ_FILE"
    exit 1
  }
elif command -v curl &>/dev/null; then
  echo "Downloading with curl..."
  curl -L -o "$GZ_FILE" "$RDP_URL" || {
    echo "ERROR: Download failed."
    exit 1
  }
else
  echo "ERROR: Neither wget nor curl found. Install one of them."
  exit 1
fi

# ── Decompress ────────────────────────────────────────────────────────────
echo "Decompressing..."
gunzip -c "$GZ_FILE" > "$FASTA_FILE" || {
  echo "ERROR: Decompression failed."
  exit 1
}

# Verify the file looks like SINTAX-formatted FASTA
SEQ_COUNT=$(grep -c "^>" "$FASTA_FILE" || echo "0")
TAX_COUNT=$(grep -c ";tax=" "$FASTA_FILE" || echo "0")
SIZE_MB=$(du -m "$FASTA_FILE" | cut -f1)

echo ""
echo "── Download complete ──────────────────────────────────────"
echo "  File:        $FASTA_FILE"
echo "  Size:        ${SIZE_MB} MB"
echo "  Sequences:   $SEQ_COUNT"
echo "  With tax:    $TAX_COUNT"

if [[ "$SEQ_COUNT" -gt 0 ]] && [[ "$TAX_COUNT" -gt 0 ]]; then
  # Write marker for abi check-resources
  echo "downloaded_at: $(date -Iseconds)" > "$MARKER_FILE"
  echo "source_url: $RDP_URL" >> "$MARKER_FILE"
  echo "sequences: $SEQ_COUNT" >> "$MARKER_FILE"
  echo "tax_annotated: $TAX_COUNT" >> "$MARKER_FILE"
  echo "✓ RDP SINTAX database ready."
else
  echo "WARNING: Downloaded file may be corrupted (no valid sequences found)."
  exit 1
fi
