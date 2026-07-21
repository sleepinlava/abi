#!/usr/bin/env bash
# Reconstruct SCAPP truth with the published thresholds and score ABI predictions.
set -euo pipefail

ABI_REPO=${ABI_REPO:-/root/autodl-tmp/abi}
TASK_ROOT=${TASK_ROOT:-/root/autodl-tmp/abi-real-data/references/scapp/independent_truth_20260717}
ASSEMBLY_DIR=${ASSEMBLY_DIR:-${TASK_ROOT}/metaspades_screen}
PLSDB_FASTA=${PLSDB_FASTA:-/root/autodl-tmp/abi-real-data/references/scapp/plsdb_2018_12_05/plsdb_2018_12_05.fasta}
SCAPP_SUPPLEMENT=${SCAPP_SUPPLEMENT:-/root/autodl-tmp/abi-real-data/references/scapp/SCAPP_supplementary_methods.pdf}
PLSDB_DUPLICATE_SCAN=${PLSDB_DUPLICATE_SCAN:-/root/autodl-tmp/abi-real-data/references/scapp/plsdb_2018_12_05/exact_duplicate_groups.tsv}
PREDICTIONS_FASTA=${PREDICTIONS_FASTA:-/root/autodl-tmp/abi-real-data/results/plasmid_scapp_core_retry7/04_plasmid_detection/SRR11038083/plasmid_contigs.fasta}
OUTPUT_DIR=${OUTPUT_DIR:-${TASK_ROOT}/paper_method_v1}
THREADS=${THREADS:-16}
BLAST_ENV=${BLAST_ENV:-/root/autodl-tmp/.mamba/envs/autoplasm-assembly}
PYTHON=${PYTHON:-/root/miniconda3/bin/python}

BLASTN=${BLAST_ENV}/bin/blastn
MAKEBLASTDB=${BLAST_ENV}/bin/makeblastdb
CONTIGS_FASTA=${ASSEMBLY_DIR}/contigs.fasta
stage=${OUTPUT_DIR}.staging.$$

cleanup() {
    if [[ -d ${stage} ]]; then
        rm -rf -- "${stage}"
    fi
}
trap cleanup EXIT

for path in "${CONTIGS_FASTA}" "${PLSDB_FASTA}" "${PREDICTIONS_FASTA}" \
    "${ABI_REPO}/scripts/reconstruct_scapp_truth.py" \
    "${ABI_REPO}/scripts/score_scapp_predictions.py" \
    "${ABI_REPO}/scripts/build_scapp_machine_evidence.py" \
    "${BLASTN}" "${MAKEBLASTDB}"; do
    [[ -s ${path} ]] || { printf 'Required input is missing or empty: %s\n' "${path}" >&2; exit 2; }
done
[[ ! -e ${OUTPUT_DIR} ]] || { printf 'Immutable output already exists: %s\n' "${OUTPUT_DIR}" >&2; exit 3; }

mkdir -p "${stage}/blastdb/plsdb" "${stage}/blastdb/truth" "${stage}/logs"
"${MAKEBLASTDB}" -in "${PLSDB_FASTA}" -dbtype nucl \
    -out "${stage}/blastdb/plsdb/plsdb" >"${stage}/logs/makeblastdb_plsdb.log" 2>&1
"${BLASTN}" -query "${CONTIGS_FASTA}" -db "${stage}/blastdb/plsdb/plsdb" \
    -out "${stage}/contigs_to_plsdb.tsv" \
    -outfmt '6 qseqid qlen sseqid slen pident length qstart qend sstart send bitscore' \
    -max_target_seqs 20000 -num_threads "${THREADS}" \
    >"${stage}/logs/blastn_contigs_to_plsdb.stdout.log" \
    2>"${stage}/logs/blastn_contigs_to_plsdb.stderr.log"
"${PYTHON}" "${ABI_REPO}/scripts/reconstruct_scapp_truth.py" \
    --blast-tsv "${stage}/contigs_to_plsdb.tsv" \
    --fasta "${PLSDB_FASTA}" \
    --coverage-tsv "${stage}/truth_reference_coverage.tsv" \
    --pair-coverage-tsv "${stage}/truth_contig_reference_pairs.tsv" \
    --summary-json "${stage}/truth_summary.json" \
    --selected-fasta "${stage}/scapp_truth_paper_method.fasta" \
    --min-identity 85 --min-contig-coverage 0.85 --min-reference-coverage 0.90 \
    >"${stage}/logs/reconstruct_truth.log" 2>&1
[[ -s ${stage}/scapp_truth_paper_method.fasta ]] || { printf 'Truth reconstruction selected zero references\n' >&2; exit 4; }

