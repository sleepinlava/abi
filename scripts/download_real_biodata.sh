#!/usr/bin/env bash
set -Eeuo pipefail

###############################################################################
# Real biological data downloader for ABI validation
#
# Default:
#   - set:    minimal
#   - method: ena
#   - outdir: data/raw
#
# Usage:
#   bash scripts/download_real_biodata.sh --set minimal  --method ena --threads 8
#   bash scripts/download_real_biodata.sh --set standard --method ena --threads 8
#   bash scripts/download_real_biodata.sh --set full     --method ena --threads 8
#
# SRA Toolkit mode:
#   bash scripts/download_real_biodata.sh --set minimal --method sra --threads 8
###############################################################################

SET_NAME="minimal"
METHOD="ena"
THREADS="8"
OUTDIR="data/raw"
META_DIR="metadata/accessions"
MANIFEST_DIR="data/manifest"
RUN_GZIP_TEST="1"
COUNT_READS="0"

usage() {
  cat <<USAGE
Usage:
  bash scripts/download_real_biodata.sh [options]

Options:
  --set minimal|standard|full     Dataset scale. Default: minimal
  --method ena|sra|auto           Download method. Default: ena
  --threads N                     Threads for compression/checks. Default: 8
  --outdir DIR                    Output root directory. Default: data/raw
  --no-gzip-test                  Skip gzip -t check
  --count-reads                   Count FASTQ reads after download. Slow for large files
  -h, --help                      Show help

Dataset sets:
  minimal:
    ERR3152364 ERR3152366 SRR915693 SRR001666

  standard:
    minimal + 6 Zymo isolate Illumina runs

  full:
    standard + ONT stress runs + all 10 Zymo isolate Illumina runs
USAGE
}

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --set)
      SET_NAME="${2:?Missing value for --set}"
      shift 2
      ;;
    --method)
      METHOD="${2:?Missing value for --method}"
      shift 2
      ;;
    --threads)
      THREADS="${2:?Missing value for --threads}"
      shift 2
      ;;
    --outdir)
      OUTDIR="${2:?Missing value for --outdir}"
      shift 2
      ;;
    --no-gzip-test)
      RUN_GZIP_TEST="0"
      shift
      ;;
    --count-reads)
      COUNT_READS="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

case "${SET_NAME}" in
  minimal|standard|full) ;;
  *) die "--set must be one of: minimal, standard, full" ;;
esac

case "${METHOD}" in
  ena|sra|auto) ;;
  *) die "--method must be one of: ena, sra, auto" ;;
esac

mkdir -p "${OUTDIR}" "${META_DIR}" "${MANIFEST_DIR}"

###############################################################################
# Dependency checks
###############################################################################

if [[ "${METHOD}" == "ena" || "${METHOD}" == "auto" ]]; then
  have_cmd curl || die "curl not found. Install it first."
  have_cmd wget || die "wget not found. Install it first."
  have_cmd md5sum || die "md5sum not found. Install coreutils first."
fi

if [[ "${METHOD}" == "sra" || "${METHOD}" == "auto" ]]; then
  have_cmd prefetch || log "[WARN] prefetch not found. SRA mode will fail unless sra-tools is installed."
  have_cmd fasterq-dump || log "[WARN] fasterq-dump not found. SRA mode will fail unless sra-tools is installed."
fi

if have_cmd pigz; then
  COMPRESS_CMD="pigz -f -p ${THREADS}"
else
  COMPRESS_CMD="gzip -f"
fi

###############################################################################
# Accession files
###############################################################################

write_accession_files() {
  mkdir -p "${META_DIR}"

  cat > "${META_DIR}/accessions_metagenome_ont.txt" <<'ACC'
ERR3152364
ERR3152366
ACC

  cat > "${META_DIR}/accessions_metagenome_ont_stress.txt" <<'ACC'
ERR3152365
ERR3152367
ACC

  cat > "${META_DIR}/accessions_zymo_isolates_core_illumina.txt" <<'ACC'
ERR2935851
ERR2935850
ERR2935852
ERR2935853
ERR2935848
ERR2935849
ACC

  cat > "${META_DIR}/accessions_zymo_isolates_all_illumina.txt" <<'ACC'
ERR2935851
ERR2935856
ERR2935850
ERR2935852
ERR2935857
ERR2935854
ERR2935853
ERR2935855
ERR2935848
ERR2935849
ACC

  cat > "${META_DIR}/accessions_rnaseq_ecoli.txt" <<'ACC'
SRR915693
ACC

  cat > "${META_DIR}/accessions_negative_control.txt" <<'ACC'
SRR001666
ACC

  cat > "${META_DIR}/accessions_minimal_real_test.txt" <<'ACC'
ERR3152364
ERR3152366
SRR915693
SRR001666
ACC
}

