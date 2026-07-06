#!/usr/bin/env bash
# ABI 全量数据库下载脚本（screen 运行）
set -uo pipefail

export ABI_PROJECT_ROOT=/root/autodl-tmp/abi
export ABI_MAMBA_ROOT=/root/autodl-tmp/.mamba
export ABI_RESOURCE_ROOT=/root/autodl-tmp/resources/autoplasm
export ABI_LOG_DIR=${ABI_PROJECT_ROOT}/logs/cloud
export TMPDIR=/root/autodl-tmp/.tmp
export PATH="/root/autodl-tmp/miniconda3/bin:$PATH"

mkdir -p "${ABI_RESOURCE_ROOT}" "${ABI_LOG_DIR}" "${TMPDIR}"

LOG="${ABI_LOG_DIR}/db_download_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${LOG}") 2>&1

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=========================================="
log " ABI 全量数据库下载"
log "=========================================="
log "Resource root: ${ABI_RESOURCE_ROOT}"
log "磁盘可用: $(df -h /root/autodl-tmp | awk 'NR==2{print $4}')"
log "日志: ${LOG}"
log "=========================================="

# Cloud config（bakta full）
CLOUD_CONFIG="/tmp/cloud_config_db.yaml"
cat > "${CLOUD_CONFIG}" << 'YAML'
resources:
  root: /root/autodl-tmp/resources/autoplasm
  bakta:
    type: full
    version: full
YAML

ABI="/root/autodl-tmp/.mamba/envs/autoplasm-base/bin/abi"
log "ABI: ${ABI}"

# ── 第 1 组：轻量插件并行 ──
log "--- [1/3] 轻量插件 ---"
${ABI} setup-resources --type amplicon_16s --confirm --config "${CLOUD_CONFIG}" &
PID1=$!
${ABI} setup-resources --type wgs_bacteria --confirm --config "${CLOUD_CONFIG}" &
PID2=$!
wait ${PID1} ${PID2}
log "第 1 组完成"

# ── 第 2 组：metagenomic_plasmid 全量 ~210GB ──
log "--- [2/3] metagenomic_plasmid 全量 (~210GB) ---"
log "  genomad + bakta(full 84GB) + mob_suite + plasmidfinder"
log "  metaphlan + amrfinderplus + kraken2(50GB) + gtdbtk(30GB)"
log "  checkm2(10GB) + eggnog_mapper(30GB)"
${ABI} setup-resources --type metagenomic_plasmid --confirm --config "${CLOUD_CONFIG}"
log "第 2 组: exit=$?"

# ── 第 3 组：easymetagenome ~50GB ──
log "--- [3/3] easymetagenome (~50GB) ---"
${ABI} setup-resources --type easymetagenome --confirm --config "${CLOUD_CONFIG}"
log "第 3 组: exit=$?"

# ── 验证 ──
log "=========================================="
log " 验证"
log "=========================================="
for plugin in metagenomic_plasmid amplicon_16s wgs_bacteria easymetagenome; do
    log ">>> ${plugin}"
    ${ABI} check-resources --type "${plugin}" --config "${CLOUD_CONFIG}" 2>&1 | head -20
done

log "--- 磁盘使用 ---"
du -sh "${ABI_RESOURCE_ROOT}" 2>/dev/null
df -h /root/autodl-tmp

log "=========================================="
log " 数据库下载完成 — $(date)"
log "=========================================="
