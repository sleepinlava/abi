#!/usr/bin/env bash
# ABI 完整环境与全量数据库重建脚本
# 阶段 0: 镜像配置 + 包缓存迁移 + 基础设置
# 阶段 1: 18 个环境并行安装 (清华镜像 + 缓存加速)
# 阶段 2: 全量数据库并行下载 (bakta full 84GB)
# 阶段 3: 验证
# 阶段 4: 自动关机
set -uo pipefail

BIGDISK=/root/autodl-tmp
export ABI_PROJECT_ROOT=${BIGDISK}/abi
export ABI_MAMBA_ROOT=${BIGDISK}/.mamba
export ABI_RESOURCE_ROOT=${BIGDISK}/resources/autoplasm
export ABI_LOG_DIR=${ABI_PROJECT_ROOT}/logs/cloud
export MAMBA_ROOT_PREFIX=${ABI_MAMBA_ROOT}
export CONDA_PKGS_DIRS=${BIGDISK}/.mamba/pkgs
export TMPDIR=${BIGDISK}/.tmp
export PATH="${BIGDISK}/miniconda3/bin:$PATH"

# 国内镜像加速
export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn"

mkdir -p "${ABI_MAMBA_ROOT}/envs" "${ABI_MAMBA_ROOT}/pkgs" "${ABI_RESOURCE_ROOT}" "${ABI_LOG_DIR}" "${TMPDIR}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${ABI_LOG_DIR}/deploy_rebuild_${TIMESTAMP}.log"
touch "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log()  { echo "[$(date +%H:%M:%S)] $*"; }

log "=========================================="
log " ABI 完整环境与全量数据库重建"
log " 开始时间: $(date)"
log "=========================================="
log "Big disk    : ${BIGDISK} ($(df -h ${BIGDISK} | awk 'NR==2{print $4}') 可用)"
log "Mamba root  : ${ABI_MAMBA_ROOT}"
log "Resource dir: ${ABI_RESOURCE_ROOT}"
log "CPU 核心    : $(nproc)"
log "micromamba  : $(micromamba --version 2>/dev/null || echo N/A)"
log "日志文件    : ${LOG_FILE}"
log "=========================================="

# ── 辅助函数 ──
check_python() { [[ -f "$1/bin/python" ]] && return 0 || return 1; }

ALL_ENVS=(
    autoplasm-base autoplasm-qc autoplasm-assembly autoplasm-annotation
    autoplasm-abundance autoplasm-plasmid-detect autoplasm-plasmid-binning
    autoplasm-integronfinder stats autoplasm-visualization autoplasm-nextflow
    abi-qc abi-stats rnaseq amplicon wgs easymeta-p0 easymeta-humann
)

# ============================================================================
# 阶段 0：镜像配置 + 包缓存迁移 + 基础设置
# ============================================================================
log "=========================================="
log " 阶段 0：镜像配置 + 包缓存迁移 + 基础设置"
log "=========================================="

# 0.1 配置国内镜像加速
log "[0.1] 配置国内镜像..."

# conda 镜像（更新已有 .condarc 路径）
if [[ -f ~/.condarc ]]; then
    log "  .condarc 已存在，更新路径..."
else
    log "  创建 .condarc..."
    conda config --add channels conda-forge 2>/dev/null || true
    conda config --add channels bioconda 2>/dev/null || true
    conda config --set show_channel_urls true 2>/dev/null || true
fi

# micromamba 镜像配置（独立于 conda）
cat > ~/.mambarc << 'MAMBAEOF'
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  bioconda: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
channels:
  - conda-forge
  - bioconda
  - defaults
channel_priority: strict
show_channel_urls: true
remote_max_retries: 5
remote_read_timeout_secs: 180
remote_connect_timeout_secs: 60
remote_backoff_factor: 2
envs_dirs:
  - /root/autodl-tmp/.mamba/envs
pkgs_dirs:
  - /root/autodl-tmp/.mamba/pkgs
