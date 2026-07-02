#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENVS_DIR="${PROJECT_ROOT}/envs"
MAMBA_ROOT="${PROJECT_ROOT}/.mamba"
LOG_DIR="${PROJECT_ROOT}/log"
mkdir -p "${LOG_DIR}"

echo "[$(date '+%H:%M:%S')] Starting parallel conda environment installation (10 threads)..."

install_env() {
    local yaml="$1"
    local name
    name=$(basename "$yaml" .yml)
    local log="${LOG_DIR}/conda_${name}.log"

    if [[ -d "${MAMBA_ROOT}/envs/${name}" ]]; then
        echo "[SKIP] ${name} already exists"
        return 0
    fi

    echo "[INSTALL] ${name} starting..."
    mamba env create -f "$yaml" &>"${log}"
    local ret=$?
    if [[ $ret -eq 0 ]]; then
        echo "[DONE] ${name} installed successfully"
    else
        echo "[FAIL] ${name} failed (exit=$ret). Check ${log}"
    fi
    return $ret
}

ENV_FILES=()
for f in "${ENVS_DIR}"/*.yml; do
    ENV_FILES+=("$f")
done

total=${#ENV_FILES[@]}
echo "Total environments to install: ${total}"

# Run in parallel with max 10 jobs
MAX_JOBS=10
count=0
pids=()

for yaml in "${ENV_FILES[@]}"; do
    install_env "$yaml" &
    pid=$!
    pids+=("$pid")
    count=$((count + 1))

    # If we've reached MAX_JOBS, wait for one to finish
    if [[ $count -ge $MAX_JOBS ]]; then
        wait -n 2>/dev/null || true
        running=()
        count=0
        # Re-count running jobs
        for p in "${pids[@]}"; do
            if kill -0 "$p" 2>/dev/null; then
                running+=("$p")
                count=$((count + 1))
            fi
        done
        pids=("${running[@]}")
    fi
done

# Wait for remaining jobs
wait

echo "[$(date '+%H:%M:%S')] All environment installations complete."
echo "Check logs in ${LOG_DIR}/conda_*.log for details."
