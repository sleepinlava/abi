#!/usr/bin/env bash
set -euo pipefail

ACC_LIST="${1:?Usage: bash scripts/download_sra_fastq.sh accessions.txt output_dir}"
OUTDIR="${2:?Usage: bash scripts/download_sra_fastq.sh accessions.txt output_dir}"

mkdir -p "${OUTDIR}/sra" "${OUTDIR}/fastq"

while read -r ACC; do
  [[ -z "${ACC}" || "${ACC}" =~ ^# ]] && continue

  echo "[INFO] Downloading ${ACC}"
  prefetch "${ACC}" --output-directory "${OUTDIR}/sra"

  echo "[INFO] Converting ${ACC} to FASTQ"
  fasterq-dump "${OUTDIR}/sra/${ACC}/${ACC}.sra" \
    --split-files \
    --threads 8 \
    --outdir "${OUTDIR}/fastq"

  echo "[INFO] Compressing ${ACC}"
  shopt -s nullglob
  fastqs=("${OUTDIR}/fastq"/"${ACC}"*.fastq)
  shopt -u nullglob
  if [[ "${#fastqs[@]}" -eq 0 ]]; then
    echo "[ERROR] No FASTQ files generated for ${ACC}" >&2
    exit 1
  fi
  if command -v pigz >/dev/null 2>&1; then
    pigz -p 8 "${fastqs[@]}"
  else
    gzip -f "${fastqs[@]}"
  fi

done < "${ACC_LIST}"

echo "[DONE] FASTQ files are in ${OUTDIR}/fastq"