MAMBAEOF
log "  .mambarc 已配置（清华镜像）"

# pip 镜像
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || true
log "  pip 已配置（清华镜像）"

# 0.2 迁移包缓存
OLD_PKGS="${ABI_PROJECT_ROOT}/.mamba/pkgs"
NEW_PKGS="${ABI_MAMBA_ROOT}/pkgs"

if [[ -d "${OLD_PKGS}" ]] && [[ $(find "${OLD_PKGS}" -type f 2>/dev/null | wc -l) -gt 100 ]]; then
    log "[0.2] 迁移包缓存: ${OLD_PKGS} -> ${NEW_PKGS}"
    old_pkgs_size=$(du -sh "${OLD_PKGS}" 2>/dev/null | cut -f1)
    log "  旧缓存: ${old_pkgs_size}"

    # 如果目标已有部分缓存（之前中断的 rsync），复用
    if [[ -d "${NEW_PKGS}" ]] && [[ $(find "${NEW_PKGS}" -type f 2>/dev/null | wc -l) -gt 50 ]]; then
        log "  目标已有缓存，增量同步..."
        rsync -a --ignore-existing "${OLD_PKGS}/" "${NEW_PKGS}/" 2>/dev/null || {
            log "  rsync 失败，尝试 cp..."
            cp -rn "${OLD_PKGS}/"* "${NEW_PKGS}/" 2>/dev/null || true
        }
    else
        rm -rf "${NEW_PKGS}" 2>/dev/null
        rsync -a "${OLD_PKGS}/" "${NEW_PKGS}/" 2>/dev/null || {
            log "  rsync 失败，尝试 cp..."
            cp -rn "${OLD_PKGS}/"* "${NEW_PKGS}/" 2>/dev/null || true
        }
    fi
    new_pkgs_size=$(du -sh "${NEW_PKGS}" 2>/dev/null | cut -f1)
    log "[0.2] 缓存迁移完成: ${new_pkgs_size}"
else
    log "[0.2] 无旧缓存，跳过迁移"
fi

# 0.3 重新生成 env yml
log "[0.3] 重新生成 envs/*.yml..."
python3 "${ABI_PROJECT_ROOT}/scripts/emit_env_yamls.py" 2>/dev/null \
    && log "[0.3] OK" || log "[0.3] WARN: emit 失败，使用已有文件"

# 0.4 确认 ABI Python 包
log "[0.4] 确认 ABI Python 包..."
if python3 -c "from abi.config import resolved_mamba_root; print(f'  resolved_mamba_root: {resolved_mamba_root()}')" 2>/dev/null; then
    log "[0.4] ABI 包正常"
else
    log "[0.4] 安装 ABI 包..."
    pip install -e "${ABI_PROJECT_ROOT}[dev,report,mcp]" -q 2>&1 | tail -3 || true
fi

# ============================================================================
# 阶段 1：18 个环境并行安装 (利用缓存，极快)
# ============================================================================
log "=========================================="
log " 阶段 1：18 个环境并行安装 (4路并发)"
log "=========================================="

# 检查哪些环境需要安装
TO_INSTALL=()
for env_name in "${ALL_ENVS[@]}"; do
    env_prefix="${ABI_MAMBA_ROOT}/envs/${env_name}"
    if check_python "${env_prefix}"; then
        size=$(du -sh "${env_prefix}" 2>/dev/null | cut -f1)
        log "  SKIP ${env_name} (${size})"
    else
        TO_INSTALL+=("${env_name}")
        # 清理残留
        rm -rf "${env_prefix}" 2>/dev/null
    fi
done

