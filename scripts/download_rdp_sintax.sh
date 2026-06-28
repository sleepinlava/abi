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

# ── Download (with retry/timeout) ───────────────────────────────────────────
if command -v wget &>/dev/null; then
  echo "Downloading with wget..."
  wget -q --show-progress --tries=3 --timeout=300 --retry-connrefused \
    -O "$GZ_FILE" "$RDP_URL" || {
    rm -f "$GZ_FILE"
    echo "ERROR: Download failed. Check network or try manually:"
    echo "  wget $RDP_URL -O $GZ_FILE"
    exit 1
  }
elif command -v curl &>/dev/null; then
  echo "Downloading with curl..."
  curl -L --retry 3 --max-time 600 -o "$GZ_FILE" "$RDP_URL" || {
    rm -f "$GZ_FILE"
    echo "ERROR: Download failed."
    exit 1
  }
else
  echo "ERROR: Neither wget nor curl found. Install one of them."
  exit 1
fi

# ── Decompress (atomic: write to .tmp, verify, then mv) ────────────────────
echo "Decompressing..."
FASTA_TMP="$FASTA_FILE.tmp"
cleanup() { rm -f "$FASTA_TMP"; }
trap cleanup EXIT
gunzip -c "$GZ_FILE" > "$FASTA_TMP" || {
  echo "ERROR: Decompression failed."
  rm -f "$FASTA_TMP"
  exit 1
}

# Verify the decompressed file looks like SINTAX-formatted FASTA
SEQ_COUNT=$(grep -c "^>" "$FASTA_TMP" || echo "0")
TAX_COUNT=$(grep -c ";tax=" "$FASTA_TMP" || echo "0")
SIZE_MB=$(du -m "$FASTA_TMP" | cut -f1)

echo ""
echo "── Download complete ──────────────────────────────────────"
echo "  File:        $FASTA_FILE"
echo "  Size:        ${SIZE_MB} MB"
echo "  Sequences:   $SEQ_COUNT"
echo "  With tax:    $TAX_COUNT"

# Require a reasonable fraction of sequences to carry SINTAX taxonomy
# (the previous check accepted a DB where 1 of 10,000 seqs was annotated).
if [[ "$SEQ_COUNT" -gt 0 ]] && [[ "$TAX_COUNT" -gt 0 ]] && \
   [[ $((TAX_COUNT * 10)) -ge $SEQ_COUNT ]]; then
  mv "$FASTA_TMP" "$FASTA_FILE"
  trap - EXIT
  # Write marker for abi check-resources
  echo "downloaded_at: $(date -Iseconds)" > "$MARKER_FILE"
  echo "source_url: $RDP_URL" >> "$MARKER_FILE"
  echo "sequences: $SEQ_COUNT" >> "$MARKER_FILE"
  echo "tax_annotated: $TAX_COUNT" >> "$MARKER_FILE"
  echo "✓ RDP SINTAX database ready."
else
  echo "WARNING: Downloaded file may be corrupted (insufficient SINTAX-annotated sequences)."
  rm -f "$FASTA_TMP"
  exit 1
fi
