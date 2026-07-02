#!/usr/bin/env bash
# =============================================================================
# ABI 全量数据库并行下载脚本 v3 (最终版)
# 下载目标: /root/autodl-tmp/resources/autoplasm/
# 总大小:  ~250GB (含 bakta full 84GB)
# 策略:    按大小分批并行，同批跨不同 conda env 避免冲突
# 用法:    screen -L -S abi_dbs bash scripts/cloud/download_all_dbs.sh
# =============================================================================
set -uo pipefail

# ── 常量 ──
# 注意: ABI_MAMBA_ROOT 可能指向错误的项目内路径 (.mamba)，强制使用系统 mamba
MAMBA_ROOT="/root/autodl-tmp/.mamba"
RESOURCE_ROOT="/root/autodl-tmp/resources/autoplasm"
LOG_DIR="/root/autodl-tmp/abi/logs/cloud"
TMPDIR="/root/autodl-tmp/.tmp"

mkdir -p "${RESOURCE_ROOT}" "${LOG_DIR}" "${TMPDIR}"

LOG="${LOG_DIR}/db_download_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${LOG}") 2>&1

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()       { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN${NC} $*"; }
log_error() { echo -e "${RED}[$(date +%H:%M:%S)] ERROR${NC} $*"; }
log_phase() { echo -e "\n${BLUE}═══ $(date +%H:%M:%S) ═══ PHASE: $* ═══${NC}"; }
disk_info() { echo "  Disk: $(df -h /root/autodl-tmp | awk 'NR==2{printf "%s used / %s free", $3, $4}')"; }

# ── 路径辅助 ──
env_exe()  { echo "${MAMBA_ROOT}/envs/$1/bin/$2"; }
env_path() { echo "${MAMBA_ROOT}/envs/$1/bin"; }
env_prefix() { echo "${MAMBA_ROOT}/envs/$1"; }

# ── 检查函数 ──
is_ready() {
    local path="$1"
    [ -f "${path}/.autoplasm_resource_ready" ] && return 0
    [ -f "${path}/.abi_ready" ] && return 0
    return 1
}

git_worktree_valid() {
    [ -d "$1/.git" ] || return 1
    git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

safe_prepare_dir() {
    local path="$1" label="$2"
    if [ -d "${path}" ] && [ "$(ls -A "${path}" 2>/dev/null)" ] && ! is_ready "${path}"; then
        local backup="${path}.bak.$(date +%s)"
        log_warn "${label}: 存在不完整数据，备份到 ${backup}"
        mv "${path}" "${backup}"
    fi
    mkdir -p "${path}"
}

# ── 后台任务 ──
bg_run() {
    local label="$1" logname="$2"; shift 2
    local logfile="${LOG_DIR}/${logname}_$(date +%Y%m%d_%H%M%S).log"
    log "  ▸ [${label}] 启动" >&2
    ("$@" > "${logfile}" 2>&1) &
    echo $!
}

wait_pids() {
    local fail=0
    for label in "${!PIDS[@]}"; do
        local pid="${PIDS[$label]}"
        wait "${pid}" 2>/dev/null
        local rc=$?
        if [ $rc -eq 0 ]; then
            log "  ✔ [${label}] 完成"
        else
            log_error "  ✘ [${label}] 失败 (exit=$rc)"
            fail=1
        fi
    done
    return $fail
}

# ============================================================================
log "╔══════════════════════════════════════════════════════════╗"
log "║  ABI 全量数据库并行下载 v3                                ║"
log "║  Resource root: ${RESOURCE_ROOT}"
log "╚══════════════════════════════════════════════════════════╝"
disk_info

# ── 清理之前 metaphlan --install 的残留下载 ──
METAPHLAN_DEFAULT_DB="${MAMBA_ROOT}/envs/stats/lib/python3.12/site-packages/metaphlan/metaphlan_databases"
if [ -f "${METAPHLAN_DEFAULT_DB}/mpa_vJan25_CHOCOPhlAnSGB_202503_bt2.tar" ]; then
    log "清理 metaphlan 残余下载 (9MB)..."
    rm -f "${METAPHLAN_DEFAULT_DB}/mpa_vJan25_CHOCOPhlAnSGB_202503_bt2.tar"
fi

# ============================================================================
# PHASE 0: 修复已存在的半成品数据库
# ============================================================================
log_phase "0: 修复已存在的半成品数据库"

# 0a. mob_suite — 已有完整数据
MOB_DIR="${RESOURCE_ROOT}/mob_suite"
MOB_SRC="/root/autodl-tmp/abi/MOB_SUITE_DB_NOT_CONFIGURED"
if [ -d "${MOB_SRC}" ] && [ -f "${MOB_SRC}/ncbi_plasmid_full_seqs.fas.nhr" ]; then
    log "0a: mob_suite → 迁移到 ${MOB_DIR}"
    mkdir -p "$(dirname "${MOB_DIR}")"
    rm -rf "${MOB_DIR}"
    mv "${MOB_SRC}" "${MOB_DIR}"
    rm -f "${MOB_DIR}/.lock"
    touch "${MOB_DIR}/.autoplasm_resource_ready"
    log "  ✔ mob_suite ($(du -sh "${MOB_DIR}" | cut -f1))"
fi

# 0b. plasmidfinder — 已 git clone
PF_DIR="${RESOURCE_ROOT}/plasmidfinder_db"
PF_SRC="/root/autodl-tmp/abi/PLASMIDFINDER_DB_NOT_CONFIGURED"
if [ -d "${PF_SRC}/.git" ] && [ -f "${PF_SRC}/config" ]; then
    log "0b: plasmidfinder → 迁移到 ${PF_DIR}"
    mkdir -p "$(dirname "${PF_DIR}")"
    rm -rf "${PF_DIR}"
    mv "${PF_SRC}" "${PF_DIR}"
    if [ -f "${PF_DIR}/INSTALL.py" ]; then
        log "  运行 INSTALL.py..."
        "$(env_exe autoplasm-annotation python)" "${PF_DIR}/INSTALL.py" \
            "$(env_exe autoplasm-annotation kma_index)" \
            >> "${LOG_DIR}/plasmidfinder_install.log" 2>&1 \
            && touch "${PF_DIR}/.autoplasm_resource_ready" \
            && log "  ✔ plasmidfinder 安装完成" \
            || log_error "  ✘ INSTALL.py 失败"
    fi
fi

# 0c. bakta — 解压 db.tar.xz
BAKTA_DIR="${RESOURCE_ROOT}/bakta"
BAKTA_SRC="/root/autodl-tmp/abi/BAKTA_DB_NOT_CONFIGURED/db.tar.xz"
if [ -f "${BAKTA_SRC}" ] && [ "$(stat -c%s "${BAKTA_SRC}" 2>/dev/null || echo 0)" -gt 1000000000 ]; then
    log "0c: bakta db.tar.xz → 解压到 ${BAKTA_DIR}"
    rm -rf "${BAKTA_DIR}"
    mkdir -p "${BAKTA_DIR}"
    if xz -d < "${BAKTA_SRC}" | tar x -C "${BAKTA_DIR}" 2>"${LOG_DIR}/bakta_extract.log"; then
        if [ -f "${BAKTA_DIR}/bakta.db" ]; then
            touch "${BAKTA_DIR}/.autoplasm_resource_ready"
            log "  ✔ bakta 解压完成 ($(du -sh "${BAKTA_DIR}" | cut -f1))"
            rm -f "${BAKTA_SRC}"  # 释放 2.9GB
        else
            log_error "  ✘ 解压后未找到 bakta.db，将重新下载"
            rm -rf "${BAKTA_DIR}"
        fi
    else
        log_error "  ✘ 解压失败，将重新下载"
        rm -rf "${BAKTA_DIR}"
    fi
fi

disk_info

# ============================================================================
# PHASE 1: 小型数据库并行下载
#   checkm2(~400MB) + RDP taxonomy(~50MB) + amrfinderplus(~251MB) + abricate(small)
# ============================================================================
log_phase "Phase 1: 小型数据库并行"

declare -A PIDS=()

# 1a. CheckM2 — stats env
CHECKM2_DIR="${RESOURCE_ROOT}/checkm2"
if ! is_ready "${CHECKM2_DIR}"; then
    safe_prepare_dir "${CHECKM2_DIR}" "checkm2"
    PIDS[checkm2]=$(bg_run "checkm2" "checkm2_db" \
        bash -c "
            export PATH=$(env_path stats):\$PATH
            export CONDA_PREFIX=$(env_prefix stats)
            export CHECKM2DB=${CHECKM2_DIR}
            checkm2 download --path ${CHECKM2_DIR}
            [ -n \"\$(ls -A ${CHECKM2_DIR} 2>/dev/null)\" ] && touch ${CHECKM2_DIR}/.autoplasm_resource_ready
        ")
else
    log "  1a: checkm2 — 已就绪"
fi

# 1b. RDP SINTAX taxonomy
RDP_DIR="${RESOURCE_ROOT}/amplicon_taxonomy"
RDP_FILE="${RDP_DIR}/rdp_16s_v16.fa"
if [ -f "${RDP_FILE}" ]; then
    log "  1b: RDP taxonomy — 已就绪"
else
    mkdir -p "${RDP_DIR}"
    PIDS[rdp]=$(bg_run "RDP" "rdp_taxonomy" \
        bash -c "
            wget -q --show-progress --timeout=300 \
                -O ${RDP_DIR}/rdp_16s_v16_sp.fa.gz \
                'https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz' \
                && gunzip -f ${RDP_DIR}/rdp_16s_v16_sp.fa.gz \
                && touch ${RDP_DIR}/.autoplasm_resource_ready
        ")
fi

# 1c. AMRFinderPlus
AMR_DIR="${RESOURCE_ROOT}/amrfinderplus"
if is_ready "${AMR_DIR}"; then
    log "  1c: amrfinderplus — 已就绪"
else
    safe_prepare_dir "${AMR_DIR}" "amrfinderplus"
    PIDS[amrfinder]=$(bg_run "AMRFinder+" "amrfinderplus_db" \
        bash -c "
            export PATH=$(env_path autoplasm-annotation):\$PATH
            export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
            amrfinder_update -d ${AMR_DIR}
            AMRPROT=\$(find ${AMR_DIR} -name 'AMRProt.fa' 2>/dev/null | head -1)
            if [ -n \"\${AMRPROT}\" ] && [ -f \"\${AMRPROT}\" ]; then
                makeblastdb -in \${AMRPROT} -dbtype prot -out \${AMRPROT}
            fi
            touch ${AMR_DIR}/.autoplasm_resource_ready
        ")
fi

# 1d. ABRicate — 用 conda perl
ABRICATE_DIR="${RESOURCE_ROOT}/abricate"
ABRICATE_EXE="$(env_exe autoplasm-annotation abricate-get_db)"
CONDA_PERL="$(env_exe autoplasm-annotation perl)"
if is_ready "${ABRICATE_DIR}"; then
    log "  1d: abricate — 已就绪"
else
    mkdir -p "${ABRICATE_DIR}"
    PIDS[abricate]=$(bg_run "abricate" "abricate_db" \
        bash -c "
            for db in card resfinder vfdb plasmidfinder; do
                echo \"[abricate] 下载 \$db...\"
                ${CONDA_PERL} ${ABRICATE_EXE} --dbdir ${ABRICATE_DIR} --db \$db --force
            done
            [ -n \"\$(ls -A ${ABRICATE_DIR} 2>/dev/null)\" ] && touch ${ABRICATE_DIR}/.autoplasm_resource_ready
        ")
fi

wait_pids || log_warn "Phase 1 部分失败"
unset PIDS
disk_info

# ============================================================================
# PHASE 2: 中型数据库 + 工具安装
#   genomad(~2.9GB) / mob_suite(~3GB) / plasmidfinder / platon / plasme / plasx
# ============================================================================
log_phase "Phase 2: 中型数据库 + 工具"

declare -A PIDS=()

# 2a. geNomad
GENOMAD_DIR="${RESOURCE_ROOT}/genomad"
if is_ready "${GENOMAD_DIR}" || [ -f "${GENOMAD_DIR}/genomad_db" ]; then
    log "  2a: genomad — 已就绪"
    [ -f "${GENOMAD_DIR}/genomad_db" ] && [ ! -f "${GENOMAD_DIR}/.autoplasm_resource_ready" ] && touch "${GENOMAD_DIR}/.autoplasm_resource_ready"
else
    safe_prepare_dir "${GENOMAD_DIR}" "genomad"
    PIDS[genomad]=$(bg_run "geNomad" "genomad_db" \
        bash -c "
            export PATH=$(env_path autoplasm-plasmid-detect):\$PATH
            export CONDA_PREFIX=$(env_prefix autoplasm-plasmid-detect)
            genomad download-database ${GENOMAD_DIR} \
                && touch ${GENOMAD_DIR}/.autoplasm_resource_ready
        ")
fi

# 2b. mob_suite
if ! is_ready "${MOB_DIR}"; then
    safe_prepare_dir "${MOB_DIR}" "mob_suite"
    PIDS[mob_suite]=$(bg_run "mob_suite" "mob_suite_db" \
        bash -c "
            export PATH=$(env_path autoplasm-annotation):\$PATH
            export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
            mob_init --database_directory ${MOB_DIR}
            if ls ${MOB_DIR}/*.nhr >/dev/null 2>&1 || ls ${MOB_DIR}/*.phr >/dev/null 2>&1; then
                touch ${MOB_DIR}/.autoplasm_resource_ready
            fi
        ")
else
    log "  2b: mob_suite — 已就绪"
fi

# 2c. plasmidfinder
if ! is_ready "${PF_DIR}"; then
    rm -rf "${PF_DIR}"
    PIDS[plasmidfinder]=$(bg_run "PlasmidFinder" "plasmidfinder_db" \
        bash -c "
            git clone --depth 1 --single-branch https://bitbucket.org/genomicepidemiology/plasmidfinder_db.git ${PF_DIR}
            PY=$(env_exe autoplasm-annotation python)
            KMA=$(env_exe autoplasm-annotation kma_index)
            if [ -f ${PF_DIR}/INSTALL.py ]; then
                \${PY} ${PF_DIR}/INSTALL.py \${KMA}
            fi
            touch ${PF_DIR}/.autoplasm_resource_ready
        ")
else
    log "  2c: plasmidfinder — 已就绪"
fi

# 2d. PLASMe tool
PLASME_DIR="${RESOURCE_ROOT}/PLASMe"
PLASME_PIP="$(env_exe autoplasm-plasmid-detect pip)"
if git_worktree_valid "${PLASME_DIR}"; then
    log "  2d: PLASMe — 已 clone"
else
    rm -rf "${PLASME_DIR}"
    PIDS[plasme]=$(bg_run "PLASMe" "plasme_tool" \
        bash -c "
            git clone --depth 1 --single-branch https://github.com/ccb-hms/PLASMe.git ${PLASME_DIR}
            cd ${PLASME_DIR} && ${PLASME_PIP} install -e . --quiet
        ")
fi

# 2e. Platon tool
PLATON_DIR="${RESOURCE_ROOT}/platon"
PLATON_PIP="$(env_exe autoplasm-plasmid-detect pip)"
if git_worktree_valid "${PLATON_DIR}"; then
    log "  2e: Platon — 已 clone"
else
    rm -rf "${PLATON_DIR}"
    PIDS[platon]=$(bg_run "Platon" "platon_tool" \
        bash -c "
            git clone --depth 1 --single-branch https://github.com/oschwengers/platon.git ${PLATON_DIR}
            cd ${PLATON_DIR} && ${PLATON_PIP} install -e . --quiet
        ")
fi

# 2f. PlasX tool
PLASX_DIR="${RESOURCE_ROOT}/PlasX"
PLASX_PIP="$(env_exe autoplasm-plasmid-detect pip)"
if git_worktree_valid "${PLASX_DIR}"; then
    log "  2f: PlasX — 已 clone"
else
    rm -rf "${PLASX_DIR}"
    PIDS[plasx]=$(bg_run "PlasX" "plasx_tool" \
        bash -c "
            git clone --depth 1 --single-branch https://github.com/michaelgoldman/PlasX.git ${PLASX_DIR}
            cd ${PLASX_DIR} && ${PLASX_PIP} install -e . --quiet
        ")
fi

wait_pids || log_warn "Phase 2 部分失败"
unset PIDS
disk_info

# ============================================================================
# PHASE 3: 3个大型数据库并行 (~168GB)
#   bakta full(84GB) | metaphlan(34GB) | kraken2(50GB)
# ============================================================================
log_phase "Phase 3: 大型数据库并行 — bakta / metaphlan / kraken2"

declare -A PIDS=()

# 3a. MetaPhlAn — stats env
METAPHLAN_DIR="${RESOURCE_ROOT}/metaphlan"
if is_ready "${METAPHLAN_DIR}"; then
    log "  3a: metaphlan — 已就绪"
else
    mkdir -p "${METAPHLAN_DIR}"
    PIDS[metaphlan]=$(bg_run "MetaPhlAn" "metaphlan_db" \
        bash -c "
            export PATH=$(env_path stats):\$PATH
            export CONDA_PREFIX=$(env_prefix stats)
            metaphlan --install --bowtie2db ${METAPHLAN_DIR} --nproc 8 \
                && touch ${METAPHLAN_DIR}/.autoplasm_resource_ready
        ")
fi

# 3b. Bakta Full
if is_ready "${BAKTA_DIR}" && [ -f "${BAKTA_DIR}/bakta.db" ]; then
    log "  3b: bakta — 已就绪"
else
    safe_prepare_dir "${BAKTA_DIR}" "bakta"
    PIDS[bakta]=$(bg_run "Bakta" "bakta_full_db" \
        bash -c "
            export PATH=$(env_path autoplasm-annotation):\$PATH
            export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
            bakta_db download --output ${BAKTA_DIR} --type full \
                && touch ${BAKTA_DIR}/.autoplasm_resource_ready
        ")
fi

# 3c. Kraken2 — aria2c
KRAKEN2_VERSION="standard_20260226"
KRAKEN2_DIR="${RESOURCE_ROOT}/kraken2"
KRAKEN2_URL="https://genome-idx.s3.amazonaws.com/kraken/k2_${KRAKEN2_VERSION}.tar.gz"
K2_PARENT="$(dirname "${KRAKEN2_DIR}")"

if is_ready "${KRAKEN2_DIR}" && [ -d "${KRAKEN2_DIR}/taxonomy" ] && [ -d "${KRAKEN2_DIR}/library" ]; then
    log "  3c: kraken2 — 已就绪"
elif [ -f "${K2_PARENT}/kraken2.tar.gz.part" ] && pgrep -x aria2c >/dev/null 2>&1; then
    log "  3c: kraken2 — 检测到正在运行的 aria2c (PID=$(pgrep -x aria2c | tr '\n' ' '))，沿用现有下载，跳过本段"
    log "    注：现有 aria2c 完成后会自动 tar/mv/touch .autoplasm_resource_ready"
elif [ -f "${K2_PARENT}/kraken2.tar.gz.part" ] && [ -f "${K2_PARENT}/kraken2.tar.gz.part.aria2" ]; then
    log "  3c: kraken2 — 有未完成 .part 但无 aria2c 进程，断点续传"
    mkdir -p "${K2_PARENT}"
    PIDS[kraken2]=$(bg_run "Kraken2" "kraken2_db" \
        bash -c "
            ARIA2C=$(env_exe autoplasm-base aria2c)
            TARBALL=${K2_PARENT}/kraken2.tar.gz.part
            STAGING=${K2_PARENT}/kraken2.staging

            echo '[kraken2] aria2c 续传 (x8)...'
            \${ARIA2C} -x 8 -s 8 --continue=true --max-tries=3 --retry-wait=5 \
                -d ${K2_PARENT} -o kraken2.tar.gz.part \
                '${KRAKEN2_URL}'
            echo '[kraken2] 解压...'
            mkdir -p \${STAGING}
            tar xzf \${TARBALL} -C \${STAGING}
            echo '[kraken2] 原子交换...'
            rm -rf ${KRAKEN2_DIR}
            mv \${STAGING} ${KRAKEN2_DIR}
            rm -f \${TARBALL}
            touch ${KRAKEN2_DIR}/.autoplasm_resource_ready
            echo '[kraken2] 完成'
        ")
else
    mkdir -p "${K2_PARENT}"
    PIDS[kraken2]=$(bg_run "Kraken2" "kraken2_db" \
        bash -c "
            ARIA2C=$(env_exe autoplasm-base aria2c)
            TARBALL=${K2_PARENT}/kraken2.tar.gz.part
            STAGING=${K2_PARENT}/kraken2.staging
            rm -f \${TARBALL}
            rm -rf \${STAGING} ${KRAKEN2_DIR}

            echo '[kraken2] aria2c 下载 (x8)...'
            \${ARIA2C} -x 8 -s 8 --continue=true --max-tries=3 --retry-wait=5 \
                -d ${K2_PARENT} -o kraken2.tar.gz.part \
                '${KRAKEN2_URL}'
            echo '[kraken2] 解压...'
            mkdir -p \${STAGING}
            tar xzf \${TARBALL} -C \${STAGING}
            echo '[kraken2] 原子交换...'
            mv \${STAGING} ${KRAKEN2_DIR}
            rm -f \${TARBALL}
            touch ${KRAKEN2_DIR}/.autoplasm_resource_ready
            echo '[kraken2] 完成'
        ")
fi

wait_pids || log_warn "Phase 3 部分失败"
unset PIDS
disk_info

# ============================================================================
# PHASE 4: gtdbtk(30GB) + eggnog_mapper(30GB)
# ============================================================================
log_phase "Phase 4: gtdbtk / eggnog_mapper"

declare -A PIDS=()

# 4a. GTDB-Tk
GTDBTK_DIR="${RESOURCE_ROOT}/gtdbtk"
if is_ready "${GTDBTK_DIR}" && [ -d "${GTDBTK_DIR}/markers" ]; then
    log "  4a: gtdbtk — 已就绪"
else
    safe_prepare_dir "${GTDBTK_DIR}" "gtdbtk"
    PIDS[gtdbtk]=$(bg_run "GTDB-Tk" "gtdbtk_db" \
        bash -c "
            export PATH=$(env_path stats):\$PATH
            export CONDA_PREFIX=$(env_prefix stats)
            export GTDBTK_DATA_PATH=${GTDBTK_DIR}
            gtdbtk db download \
                && touch ${GTDBTK_DIR}/.autoplasm_resource_ready
        ")
fi

# 4b. eggNOG-mapper
EGGNOG_DIR="${RESOURCE_ROOT}/eggnog_mapper"
if is_ready "${EGGNOG_DIR}"; then
    log "  4b: eggnog_mapper — 已就绪"
else
    safe_prepare_dir "${EGGNOG_DIR}" "eggnog_mapper"
    PIDS[eggnog]=$(bg_run "eggNOG" "eggnog_db" \
        bash -c "
            export PATH=$(env_path autoplasm-annotation):\$PATH
            export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
            download_eggnog_data.py -y --data_dir ${EGGNOG_DIR} \
                && touch ${EGGNOG_DIR}/.autoplasm_resource_ready
        ")
fi

wait_pids || log_warn "Phase 4 部分失败"
unset PIDS
disk_info

# ============================================================================
# PHASE 5: easyMetagenome 数据库
#   kneaddata host(3GB) + HUMAnN chocophlan(5GB) + uniref(3GB)
# ============================================================================
log_phase "Phase 5: easyMetagenome (kneaddata / HUMAnN)"

declare -A PIDS=()

# 5a. KneadData host
KNEAD_DIR="${RESOURCE_ROOT}/kneaddata_host"
if is_ready "${KNEAD_DIR}"; then
    log "  5a: kneaddata host — 已就绪"
else
    mkdir -p "${KNEAD_DIR}"
    PIDS[kneaddata]=$(bg_run "KneadData" "kneaddata_db" \
        bash -c "
            export PATH=$(env_path easymeta-p0):\$PATH
            export CONDA_PREFIX=$(env_prefix easymeta-p0)
            kneaddata_database --download human_genome bowtie2 ${KNEAD_DIR} \
                && touch ${KNEAD_DIR}/.autoplasm_resource_ready
        ")
fi

# 5b. HUMAnN ChocoPhlAn
HUMANN_NUC="${RESOURCE_ROOT}/humann/chocophlan"
if is_ready "${HUMANN_NUC}"; then
    log "  5b: HUMAnN chocophlan — 已就绪"
else
    mkdir -p "${HUMANN_NUC}"
    PIDS[humann_nuc]=$(bg_run "HUMAnN-nuc" "humann_nuc_db" \
        bash -c "
            export PATH=$(env_path easymeta-humann):\$PATH
            export CONDA_PREFIX=$(env_prefix easymeta-humann)
            humann_databases --download chocophlan full ${HUMANN_NUC} \
                && touch ${HUMANN_NUC}/.autoplasm_resource_ready
        ")
fi

# 5c. HUMAnN UniRef90
HUMANN_PROT="${RESOURCE_ROOT}/humann/uniref"
if is_ready "${HUMANN_PROT}"; then
    log "  5c: HUMAnN uniref — 已就绪"
else
    mkdir -p "${HUMANN_PROT}"
    PIDS[humann_prot]=$(bg_run "HUMAnN-prot" "humann_prot_db" \
        bash -c "
            export PATH=$(env_path easymeta-humann):\$PATH
            export CONDA_PREFIX=$(env_prefix easymeta-humann)
            humann_databases --download uniref uniref90_diamond ${HUMANN_PROT} \
                && touch ${HUMANN_PROT}/.autoplasm_resource_ready
        ")
fi

wait_pids || log_warn "Phase 5 部分失败"
unset PIDS
disk_info

# ============================================================================
# PHASE 6: CARD/RGI
# ============================================================================
log_phase "Phase 6: CARD/RGI"

CARD_DIR="${RESOURCE_ROOT}/card"
if is_ready "${CARD_DIR}"; then
    log "  6: CARD — 已就绪"
else
    mkdir -p "${CARD_DIR}"
    log "  加载 CARD 数据库 (需访问 card.mcmaster.ca)..."
    bash -c "
        export PATH=$(env_path autoplasm-annotation):\$PATH
        export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
        rgi load --card_json ${CARD_DIR}/card.json --local
    " > "${LOG_DIR}/card_db.log" 2>&1
    if [ -n "$(ls -A "${CARD_DIR}" 2>/dev/null)" ]; then
        touch "${CARD_DIR}/.autoplasm_resource_ready"
        log "  ✔ CARD 加载完成"
    else
        log_warn "  ✘ CARD 下载失败 — 手动: https://card.mcmaster.ca/download"
    fi
fi

disk_info

# ============================================================================
# 最终汇总
# ============================================================================
log_phase "下载完成 — 汇总"

report_db() {
    local name="$1" path="$2" check="$3"
    local status="✘ MISSING" size=""
    if [ -e "${path}" ]; then
        size=$(du -sh "${path}" 2>/dev/null | cut -f1)
        if [ -n "${check}" ] && [ -e "${path}/${check}" ]; then
            status="✔ READY"
        elif [ -f "${path}/.autoplasm_resource_ready" ]; then
            status="✔ READY"
        elif [ -f "${path}/.abi_ready" ]; then
            status="✔ READY"
        elif [ -n "$(ls -A "${path}" 2>/dev/null)" ]; then
            status="◐ PARTIAL"
        else
            status="✘ EMPTY"
        fi
    fi
    printf "║  %-30s  %-18s %8s  ║\n" "${name}" "${status}" "${size:-N/A}"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Database                       Status             Size      ║"
echo "╠══════════════════════════════════════════════════════════════╣"

report_db "genomad"            "${GENOMAD_DIR}"       "genomad_db"
report_db "bakta"              "${BAKTA_DIR}"         "bakta.db"
report_db "mob_suite"          "${MOB_DIR}"           ""
report_db "plasmidfinder"      "${PF_DIR}"            "config"
report_db "metaphlan"          "${METAPHLAN_DIR}"     ""
report_db "amrfinderplus"      "${AMR_DIR}"           ""
report_db "kraken2"            "${KRAKEN2_DIR}"       "taxonomy"
report_db "gtdbtk"             "${GTDBTK_DIR}"        "markers"
report_db "checkm2"            "${CHECKM2_DIR}"       ""
report_db "eggnog_mapper"      "${EGGNOG_DIR}"        ""
report_db "abricate"           "${ABRICATE_DIR}"      ""
report_db "RDP taxonomy"       "${RDP_DIR}"           "rdp_16s_v16.fa"
report_db "card (RGI)"         "${CARD_DIR}"          ""
report_db "kneaddata host"     "${KNEAD_DIR}"         ""
report_db "HUMAnN chocophlan"  "${HUMANN_NUC}"        ""
report_db "HUMAnN uniref"      "${HUMANN_PROT}"       ""
report_db "PLASMe tool"        "${PLASME_DIR}"        ".git"
report_db "Platon tool"        "${PLATON_DIR}"        ".git"
report_db "PlasX tool"         "${PLASX_DIR}"         ".git"

echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Resource root: ${RESOURCE_ROOT}"
echo "  主日志: ${LOG}"
echo "  子日志: ${LOG_DIR}/"
disk_info
echo ""
log "全量数据库下载完成 — $(date)"
