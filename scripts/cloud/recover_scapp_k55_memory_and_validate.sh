#!/usr/bin/env bash
# Recover the failed SCAPP MetaSPAdes K55 stage with the paper-scale memory limit,
# preserve machine-readable failure/recovery evidence, and run final validation.
set -euo pipefail

ABI_REPO=${ABI_REPO:-/root/autodl-tmp/abi}
TASK_ROOT=${TASK_ROOT:-/root/autodl-tmp/abi-real-data/references/scapp/independent_truth_20260717}
ASSEMBLY_DIR=${ASSEMBLY_DIR:-${TASK_ROOT}/metaspades_screen}
INITIAL_EXIT=${INITIAL_EXIT:-${TASK_ROOT}/metaspades_screen.exit_code}
INITIAL_LOG=${INITIAL_LOG:-${TASK_ROOT}/metaspades_screen.launch.log}
RECOVERY_EXIT=${RECOVERY_EXIT:-${TASK_ROOT}/metaspades_k127_memory_recovery.exit_code}
RECOVERY_LOG=${RECOVERY_LOG:-${TASK_ROOT}/metaspades_k127_memory_recovery.launch.log}
RECOVERY_PROVENANCE=${RECOVERY_PROVENANCE:-${TASK_ROOT}/metaspades_k127_memory_recovery.provenance.tsv}
K55_SNAPSHOT=${K55_SNAPSHOT:-${TASK_ROOT}/metaspades_k55_recovered_snapshot}
SPADES_ENV=${SPADES_ENV:-/root/autodl-tmp/.mamba/envs/autoplasm-assembly}
THREADS=${THREADS:-16}
MEMORY_GB=${MEMORY_GB:-750}
MIN_AVAILABLE_GB=${MIN_AVAILABLE_GB:-800}

fail() {
    printf '%s\n' "$*" >&2
    exit 2
}

[[ -f ${INITIAL_EXIT} ]] || fail "Missing initial exit marker: ${INITIAL_EXIT}"
[[ $(<"${INITIAL_EXIT}") == 68 ]] || fail "Expected preserved initial exit 68"
grep -q 'unable to allocate OS memory' "${INITIAL_LOG}" \
    || fail "Initial log does not contain the expected allocation failure"
[[ -d ${ASSEMBLY_DIR}/K21 && -d ${ASSEMBLY_DIR}/K33 ]] \
    || fail "Required K21/K33 restart state is missing"
[[ ! -e ${RECOVERY_EXIT} ]] || fail "Recovery exit marker already exists: ${RECOVERY_EXIT}"
[[ ! -e ${K55_SNAPSHOT} ]] || fail "Recovery snapshot already exists: ${K55_SNAPSHOT}"
[[ ! -e ${TASK_ROOT}/paper_method_v1 ]] \
    || fail "Immutable validation output already exists: ${TASK_ROOT}/paper_method_v1"

available_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[[ -n ${available_kb} ]] || fail "Unable to determine MemAvailable"
available_gb=$((available_kb / 1024 / 1024))
(( available_gb >= MIN_AVAILABLE_GB )) \
    || fail "Only ${available_gb} GiB available; require at least ${MIN_AVAILABLE_GB} GiB"

{
    printf 'started_at\t%s\n' "$(date -Is)"
    printf 'reason\tinitial_k55_memory_allocation_failure_exit_68\n'
    printf 'initial_exit_marker\t%s\n' "${INITIAL_EXIT}"
    printf 'initial_log\t%s\n' "${INITIAL_LOG}"
    printf 'restart_from\tk55\n'
    printf 'kmer_list\t21,33,55,77,99,127\n'
    printf 'threads\t%s\n' "${THREADS}"
    printf 'memory_limit_gb\t%s\n' "${MEMORY_GB}"
    printf 'available_memory_gib_before_start\t%s\n' "${available_gb}"
    printf 'spades_version\t%s\n' "$("${SPADES_ENV}/bin/metaspades.py" --version 2>&1 | head -1)"
    printf 'pre_restart_params_sha256\t%s\n' "$(sha256sum "${ASSEMBLY_DIR}/params.txt" | cut -d' ' -f1)"
} >"${RECOVERY_PROVENANCE}"

set +e
"${SPADES_ENV}/bin/metaspades.py" --restart-from k55 \
    -k 21,33,55,77,99,127 --threads "${THREADS}" --memory "${MEMORY_GB}" \
    -o "${ASSEMBLY_DIR}" >"${RECOVERY_LOG}" 2>&1
recovery_status=$?
set -e
printf '%s\n' "${recovery_status}" >"${RECOVERY_EXIT}"
{
    printf 'finished_at\t%s\n' "$(date -Is)"
    printf 'recovery_exit_code\t%s\n' "${recovery_status}"
} >>"${RECOVERY_PROVENANCE}"
[[ ${recovery_status} -eq 0 ]] || exit "${recovery_status}"

stage=${K55_SNAPSHOT}.staging.$$
mkdir "${stage}"
for name in before_rr.fasta assembly_graph_after_simplification.gfa final_contigs.fasta \
    first_pe_contigs.fasta strain_graph.gfa scaffolds.fasta scaffolds.paths \
    assembly_graph_with_scaffolds.gfa assembly_graph.fastg final_contigs.paths; do
    [[ ! -f ${ASSEMBLY_DIR}/K55/${name} ]] || cp -a "${ASSEMBLY_DIR}/K55/${name}" "${stage}/"
done
cp -a "${ASSEMBLY_DIR}/params.txt" "${ASSEMBLY_DIR}/run_spades.yaml" "${stage}/"
(
    cd "${stage}"
    find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS
    sha256sum -c SHA256SUMS >/dev/null
)
mv -T -- "${stage}" "${K55_SNAPSHOT}"

"${ABI_REPO}/scripts/cloud/run_scapp_paper_method_validation.sh" \
    >"${TASK_ROOT}/paper_method_v1.launch.log" 2>&1
