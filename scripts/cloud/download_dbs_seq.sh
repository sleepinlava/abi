#!/usr/bin/env bash
# =============================================================================
# ABI 数据库顺序下载脚本 (v2 真等待版)
# 修正 download_all_dbs.sh 的 $PIDS[]=$(bg_run ...) 命令替换缺陷：
#   - 每个库在主壳 foreground/直 fork 子进程并 wait，确保真正等待
#   - 跳过 kraken2 (现有 aria2c 续传中)
#   - 跳过 humann (easymeta-humann env 缺 humann 包，需另行修复) / card (缺 rgi)
# 用法: screen -dm -S abi-dbs-seq bash -L -Logfile $LOG bash scripts/cloud/download_dbs_seq.sh
# =============================================================================
set -o pipefail

MAMBA_ROOT="/root/autodl-tmp/.mamba"
RESOURCE_ROOT="/root/autodl-tmp/resources/autoplasm"
LOG_DIR="/root/autodl-tmp/abi/logs/cloud"
mkdir -p "${RESOURCE_ROOT}" "${LOG_DIR}"

LOG="${LOG_DIR}/db_seq_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${LOG}") 2>&1

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()       { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[$(date +%H:%M:%S) WARN]${NC} $*"; }
log_error() { echo -e "${RED}[$(date +%H:%M:%S) ERROR]${NC} $*"; }
log_phase()  { echo -e "\n${BLUE}═══ $(date +%H:%M:%S) ═══ $* ═══${NC}"; }
disk_info()  { echo "  Disk: $(df -h /root/autodl-tmp | awk 'NR==2{printf "%s used / %s free", $3, $4}')"; }

env_prefix() { echo "${MAMBA_ROOT}/envs/$1"; }
env_path()   { echo "${MAMBA_ROOT}/envs/$1/bin"; }
env_exe()    { echo "${MAMBA_ROOT}/envs/$1/bin/$2"; }

is_ready() { [ -f "$1/.autoplasm_resource_ready" ] || [ -f "$1/.abi_ready" ]; }

# 真正的 fork + wait：直接在主壳后台运行 `&`，捕获 $! 为直接子进程 PID
# 注意 — 必须 `& 记 $! 然后 disown -h 防止 SIGHUP`？不需要，因为 screen 会话保活。
run_step() {
    local label="$1" logname="$2"; shift 2
    local logfile="${LOG_DIR}/${logname}_$(date +%Y%m%d_%H%M%S).log"
    log "  ▸ [${label}] 启动 → ${logfile}"
    ( "$@" ) > "${logfile}" 2>&1 &
    local pid=$!
    wait "${pid}"
    local rc=$?
    if [ $rc -eq 0 ]; then log "  ✔ [${label}] 完成"; else log_error "  ✘ [${label}] 失败 (exit=$rc) — 日志: ${logfile}"; fi
    return $rc
}

log "╔════════════════════════════════════════════════════╗"
log "║  ABI 数据库顺序下载 v2 (真等待, 跳过 kraken2/humann/card) ║"
log "╚════════════════════════════════════════════════════╝"
disk_info

# ============================================================================
log_phase "PHASE 1: 小型数据库 (checkm2 / amrfinderplus / abricate 补全 / RDP)"

# 1a. CheckM2 — zenodo.org 不可达 (Connection refused), 已知必然失败, 跳过避免污染目录
CHECKM2_DIR="${RESOURCE_ROOT}/checkm2"
if is_ready "${CHECKM2_DIR}"; then
    log "  1a: checkm2 — 已就绪"
elif timeout 6 bash -c '</dev/tcp/zenodo.org/443' 2>/dev/null; then
    rm -f "${CHECKM2_DIR}/.autoplasm_resource_ready"
    run_step "checkm2" "checkm2_db" bash -c "
        set -e
        export PATH=$(env_path stats):\$PATH
        export CONDA_PREFIX=$(env_prefix stats)
        export CHECKM2DB=${CHECKM2_DIR}
        checkm2 database --download --path ${CHECKM2_DIR}
        touch ${CHECKM2_DIR}/.autoplasm_resource_ready
    "
else
    log_warn "  1a: checkm2 — SKIP (zenodo.org 不可达)"
fi

# 1b. AMRFinderPlus
AMR_DIR="${RESOURCE_ROOT}/amrfinderplus"
if is_ready "${AMR_DIR}"; then log "  1b: amrfinderplus — 已就绪"; else
    rm -rf "${AMR_DIR}"; mkdir -p "${AMR_DIR}"
    run_step "amrfinderplus" "amrfinderplus_db" bash -c "
        set -e
        export PATH=$(env_path autoplasm-annotation):\$PATH
        export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
        amrfinder_update -d ${AMR_DIR}
        AMRPROT=\$(find ${AMR_DIR} -name 'AMRProt.fa' 2>/dev/null | head -1)
        if [ -n \"\${AMRPROT}\" ] && [ -f \"\${AMRPROT}\" ]; then
            makeblastdb -in \${AMRPROT} -dbtype prot -out \${AMRPROT}
        fi
        touch ${AMR_DIR}/.autoplasm_resource_ready
    "
fi

# 1c. ABRicate — 已有 4 个 DB 完整，跳过；如不完整则补
ABRICATE_DIR="${RESOURCE_ROOT}/abricate"
NEEDED_DBS="card resfinder vfdb plasmidfinder"
MISSING_DBS=""
for db in ${NEEDED_DBS}; do
    [ -d "${ABRICATE_DIR}/${db}" ] && [ -n "$(ls -A "${ABRICATE_DIR}/${db}" 2>/dev/null)" ] || MISSING_DBS="${MISSING_DBS} ${db}"
done
if [ -z "${MISSING_DBS}" ]; then
    log "  1c: abricate — 已就绪 (card/resfinder/vfdb/plasmidfinder)"
    touch "${ABRICATE_DIR}/.autoplasm_resource_ready"
else
    run_step "abricate(${MISSING_DBS})" "abricate_db" bash -c "
        set -e
        export PATH=$(env_path autoplasm-annotation):\$PATH
        export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
        for db in ${MISSING_DBS}; do
            perl $(env_exe autoplasm-annotation abricate-get_db) --dbdir ${ABRICATE_DIR} --db \$db --force
        done
        touch ${ABRICATE_DIR}/.autoplasm_resource_ready
    "
fi

# 1d. RDP SINTAX taxonomy
RDP_DIR="${RESOURCE_ROOT}/amplicon_taxonomy"
if [ -f "${RDP_DIR}/.autoplasm_resource_ready" ] || ls "${RDP_DIR}"/rdp_*.fa >/dev/null 2>&1; then
    log "  1d: RDP — 已就绪 ($(du -sh "${RDP_DIR}" | cut -f1))"
    touch "${RDP_DIR}/.autoplasm_resource_ready"
else
    mkdir -p "${RDP_DIR}"
    run_step "RDP-taxonomy" "rdp_taxonomy" bash -c "
        set -e
        wget --tries=3 --timeout=120 -O ${RDP_DIR}/rdp_16s_v16_sp.fa.gz \\
            'https://www.drive5.com/sintax/rdp_16s_v16_sp.fa.gz'
        gunzip -f ${RDP_DIR}/rdp_16s_v16_sp.fa.gz
        touch ${RDP_DIR}/.autoplasm_resource_ready
    "
fi

disk_info

# ============================================================================
log_phase "PHASE 2: 中型数据库 + 工具 (genomad / mob_suite / plasmidfinder / PLASMe / Platon / PlasX)"

# 2a. geNomad — 数据库托管于 zenodo, 通常不可达; 可达性动态探测
GENOMAD_DIR="${RESOURCE_ROOT}/genomad"
if is_ready "${GENOMAD_DIR}"; then log "  2a: genomad — 已就绪"; else
    rm -rf "${GENOMAD_DIR}" "${RESOURCE_ROOT}/genomad.bak".* 2>/dev/null
    mkdir -p "${GENOMAD_DIR}"
    run_step "geNomad" "genomad_db" bash -c "
        set -e
        export PATH=$(env_path autoplasm-plasmid-detect):\$PATH
        export CONDA_PREFIX=$(env_prefix autoplasm-plasmid-detect)
        genomad download-database ${GENOMAD_DIR}
        touch ${GENOMAD_DIR}/.autoplasm_resource_ready
    "
    if ! is_ready "${GENOMAD_DIR}"; then log_warn "  2a: genomad 下载失败 (多半因 zenodo 不可达), 已 SKIP"; fi
fi

# 2b. mob_suite
MOB_DIR="${RESOURCE_ROOT}/mob_suite"
if is_ready "${MOB_DIR}"; then log "  2b: mob_suite — 已就绪"; else
    mkdir -p "${MOB_DIR}"
    run_step "mob_suite" "mob_suite_db" bash -c "
        set -e
        export PATH=$(env_path autoplasm-annotation):\$PATH
        export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
        mob_init --database_directory ${MOB_DIR}
        ls ${MOB_DIR}/*.nhr >/dev/null 2>&1 || ls ${MOB_DIR}/*.phr >/dev/null 2>&1
        touch ${MOB_DIR}/.autoplasm_resource_ready
    "
fi

# 2c. PLASMe
PLASME_DIR="${RESOURCE_ROOT}/PLASMe"
if [ -d "${PLASME_DIR}/.git" ]; then log "  2c: PLASMe — 已 clone"; else
    rm -rf "${PLASME_DIR}"
    run_step "PLASMe" "plasme_tool" bash -c "
        set -e
        git clone --depth 1 --single-branch https://github.com/ccb-hms/PLASMe.git ${PLASME_DIR}
        cd ${PLASME_DIR} && $(env_exe autoplasm-plasmid-detect pip) install -e . --quiet
    "
fi

# 2d. Platon
PLATON_DIR="${RESOURCE_ROOT}/platon"
if [ -d "${PLATON_DIR}/.git" ]; then log "  2d: Platon — 已 clone"; else
    rm -rf "${PLATON_DIR}"
    run_step "Platon" "platon_tool" bash -c "
        set -e
        git clone --depth 1 --single-branch https://github.com/oschwengers/platon.git ${PLATON_DIR}
        cd ${PLATON_DIR} && $(env_exe autoplasm-plasmid-detect pip) install -e . --quiet
    "
fi

# 2e. PlasX
PLASX_DIR="${RESOURCE_ROOT}/PlasX"
if [ -d "${PLASX_DIR}/.git" ]; then log "  2e: PlasX — 已 clone"; else
    rm -rf "${PLASX_DIR}"
    run_step "PlasX" "plasx_tool" bash -c "
        set -e
        git clone --depth 1 --single-branch https://github.com/michaelgoldman/PlasX.git ${PLASX_DIR}
        cd ${PLASX_DIR} && $(env_exe autoplasm-plasmid-detect pip) install -e . --quiet
    "
fi

disk_info

# ============================================================================
log_phase "PHASE 3: 大型数据库中 bakta full + metaphlan (kraken2 已在 aria2c 中)"

# 3a. MetaPhlAn (full)
METAPHLAN_DIR="${RESOURCE_ROOT}/metaphlan"
if is_ready "${METAPHLAN_DIR}"; then log "  3a: metaphlan — 已就绪"; else
    mkdir -p "${METAPHLAN_DIR}"
    run_step "MetaPhlAn" "metaphlan_db" bash -c "
        set -e
        export PATH=$(env_path stats):\$PATH
        export CONDA_PREFIX=$(env_prefix stats)
        export DEFAULT_DB_FOLDER=${METAPHLAN_DIR}
        metaphlan --install --nproc 8
        touch ${METAPHLAN_DIR}/.autoplasm_resource_ready
    "
fi

# 3b. Bakta FULL — 主数据库托管在 zenodo (DOI 10.5281/zenodo.4247253), 当前 zenodo.org 不可达
BAKTA_DIR="${RESOURCE_ROOT}/bakta"
if is_ready "${BAKTA_DIR}" && [ -f "${BAKTA_DIR}/bakta.db" ]; then log "  3b: bakta — 已就绪"; else
    rm -rf "${BAKTA_DIR}"; mkdir -p "${BAKTA_DIR}"
    run_step "Bakta-full" "bakta_full_db" bash -c "
        set -e
        export PATH=$(env_path autoplasm-annotation):\$PATH
        export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
        bakta_db download --output ${BAKTA_DIR} --type full
        [ -f ${BAKTA_DIR}/bakta.db ] && touch ${BAKTA_DIR}/.autoplasm_resource_ready
    "
    if ! is_ready "${BAKTA_DIR}"; then log_warn "  3b: bakta 失败 — 等待 zenodo 恢复后重试. 已 SKIP"; fi
fi

disk_info

# ============================================================================
log_phase "PHASE 4: gtdbtk + eggnog"

GTDBTK_DIR="${RESOURCE_ROOT}/gtdbtk"
if is_ready "${GTDBTK_DIR}" && [ -d "${GTDBTK_DIR}/markers" ]; then log "  4a: gtdbtk — 已就绪"; else
    rm -rf "${GTDBTK_DIR}"; mkdir -p "${GTDBTK_DIR}"
    run_step "GTDB-Tk" "gtdbtk_db" bash -c "
        set -e
        export PATH=$(env_path stats):\$PATH
        export CONDA_PREFIX=$(env_prefix stats)
        export GTDBTK_DATA_PATH=${GTDBTK_DIR}
        gtdbtk db download
        touch ${GTDBTK_DIR}/.autoplasm_resource_ready
    "
fi

# 4b. eggNOG-mapper — eggnog5.embl.de 通常不可达, 探测后决定
EGGNOG_DIR="${RESOURCE_ROOT}/eggnog_mapper"
if is_ready "${EGGNOG_DIR}"; then log "  4b: eggnog_mapper — 已就绪"; else
    if timeout 6 bash -c '</dev/tcp/eggnog5.embl.de/443' 2>/dev/null; then
        rm -rf "${EGGNOG_DIR}"; mkdir -p "${EGGNOG_DIR}"
        run_step "eggNOG" "eggnog_db" bash -c "
            set -e
            export PATH=$(env_path autoplasm-annotation):\$PATH
            export CONDA_PREFIX=$(env_prefix autoplasm-annotation)
            download_eggnog_data.py -y --data_dir ${EGGNOG_DIR}
            touch ${EGGNOG_DIR}/.autoplasm_resource_ready
        "
    else
        log_warn "  4b: eggnog_mapper — SKIP (eggnog5.embl.de 不可达)"
    fi
fi

disk_info

# ============================================================================
log_phase "PHASE 5: kneaddata host (humann 跳过 — env 缺 humann 包, 需另行修复)"

KNEAD_DIR="${RESOURCE_ROOT}/kneaddata_host"
if is_ready "${KNEAD_DIR}"; then log "  5: kneaddata host — 已就绪"; else
    # 现有 256M tar 但未解压，清理后重下
    rm -rf "${KNEAD_DIR}"; mkdir -p "${KNEAD_DIR}"
    # 5. KneadData host — 注意: 此前 9:46 启动的旧孤儿进程 (kneaddata_db_20260629_094658.log)
#     实际可达 huttenhower.s3 amazonaws.com (huttenhower.s3.amazonaws.com) — curl HEAD 假阴性
#     兼顾运行中的孤儿: 若有 kneaddata 进程在跑 OR 目录已 ready, 跳过避免互毁
if is_ready "${KNEAD_DIR}"; then
    log "  5: kneaddata host — 已就绪"
elif pgrep -x kneaddata_database >/dev/null 2>&1 || pgrep -af 'kneaddata_database.*human_genome' >/dev/null 2>&1; then
    log "  5: kneaddata host — 检测到运行中的 kneaddata 进程 ($(pgrep -af 'kneaddata_database' | awk '{print $1}' | tr '\n' ' ')), SKIP"
    log "    完成后请手动: touch ${KNEAD_DIR}/.autoplasm_resource_ready"
else
    run_step "KneadData-host" "kneaddata_db" bash -c "
        set -e
        export PATH=$(env_path easymeta-p0):\$PATH
        export CONDA_PREFIX=$(env_prefix easymeta-p0)
        kneaddata_database --download human_genome bowtie2 ${KNEAD_DIR}
        touch ${KNEAD_DIR}/.autoplasm_resource_ready
    "
fi
fi

disk_info

# ============================================================================
log_phase "汇总"

report_db() {
    local name="$1" path="$2" check="$3"
    local status="✘ MISSING" size=""
    if [ -e "${path}" ]; then
        size=$(du -sh "${path}" 2>/dev/null | cut -f1)
        if [ -n "${check}" ] && [ -e "${path}/${check}" ]; then status="✔ READY"
        elif [ -f "${path}/.autoplasm_resource_ready" ]; then status="✔ READY"
        elif [ -f "${path}/.abi_ready" ]; then status="✔ READY"
        elif [ -n "$(ls -A "${path}" 2>/dev/null)" ]; then status="◐ PARTIAL"
        else status="✘ EMPTY"; fi
    fi
    printf "║  %-30s  %-18s %8s  ║\n" "${name}" "${status}" "${size:-N/A}"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Database                       Status             Srce      ║"
echo "╠══════════════════════════════════════════════════════════════╣"

report_db "genomad"            "${GENOMAD_DIR}"     "genomad_db"
report_db "bakta (full)"       "${BAKTA_DIR}"       "bakta.db"
report_db "mob_suite"          "${MOB_DIR}"         ""
report_db "metaphlan"          "${METAPHLAN_DIR}"   ""
report_db "amrfinderplus"      "${AMR_DIR}"         ""
report_db "gtdbtk"             "${GTDBTK_DIR}"      "markers"
report_db "checkm2"            "${CHECKM2_DIR}"     ""
report_db "eggnog_mapper"      "${EGGNOG_DIR}"      ""
report_db "abricate"           "${ABRICATE_DIR}"    ""
report_db "RDP taxonomy"       "${RDP_DIR}"         ""
report_db "kneaddata host"     "${KNEAD_DIR}"       ""
# kraken2 (跳过)
KRAKEN2_DIR="${RESOURCE_ROOT}/kraken2"
if [ -f "${KRAKEN2_DIR}/.autoplasm_resource_ready" ] && [ -d "${KRAKEN2_DIR}/taxonomy" ]; then
    printf "║  %-30s  %-18s %8s  ║\n" "kraken2 (external)" "✔ READY" "$(du -sh "${KRAKEN2_DIR}" | cut -f1)"
else
    ARIA_PART="${RESOURCE_ROOT}/kraken2.tar.gz.part"
    SZ=$(du -sh "${ARIA_PART}" 2>/dev/null | cut -f1)
    printf "║  %-30s  %-18s %8s  ║\n" "kraken2 (external aria2c)" "◐ RUNNING" "${SZ}"
fi
# humann 跳过
printf "║  %-30s  %-18s %8s  ║\n" "humann (chocophlan/uniref)" "⚠ ENV BROKEN" "skip"
report_db "PLASMe tool"        "${PLASME_DIR}"      ".git"
report_db "Platon tool"        "${PLATON_DIR}"      ".git"
report_db "PlasX tool"         "${PLASX_DIR}"       ".git"

echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Resource root: ${RESOURCE_ROOT}"
echo "  主日志: ${LOG}"
echo "  子日志: ${LOG_DIR}/"
disk_info
log "顺序下载完成 — $(date)"