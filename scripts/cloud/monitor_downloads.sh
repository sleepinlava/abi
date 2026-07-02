#!/usr/bin/env bash
# =============================================================================
# ABI 数据库下载监控脚本
# 用法: bash scripts/cloud/monitor_downloads.sh [--once|--watch]
#   --once   运行一次输出状态
#   --watch  持续监控(每60秒刷新)
# =============================================================================
set -uo pipefail

RESOURCE_ROOT="/root/autodl-tmp/resources/autoplasm"
LOG_DIR="/root/autodl-tmp/abi/logs/cloud"
MAMBA_ROOT="/root/autodl-tmp/.mamba"
STATUS_FILE="${LOG_DIR}/.download_status.json"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# ── 数据库清单 (name, path, check_file, expected_size_range) ──
declare -A DB_PATH=()
declare -A DB_CHECK=()
declare -A DB_SIZE_RANGE=()

register_db() {
    local id="$1" path="$2" check="$3" range="$4"
    DB_PATH[$id]="$path"
    DB_CHECK[$id]="$check"
    DB_SIZE_RANGE[$id]="$range"
}

register_db genomad           "${RESOURCE_ROOT}/genomad"           "genomad_db"        "2G-4G"
register_db bakta             "${RESOURCE_ROOT}/bakta"             "bakta.db"          "70G-90G"
register_db mob_suite         "${RESOURCE_ROOT}/mob_suite"         ".autoplasm_resource_ready" "2G-4G"
register_db plasmidfinder     "${RESOURCE_ROOT}/plasmidfinder_db"  "config"            "50K-1G"
register_db metaphlan         "${RESOURCE_ROOT}/metaphlan"         ".autoplasm_resource_ready" "25G-40G"
register_db amrfinderplus     "${RESOURCE_ROOT}/amrfinderplus"     ".autoplasm_resource_ready" "200M-2G"
register_db kraken2           "${RESOURCE_ROOT}/kraken2"           "taxonomy"          "40G-60G"
register_db gtdbtk            "${RESOURCE_ROOT}/gtdbtk"            "markers"           "25G-40G"
register_db checkm2           "${RESOURCE_ROOT}/checkm2"           ".autoplasm_resource_ready" "200M-2G"
register_db eggnog_mapper     "${RESOURCE_ROOT}/eggnog_mapper"     ".autoplasm_resource_ready" "25G-40G"
register_db abricate          "${RESOURCE_ROOT}/abricate"          ".autoplasm_resource_ready" "1M-10G"
register_db rdp_taxonomy      "${RESOURCE_ROOT}/amplicon_taxonomy" "rdp_16s_v16.fa"    "10M-200M"
register_db card              "${RESOURCE_ROOT}/card"              ".autoplasm_resource_ready" "1M-5G"
register_db kneaddata_host    "${RESOURCE_ROOT}/kneaddata_host"    ".autoplasm_resource_ready" "2G-5G"
register_db humann_chocophlan "${RESOURCE_ROOT}/humann/chocophlan" ".autoplasm_resource_ready" "3G-8G"
register_db humann_uniref     "${RESOURCE_ROOT}/humann/uniref"     ".autoplasm_resource_ready" "2G-5G"

# ── 检查函数 ──
get_size() { du -sh "$1" 2>/dev/null | cut -f1; }
get_size_bytes() { du -sb "$1" 2>/dev/null | cut -f1; }

is_ready() {
    local path="$1" check="$2"
    [ -e "$path" ] || return 1
    if [ -n "$check" ] && [ -e "$path/$check" ]; then return 0; fi
    [ -f "$path/.autoplasm_resource_ready" ] && return 0
    [ -f "$path/.abi_ready" ] && return 0
    return 1
}

# 检查是否有下载任务在运行（检查活跃子进程）
count_active_downloads() {
    local count=0
    for p in aria2c bakta_db genomad metaphlan gtdbtk checkm2 kneaddata_database humann_databases download_eggnog_data.py wget curl; do
        local c=$(ps aux 2>/dev/null | grep -c "[${p:0:1}]${p:1}" || true)
        count=$((count + c))
    done
    echo $count
}