"${MAKEBLASTDB}" -in "${stage}/scapp_truth_paper_method.fasta" -dbtype nucl \
    -out "${stage}/blastdb/truth/truth" >"${stage}/logs/makeblastdb_truth.log" 2>&1
"${BLASTN}" -query "${PREDICTIONS_FASTA}" -db "${stage}/blastdb/truth/truth" \
    -out "${stage}/predictions_to_truth.tsv" \
    -outfmt '6 qseqid qlen sseqid slen pident length qstart qend sstart send bitscore' \
    -max_target_seqs 20000 -num_threads "${THREADS}" \
    >"${stage}/logs/blastn_predictions_to_truth.stdout.log" \
    2>"${stage}/logs/blastn_predictions_to_truth.stderr.log"
"${PYTHON}" "${ABI_REPO}/scripts/score_scapp_predictions.py" \
    --blast-tsv "${stage}/predictions_to_truth.tsv" \
    --predictions-fasta "${PREDICTIONS_FASTA}" \
    --truth-fasta "${stage}/scapp_truth_paper_method.fasta" \
    --output-dir "${stage}" --min-identity 80 --min-coverage 0.90 \
    >"${stage}/logs/score_predictions.log" 2>&1

{
    printf 'created_at\t%s\n' "$(date -Is)"
    printf 'assembly_dir\t%s\n' "${ASSEMBLY_DIR}"
    printf 'abi_git_commit\t%s\n' "$(git -C "${ABI_REPO}" rev-parse HEAD)"
    if [[ -n $(git -C "${ABI_REPO}" status --porcelain) ]]; then
        printf 'abi_git_dirty\ttrue\n'
    else
        printf 'abi_git_dirty\tfalse\n'
    fi
    printf 'truth_builder_sha256\t%s\n' "$(sha256sum "${ABI_REPO}/scripts/reconstruct_scapp_truth.py" | cut -d' ' -f1)"
    printf 'prediction_scorer_sha256\t%s\n' "$(sha256sum "${ABI_REPO}/scripts/score_scapp_predictions.py" | cut -d' ' -f1)"
    printf 'evidence_builder_sha256\t%s\n' "$(sha256sum "${ABI_REPO}/scripts/build_scapp_machine_evidence.py" | cut -d' ' -f1)"
    printf 'assembly_contigs_sha256\t%s\n' "$(sha256sum "${CONTIGS_FASTA}" | cut -d' ' -f1)"
    printf 'plsdb_fasta_sha256\t%s\n' "$(sha256sum "${PLSDB_FASTA}" | cut -d' ' -f1)"
    printf 'predictions_fasta_sha256\t%s\n' "$(sha256sum "${PREDICTIONS_FASTA}" | cut -d' ' -f1)"
    printf 'plsdb_input_records\t%s\n' "$(grep -c '^>' "${PLSDB_FASTA}")"
    printf 'paper_reported_deduplicated_plsdb_records\t13469\n'
    printf 'database_scope_note\tOfficial 2018-12-05 archive contains 14739 records; the paper-specific 13469-record deduplication list was not published.\n'
    if [[ -s ${SCAPP_SUPPLEMENT} ]]; then
        printf 'scapp_supplement_sha256\t%s\n' "$(sha256sum "${SCAPP_SUPPLEMENT}" | cut -d' ' -f1)"
    fi
    if [[ -s ${PLSDB_DUPLICATE_SCAN} ]]; then
        printf 'plsdb_exact_duplicate_scan_sha256\t%s\n' "$(sha256sum "${PLSDB_DUPLICATE_SCAN}" | cut -d' ' -f1)"
    fi
    printf 'spades_version\t%s\n' "$("${BLAST_ENV}/bin/metaspades.py" --version 2>&1 | head -1)"
    printf 'blastn_version\t%s\n' "$("${BLASTN}" -version | head -1)"
    printf 'threads\t%s\n' "${THREADS}"
    printf 'blast_max_target_seqs\t20000\n'
} >"${stage}/run_provenance.tsv"
"${PYTHON}" "${ABI_REPO}/scripts/build_scapp_machine_evidence.py" \
    --output-dir "${stage}" >"${stage}/logs/build_machine_evidence.log" 2>&1
# BLAST databases are deterministic caches derived from frozen FASTA inputs.
# Remove them before publication; retain the HSP tables and their checksums.
rm -rf -- "${stage}/blastdb"
printf 'complete\n' >"${stage}/VALIDATION_COMPLETE"
(
    cd "${stage}"
    find . -type f ! -path './blastdb/*' ! -name SHA256SUMS -print0 \
        | sort -z | xargs -0 sha256sum >SHA256SUMS
    sha256sum -c SHA256SUMS >/dev/null
)
mv -T -- "${stage}" "${OUTPUT_DIR}"
trap - EXIT
printf 'Published paper-method SCAPP validation: %s\n' "${OUTPUT_DIR}"
