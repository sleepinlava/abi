#!/usr/bin/env bash
# Build an immutable, strictly validated ABI runtime lock on the cloud host.
# Usage: scripts/cloud/prepare_release_lock.sh [--require-all-tools]
set -euo pipefail

PROJECT_ROOT=${ABI_PROJECT_ROOT:-/root/autodl-tmp/abi}
MAMBA_ROOT=${ABI_MAMBA_ROOT:-/root/autodl-tmp/.mamba}
RESOURCE_ROOT=${ABI_RUNTIME_RESOURCE_ROOT:-/root/autodl-tmp/resources}
LOCK_ROOT=${ABI_LOCK_ROOT:-/root/autodl-tmp/runtime-locks}
AUTOPLASM_SOURCE=${ABI_AUTOPLASM_SOURCE:-${PROJECT_ROOT}/resources/autoplasm}
RNA_SOURCE=${ABI_RNA_SOURCE:-${PROJECT_ROOT}/resources}
ABI_BIN=${ABI_BIN:-${MAMBA_ROOT}/envs/autoplasm-base/bin/abi}
PUBLISH_WAIT_SECONDS=${ABI_PUBLISH_WAIT_SECONDS:-60}

require_all_tools=()
if [[ ${1:-} == "--require-all-tools" ]]; then
  require_all_tools=(--require-all-tools)
elif [[ $# -gt 0 ]]; then
  echo "Unknown argument: $1" >&2
  exit 2
fi

ensure_link() {
  local source=$1
  local target=$2
  if [[ ! -e ${source} ]]; then
    echo "Required resource source does not exist: ${source}" >&2
    exit 1
  fi
  if [[ -e ${target} || -L ${target} ]]; then
    if [[ $(readlink -f "${target}") != $(readlink -f "${source}") ]]; then
      echo "Refusing to replace existing resource path: ${target}" >&2
      exit 1
    fi
    return
  fi
  if ln -s "${source}" "${target}" 2>/dev/null; then
    return
  fi
  if [[ -L ${target} ]] && [[ $(readlink -f "${target}") == $(readlink -f "${source}") ]]; then
    return
  fi
  echo "Failed to create canonical resource link: ${target}" >&2
  exit 1
}

mkdir -p "${RESOURCE_ROOT}" "${LOCK_ROOT}"
ensure_link "${AUTOPLASM_SOURCE}" "${RESOURCE_ROOT}/autoplasm"
ensure_link "${RNA_SOURCE}/star_index" "${RESOURCE_ROOT}/star_index"
ensure_link "${RNA_SOURCE}/NC_000913.3.gtf" "${RESOURCE_ROOT}/NC_000913.3.gtf"

version=$("${ABI_BIN}" --version)
commit=$(git -C "${PROJECT_ROOT}" rev-parse --short=12 HEAD)
prefix="abi-${version}-${commit}"
output_dir="${LOCK_ROOT}/${prefix}"
staging_dir="${output_dir}.staging.$$"
publish_lock="${output_dir}.publish-lock"

verify_release() {
  if [[ ! -f ${output_dir}/${prefix}.sha256 ]]; then
    echo "Existing release lock has no checksum manifest: ${output_dir}" >&2
    return 1
  fi
  (
    cd "${output_dir}"
    sha256sum --check "${prefix}.sha256"
  )
}

if [[ -d ${output_dir} ]]; then
  verify_release
  echo "Release lock already verified: ${output_dir}"
  exit 0
fi

lock_acquired=false
for _ in $(seq 1 "${PUBLISH_WAIT_SECONDS}"); do
  if mkdir "${publish_lock}" 2>/dev/null; then
    lock_acquired=true
    break
  fi
  if [[ -d ${output_dir} ]]; then
    verify_release
    echo "Release lock already verified: ${output_dir}"
    exit 0
  fi
  sleep 1
done
if [[ ${lock_acquired} != true ]]; then
  echo "Timed out waiting for release publication lock: ${publish_lock}" >&2
  exit 1
fi

if [[ -d ${output_dir} ]]; then
  rmdir "${publish_lock}"
  verify_release
  echo "Release lock already verified: ${output_dir}"
  exit 0
elif [[ -e ${output_dir} ]]; then
  echo "Refusing to replace existing release path: ${output_dir}" >&2
  rmdir "${publish_lock}"
  exit 1
fi

cleanup() {
  if [[ -d ${staging_dir} ]]; then
    rm -rf "${staging_dir}"
  fi
  if [[ -d ${publish_lock} ]]; then
    rmdir "${publish_lock}"
  fi
}
trap cleanup EXIT
mkdir -p "${staging_dir}"

"${ABI_BIN}" lock-runtime \
  --output-dir "${staging_dir}" \
  --prefix "${prefix}" \
  --mamba-root "${MAMBA_ROOT}" \
  --resource-root "${RESOURCE_ROOT}" \
  --conda-executable /root/autodl-tmp/miniconda3/bin/conda \
  --db-profile full \
  --type amplicon_16s \
  --type easymetagenome \
  --type metagenomic_plasmid \
  --type metatranscriptomics \
  --type rnaseq_expression \
  --type wgs_bacteria \
  --strict \
  "${require_all_tools[@]}"

(
  cd "${staging_dir}"
  sha256sum ./*.lock.yaml > "${prefix}.sha256"
)
chmod a-w "${staging_dir}"/* "${staging_dir}"
mv -T "${staging_dir}" "${output_dir}"
rmdir "${publish_lock}"
trap - EXIT
echo "Release lock created: ${output_dir}"