###############################################################################
# Dataset selection
###############################################################################

dataset_files_for_set() {
  case "${SET_NAME}" in
    minimal)
      echo "metagenome_ont:${META_DIR}/accessions_metagenome_ont.txt"
      echo "ecoli_rnaseq:${META_DIR}/accessions_rnaseq_ecoli.txt"
      echo "negative_control:${META_DIR}/accessions_negative_control.txt"
      ;;
    standard)
      echo "metagenome_ont:${META_DIR}/accessions_metagenome_ont.txt"
      echo "zymo_isolates:${META_DIR}/accessions_zymo_isolates_core_illumina.txt"
      echo "ecoli_rnaseq:${META_DIR}/accessions_rnaseq_ecoli.txt"
      echo "negative_control:${META_DIR}/accessions_negative_control.txt"
      ;;
    full)
      echo "metagenome_ont:${META_DIR}/accessions_metagenome_ont.txt"
      echo "metagenome_ont_stress:${META_DIR}/accessions_metagenome_ont_stress.txt"
      echo "zymo_isolates:${META_DIR}/accessions_zymo_isolates_all_illumina.txt"
      echo "ecoli_rnaseq:${META_DIR}/accessions_rnaseq_ecoli.txt"
      echo "negative_control:${META_DIR}/accessions_negative_control.txt"
      ;;
  esac
}

###############################################################################
# ENA download
###############################################################################

download_one_ena() {
  local dataset="$1"
  local acc="$2"
  local dataset_dir="${OUTDIR}/${dataset}"
  local fastq_dir="${dataset_dir}/fastq"
  local metadata_dir="${dataset_dir}/metadata"
  local report="${metadata_dir}/${acc}.ena.tsv"

  mkdir -p "${fastq_dir}" "${metadata_dir}"

  log "[ENA] Querying ${acc}"

  local api_url
  api_url="https://www.ebi.ac.uk/ena/portal/api/filereport?accession=${acc}&result=read_run&fields=run_accession,library_layout,instrument_platform,instrument_model,fastq_ftp,fastq_md5,fastq_bytes&format=tsv&download=false"

  curl -fsSL --retry 5 --retry-delay 5 --connect-timeout 30 --max-time 180 \
    "${api_url}" > "${report}" || return 1

  local fastq_ftp fastq_md5
  fastq_ftp="$(awk -F'\t' 'NR==2 {print $5}' "${report}")"
  fastq_md5="$(awk -F'\t' 'NR==2 {print $6}' "${report}")"

  [[ -n "${fastq_ftp}" ]] || return 1

  IFS=';' read -r -a urls <<< "${fastq_ftp}"
  IFS=';' read -r -a md5s <<< "${fastq_md5}"

  local i
  for i in "${!urls[@]}"; do
    local url="${urls[$i]}"
    local expected_md5="${md5s[$i]:-}"
    local filename
    filename="$(basename "${url}")"

    local outfile="${fastq_dir}/${filename}"

    log "[ENA] Downloading ${acc}: ${filename}"

    if [[ -s "${outfile}" ]]; then
      log "[SKIP] Existing file found: ${outfile}"
    else
      wget -c \
        --tries=8 \
        --waitretry=10 \
        --timeout=120 \
        --read-timeout=120 \
        -P "${fastq_dir}" \
        "https://${url}" \
      || wget -c \
        --tries=8 \
        --waitretry=10 \
        --timeout=120 \
        --read-timeout=120 \
        -P "${fastq_dir}" \
        "ftp://${url}"
    fi

    if [[ -n "${expected_md5}" ]]; then
      log "[ENA] MD5 checking ${filename}"
      local actual_md5
      actual_md5="$(md5sum "${outfile}" | awk '{print $1}')"

      if [[ "${actual_md5}" != "${expected_md5}" ]]; then
        echo -e "${dataset}\t${acc}\t${outfile}\tMD5_FAIL\t${actual_md5}\t${expected_md5}" \
          >> "${MANIFEST_DIR}/download_failures.tsv"
        die "MD5 mismatch for ${outfile}. Remove the file and rerun."
      fi
    fi
  done

  return 0
}

###############################################################################
# SRA Toolkit download
###############################################################################