# ── 单次报告 ──
print_status() {
    local active=$(count_active_downloads)
    local disk_used=$(df -h /root/autodl-tmp | awk 'NR==2{print $3}')
    local disk_free=$(df -h /root/autodl-tmp | awk 'NR==2{print $4}')
    local disk_pct=$(df -h /root/autodl-tmp | awk 'NR==2{print $5}')
    local total_size=0
    for id in "${!DB_PATH[@]}"; do
        local s=$(get_size_bytes "${DB_PATH[$id]}")
        total_size=$((total_size + ${s:-0}))
    done
    local total_h=$(numfmt --to=iec $total_size 2>/dev/null || echo "${total_size}B")

    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║  ABI 数据库下载监控  —  $(date '+%Y-%m-%d %H:%M:%S')                    ║"
    echo "╠══════════════════════════════════════════════════════════════════════╣"
    printf "║  活跃下载进程: %-3s  磁盘: %s / %s (%s)  已下载: %-8s      ║\n" \
        "$active" "$disk_used" "$disk_free" "$disk_pct" "$total_h"
    echo "╠══════════════════════════════════════════════════════════════════════╣"
    printf "║  %-28s  %-12s  %8s  %-10s ║\n" "Database" "Status" "Size" "ETA"
    echo "╠══════════════════════════════════════════════════════════════════════╣"

    local ready=0 total=0 partial=0 missing=0
    for id in genomad bakta mob_suite plasmidfinder metaphlan amrfinderplus kraken2 gtdbtk checkm2 eggnog_mapper abricate rdp_taxonomy card kneaddata_host humann_chocophlan humann_uniref; do
        total=$((total + 1))
        local path="${DB_PATH[$id]}"
        local check="${DB_CHECK[$id]}"
        local size=$(get_size "$path")
        local status_icon="✘"
        local status_text="MISSING"
        local eta=""

        if is_ready "$path" "$check"; then
            status_icon="✔"
            status_text="READY"
            ready=$((ready + 1))
        elif [ -d "$path" ] && [ "$(ls -A "$path" 2>/dev/null)" ]; then
            status_icon="◐"
            status_text="DOWNLOADING"
            partial=$((partial + 1))
            # 估算剩余时间(基于10分钟的变化)
            local current_bytes=$(get_size_bytes "$path")
            local marker_file="${LOG_DIR}/.size_${id}"
            if [ -f "$marker_file" ] && [ "${current_bytes:-0}" -gt 0 ]; then
                local prev_bytes=$(cat "$marker_file")
                local delta=$(( ${current_bytes:-0} - ${prev_bytes:-0} ))
                local total_expected=${DB_SIZE_RANGE[$id]}
                # 简化: 如果增长快就显示进度
                if [ $delta -gt 1048576 ]; then  # >1MB增长
                    eta="${delta} B/s"
                fi
            fi
            echo "$current_bytes" > "$marker_file" 2>/dev/null
        else
            missing=$((missing + 1))
        fi

        local color=""
        case "$status_icon" in
            ✔) color="$GREEN" ;;
            ◐) color="$YELLOW" ;;
            *) color="$RED" ;;
        esac
        printf "${color}║  %-28s  %-1s %-11s  %8s  %-10s${NC} ║\n" \
            "$id" "$status_icon" "$status_text" "${size:-N/A}" "$eta"
    done

    echo "╠══════════════════════════════════════════════════════════════════════╣"
    printf "║  总计: %-2d  READY: %-2d  IN-PROGRESS: %-2d  PENDING: %-2d                 ║\n" \
        $total $ready $partial $missing
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""

    # 输出 JSON 给定时任务用
    cat > "${STATUS_FILE}" << JSONEOF
{
    "timestamp": "$(date -Iseconds)",
    "active_downloads": $active,
    "disk_used": "$disk_used",
    "disk_free": "$disk_free",
    "disk_pct": "$disk_pct",
    "total_size": "$total_h",
    "databases": {
        "ready": $ready, "in_progress": $partial, "pending": $missing, "total": $total
    }
}
JSONEOF
}

# ── 持续监控 ──
watch_loop() {
    echo "持续监控模式 — Ctrl+C 退出"
    while true; do
        clear 2>/dev/null || true
        print_status
        echo "  刷新间隔: 60秒 | 下次刷新: $(date -d '+60 seconds' '+%H:%M:%S')"
        sleep 60
    done
}

# ── 主入口 ──
case "${1:-}" in
    --watch|-w)
        watch_loop
        ;;
    --json|-j)
        print_status > /dev/null
        cat "${STATUS_FILE}"
        ;;
    *)
        print_status
        ;;
esac
