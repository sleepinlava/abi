#!/usr/bin/env bash
# Preserve the default-k snapshot, extend MetaSPAdes through K127, then validate.
set -euo pipefail

ABI_REPO=${ABI_REPO:-/root/autodl-tmp/abi}
TASK_ROOT=${TASK_ROOT:-/root/autodl-tmp/abi-real-data/references/scapp/independent_truth_20260717}
ASSEMBLY_DIR=${ASSEMBLY_DIR:-${TASK_ROOT}/metaspades_screen}
INITIAL_EXIT=${INITIAL_EXIT:-${TASK_ROOT}/metaspades_screen.exit_code}
RESTART_EXIT=${RESTART_EXIT:-${TASK_ROOT}/metaspades_k127_restart.exit_code}
SPADES_ENV=${SPADES_ENV:-/root/autodl-tmp/.mamba/envs/autoplasm-assembly}
POLL_SECONDS=${POLL_SECONDS:-30}

while [[ ! -f ${INITIAL_EXIT} ]]; do
    sleep "${POLL_SECONDS}"
done
[[ $(<"${INITIAL_EXIT}") == 0 ]] || { printf 'Initial MetaSPAdes failed: %s\n' "$(<"${INITIAL_EXIT}")" >&2; exit 10; }

snapshot=${TASK_ROOT}/metaspades_default_k_snapshot
[[ ! -e ${snapshot} ]] || { printf 'Snapshot already exists: %s\n' "${snapshot}" >&2; exit 11; }
mkdir "${snapshot}"
for name in contigs.fasta scaffolds.fasta assembly_graph.fastg assembly_graph_with_scaffolds.gfa \
    params.txt spades.log; do
    [[ ! -f ${ASSEMBLY_DIR}/${name} ]] || cp -a "${ASSEMBLY_DIR}/${name}" "${snapshot}/"
done
(
    cd "${snapshot}"
    find . -type f -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS
)

rm -f -- "${RESTART_EXIT}"
set +e
"${SPADES_ENV}/bin/metaspades.py" --restart-from k55 \
    -k 21,33,55,77,99,127 --threads 16 --memory 100 -o "${ASSEMBLY_DIR}" \
    >"${TASK_ROOT}/metaspades_k127_restart.launch.log" 2>&1
restart_status=$?
set -e
printf '%s\n' "${restart_status}" >"${RESTART_EXIT}"
[[ ${restart_status} -eq 0 ]] || exit "${restart_status}"

"${ABI_REPO}/scripts/cloud/run_scapp_paper_method_validation.sh" \
    >"${TASK_ROOT}/paper_method_v1.launch.log" 2>&1