download_one_sra() {
  local dataset="$1"
  local acc="$2"
  local dataset_dir="${OUTDIR}/${dataset}"
  local sra_dir="${dataset_dir}/sra"
  local fastq_dir="${dataset_dir}/fastq"
  local tmp_dir="${dataset_dir}/tmp/${acc}"

  mkdir -p "${sra_dir}" "${fastq_dir}" "${tmp_dir}"

  have_cmd prefetch || die "prefetch not found. Install sra-tools first."
  have_cmd fasterq-dump || die "fasterq-dump not found. Install sra-tools first."

  log "[SRA] Prefetch ${acc}"

  prefetch "${acc}" \
    --output-directory "${sra_dir}" \
    --max-size 100000G

  local sra_file
  sra_file="$(find "${sra_dir}" -name "${acc}.sra" -type f | head -n 1)"

  [[ -n "${sra_file}" ]] || die "Cannot find downloaded SRA file for ${acc}"

  log "[SRA] fasterq-dump ${acc}"

  fasterq-dump "${sra_file}" \
    --split-files \
    --threads "${THREADS}" \
    --outdir "${fastq_dir}" \
    --temp "${tmp_dir}"

  log "[SRA] Compressing FASTQ for ${acc}"

  shopt -s nullglob
  local fq_files=("${fastq_dir}/${acc}"*.fastq)
  shopt -u nullglob

  if [[ "${#fq_files[@]}" -eq 0 ]]; then
    die "No FASTQ files generated for ${acc}"
  fi

  # shellcheck disable=SC2086
  ${COMPRESS_CMD} "${fq_files[@]}"
}

###############################################################################
# Download dispatcher
###############################################################################

download_one() {
  local dataset="$1"
  local acc="$2"

  case "${METHOD}" in
    ena)
      download_one_ena "${dataset}" "${acc}" || die "ENA download failed for ${acc}"
      ;;
    sra)
      download_one_sra "${dataset}" "${acc}"
      ;;
    auto)
      if download_one_ena "${dataset}" "${acc}"; then
        log "[AUTO] ENA succeeded for ${acc}"
      else
        log "[AUTO] ENA failed for ${acc}; falling back to SRA Toolkit"
        download_one_sra "${dataset}" "${acc}"
      fi
      ;;
  esac
}

download_dataset() {
  local dataset="$1"
  local accession_file="$2"

  [[ -f "${accession_file}" ]] || die "Accession file not found: ${accession_file}"

  log "========== Dataset: ${dataset} =========="
  log "Accession file: ${accession_file}"

  while read -r acc; do
    [[ -z "${acc}" || "${acc}" =~ ^# ]] && continue
    download_one "${dataset}" "${acc}"
  done < "${accession_file}"
}

###############################################################################
# Manifest and checks
###############################################################################

write_manifest() {
  local manifest="${MANIFEST_DIR}/raw_fastq_manifest.tsv"

  log "[MANIFEST] Writing ${manifest}"

  {
    echo -e "dataset\tfilename\tpath\tbytes\tmd5"
    find "${OUTDIR}" -path "*/fastq/*.fastq.gz" -type f | sort | while read -r f; do
      local dataset relpath
      relpath="${f#${OUTDIR}/}"
      dataset="${relpath%%/*}"
      local filename bytes md5
      filename="$(basename "${f}")"
      bytes="$(stat -c%s "${f}")"
      md5="$(md5sum "${f}" | awk '{print $1}')"
      echo -e "${dataset}\t${filename}\t${f}\t${bytes}\t${md5}"
    done
  } > "${manifest}"
}

gzip_test_all() {
  [[ "${RUN_GZIP_TEST}" == "1" ]] || return 0

  log "[CHECK] Running gzip -t on all FASTQ.gz files"

  find "${OUTDIR}" -path "*/fastq/*.fastq.gz" -type f -print0 \
    | xargs -r -0 -n 1 -P "${THREADS}" gzip -t

  log "[CHECK] gzip -t passed"
}

count_reads_all() {
  [[ "${COUNT_READS}" == "1" ]] || return 0

  local read_count_file="${MANIFEST_DIR}/fastq_read_counts.tsv"

  log "[COUNT] Counting reads. This can be slow for large files."

  {
    echo -e "file\treads"
    find "${OUTDIR}" -path "*/fastq/*.fastq.gz" -type f | sort | while read -r f; do
      local reads
      reads="$(zcat "${f}" | awk 'END {if (NR % 4 != 0) {print "INVALID_FASTQ"} else {print NR/4}}')"
      echo -e "${f}\t${reads}"
    done
  } > "${read_count_file}"

  log "[COUNT] Wrote ${read_count_file}"
}

###############################################################################
# Main
###############################################################################

log "ABI real biological data download started"
log "SET=${SET_NAME}"
log "METHOD=${METHOD}"
log "THREADS=${THREADS}"
log "OUTDIR=${OUTDIR}"

write_accession_files

log "Created accession files under ${META_DIR}"

while IFS=':' read -r dataset accession_file; do
  download_dataset "${dataset}" "${accession_file}"
done < <(dataset_files_for_set)

gzip_test_all
write_manifest
count_reads_all

log "DONE"
log "FASTQ root: ${OUTDIR}"
log "Manifest: ${MANIFEST_DIR}/raw_fastq_manifest.tsv"