if [[ ${#TO_INSTALL[@]} -eq 0 ]]; then
    log "所有 18 个环境已就绪！"
else
    log "需要安装 ${#TO_INSTALL[@]} 个环境: ${TO_INSTALL[*]}"

    BATCH_SIZE=4
    total=${#TO_INSTALL[@]}
    created=0; failed=0

    for ((i=0; i<total; i+=BATCH_SIZE)); do
        batch_end=$((i + BATCH_SIZE))
        [[ ${batch_end} -gt ${total} ]] && batch_end=${total}
        batch_num=$((i/BATCH_SIZE + 1))

        log "--- 第 ${batch_num} 批 (${i}..$((batch_end-1))): ${TO_INSTALL[@]:i:BATCH_SIZE} ---"
        pids=()

        for ((j=i; j<batch_end; j++)); do
            env_name="${TO_INSTALL[$j]}"
            env_yaml="${ABI_PROJECT_ROOT}/envs/${env_name}.yml"
            env_prefix="${ABI_MAMBA_ROOT}/envs/${env_name}"

            (
                if [[ ! -f "${env_yaml}" ]]; then
                    echo "[FAIL] ${env_name}: yaml 不存在"
                    exit 1
                fi
                echo "[CREATE] ${env_name} 开始..."
                if micromamba create -p "${env_prefix}" -f "${env_yaml}" -y 2>&1 | tail -3; then
                    if check_python "${env_prefix}"; then
                        echo "[OK]   ${env_name}"
                        exit 0
                    else
                        echo "[FAIL] ${env_name}: python 缺失"
                        exit 1
                    fi
                else
                    echo "[FAIL] ${env_name}: micromamba 失败"
                    exit 1
                fi
            ) &
            pids+=($!)
        done

        for pid in "${pids[@]}"; do
            wait ${pid} 2>/dev/null || true
        done

        micromamba clean -afy 2>/dev/null || true
        log "第 ${batch_num} 批完成"
    done
fi

# 环境总览
log "--- 环境状态 ---"
env_ok=0; env_fail=0; failed_list=""
for env_name in "${ALL_ENVS[@]}"; do
    if check_python "${ABI_MAMBA_ROOT}/envs/${env_name}"; then
        size=$(du -sh "${ABI_MAMBA_ROOT}/envs/${env_name}" 2>/dev/null | cut -f1)
        log "  ✅ ${env_name} (${size})"
        ((env_ok++))
    else
        log "  ❌ ${env_name}"
        ((env_fail++))
        failed_list="${failed_list} ${env_name}"
    fi
done
log "环境总计: ${env_ok}/18 OK, ${env_fail} 失败"
[[ -n "${failed_list}" ]] && log "失败列表:${failed_list}"

# 清理旧环境目录
OLD_ENV_DIR="${ABI_PROJECT_ROOT}/.mamba/envs"
if [[ -d "${OLD_ENV_DIR}" ]]; then
    log "清理旧环境目录: ${OLD_ENV_DIR}"
    rm -rf "${OLD_ENV_DIR}" 2>/dev/null && log "  已清理" || log "  清理失败（非致命）"
fi

# R 包
if check_python "${ABI_MAMBA_ROOT}/envs/rnaseq"; then
    log "安装/检查 DESeq2 R 包..."
    bash "${ABI_PROJECT_ROOT}/scripts/setup_rnaseq_env.sh" --mamba-root "${ABI_MAMBA_ROOT}" 2>&1 | tail -5 || log "WARN: DESeq2 可能有问题"
fi

log "Mamba root 总大小: $(du -sh ${ABI_MAMBA_ROOT} 2>/dev/null | cut -f1)"

# ============================================================================
# 阶段 2：全量数据库下载
# ============================================================================
log "=========================================="
log " 阶段 2：全量数据库下载 (bakta full 84GB)"
log "=========================================="

CLOUD_CONFIG="${ABI_LOG_DIR}/cloud_config.yaml"
cat > "${CLOUD_CONFIG}" << 'YAML'
resources:
  root: /root/autodl-tmp/resources/autoplasm
  bakta:
    type: full
    version: full
YAML
log "Cloud config:"
cat "${CLOUD_CONFIG}"

ABI_BIN="${ABI_MAMBA_ROOT}/envs/autoplasm-base/bin/abi"
[[ -x "${ABI_BIN}" ]] || ABI_BIN="abi"
log "ABI binary: ${ABI_BIN}"

run_dbs() {
    local plugin="$1"; local label="$2"
    log ">>> [${plugin}] ${label} 开始..."
    if ${ABI_BIN} setup-resources --type "${plugin}" --confirm --config "${CLOUD_CONFIG}" 2>&1; then
        log "<<< [${plugin}] OK"
        return 0
    else
        log "<<< [${plugin}] FAIL (非致命，继续)"
        return 1
    fi
}

# 第 1 组：3 个轻量插件并行
log "--- 数据库第 1 组: 轻量插件并行 ---"
run_dbs "amplicon_16s" "RDP 16S (~0.2GB)" &
run_dbs "wgs_bacteria" "AMRFinderPlus (~1GB)" &
run_dbs "rnaseq_expression" "DESeq2 (~0.5GB)" &
wait
log "第 1 组完成"

# 第 2 组：metagenomic_plasmid (~210 GB)
log "--- 数据库第 2 组: metagenomic_plasmid 全量 (~210 GB) ---"
log "  genomad(~3GB) + bakta(full 84GB) + mob_suite + plasmidfinder"
log "  metaphlan(~3GB) + amrfinderplus(~1GB) + kraken2(aria2c 8连接 ~50GB)"
log "  gtdbtk(~30GB) + checkm2(~10GB) + eggnog_mapper(~30GB)"
run_dbs "metagenomic_plasmid" "全量数据库 (~210GB)" || log "WARN: metagenomic_plasmid 有失败项"

# 第 3 组：easymetagenome (~50 GB)
log "--- 数据库第 3 组: easymetagenome (~50 GB) ---"
log "  kraken2 + bracken + kneaddata + humann + metaphlan"
run_dbs "easymetagenome" "easyMeta (~50GB)" || log "WARN: easymetagenome 有失败项"

# Tier 2 手动数据库
log "=========================================="
log " Tier 2 手动数据库（需人工下载）"
log "=========================================="
cat << 'MANUAL'
metagenomic_plasmid:  card, abricate, plasme, plasx, copla, blast, plasmidhostfinder
easymetagenome:       host_db, humann_nucleotide, humann_protein
viral_viwrap:         viwrap_db, viwrap_envs
rnaseq/metatx:        genome_index (STAR), annotation_gtf
MANUAL

# ============================================================================
# 阶段 3：验证
# ============================================================================
log "=========================================="
log " 阶段 3：验证"
log "=========================================="

log "--- 环境 ---"
for env_name in "${ALL_ENVS[@]}"; do
    if check_python "${ABI_MAMBA_ROOT}/envs/${env_name}"; then
        size=$(du -sh "${ABI_MAMBA_ROOT}/envs/${env_name}" 2>/dev/null | cut -f1)
        log "  ✅ ${env_name} (${size})"
    else
        log "  ❌ ${env_name}"
    fi
done

log "--- 数据库 ---"
for plugin in metagenomic_plasmid amplicon_16s wgs_bacteria rnaseq_expression metatranscriptomics easymetagenome viral_viwrap; do
    log ">>> check-resources --type ${plugin}"
    ${ABI_BIN} check-resources --type "${plugin}" --config "${CLOUD_CONFIG}" 2>&1 || true
done

log "--- 磁盘使用 ---"
du -sh "${ABI_MAMBA_ROOT}" 2>/dev/null || true
du -sh "${ABI_RESOURCE_ROOT}" 2>/dev/null || true
df -h "${BIGDISK}"

# ============================================================================
# 阶段 4：自动关机
# ============================================================================
log "=========================================="
log " 全流程完成 — $(date)"
log "日志: ${LOG_FILE}"
log "将在 60 秒后自动关机... (Ctrl+C 取消)"
log "=========================================="

sleep 60
log "关机中..."
shutdown -h now || poweroff || log "ERROR: 关机失败，请手动执行 shutdown -h now"
