#!/usr/bin/env bash
# =============================================================================
# ABI 数据库下载一键启动器 (下载 + 自动监控)
# 用法: bash scripts/cloud/launch_download.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_SCRIPT="${SCRIPT_DIR}/download_all_dbs.sh"
MONITOR_SCRIPT="${SCRIPT_DIR}/monitor_downloads.sh"
LOG_DIR="/root/autodl-tmp/abi/logs/cloud"
PID_FILE="${LOG_DIR}/.download_pid"
MONITOR_PID_FILE="${LOG_DIR}/.monitor_pid"
STATUS_SOCKET="/tmp/abi_download_status"

mkdir -p "${LOG_DIR}"

# ── 防止重复启动 ──
if [ -f "${PID_FILE}" ]; then
    old_pid=$(cat "${PID_FILE}")
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "⚠ 下载已在运行 (PID=$old_pid)"
        echo "  查看: tail -f ${LOG_DIR}/download_master.log"
        echo "  监控: bash ${MONITOR_SCRIPT}"
        echo "  停止: kill $old_pid"
        exit 1
    fi
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ABI 全量数据库下载启动器                               ║"
echo "║  开始时间: $(date '+%Y-%m-%d %H:%M:%S')                        ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── 1. 启动下载 ──
echo ""
echo "[1/3] 启动下载主进程..."
rm -f "${LOG_DIR}/download_master.log"
nohup bash "${DOWNLOAD_SCRIPT}" > "${LOG_DIR}/download_master.log" 2>&1 &
DOWNLOAD_PID=$!
echo "$DOWNLOAD_PID" > "${PID_FILE}"
echo "  ✔ 下载进程 PID=$DOWNLOAD_PID"
echo "  主日志: ${LOG_DIR}/download_master.log"

# ── 2. 启动后台监控 ──
echo ""
echo "[2/3] 启动后台监控 (每5分钟记录一次)..."
nohup bash -c "
    MONITOR_SCRIPT=${MONITOR_SCRIPT}
    LOG_DIR=${LOG_DIR}
    STATUS_FILE=${LOG_DIR}/.download_status.json
    HISTORY_FILE=${LOG_DIR}/.download_history.csv

    # 写入 CSV header
    echo 'timestamp,active_downloads,disk_free_gb,ready_count,in_progress,pending' > \${HISTORY_FILE}

    while true; do
        # 运行监控
        bash \${MONITOR_SCRIPT} --json 2>/dev/null

        # 追加到历史记录
        ts=\$(date +%s)
        active=\$(jq -r '.active_downloads' \${STATUS_FILE} 2>/dev/null || echo 0)
        free=\$(echo \$(jq -r '.disk_free' \${STATUS_FILE} 2>/dev/null || echo 0) | sed 's/G//')
        ready=\$(jq -r '.databases.ready' \${STATUS_FILE} 2>/dev/null || echo 0)
        prog=\$(jq -r '.databases.in_progress' \${STATUS_FILE} 2>/dev/null || echo 0)
        pend=\$(jq -r '.databases.pending' \${STATUS_FILE} 2>/dev/null || echo 0)
        echo \"\${ts},\${active},\${free},\${ready},\${prog},\${pend}\" >> \${HISTORY_FILE}

        # 检测完成: 没有活跃下载 + 所有DB就绪(或没有待处理)
        if [ \"\$active\" -eq 0 ] && [ \"\$pend\" -eq 0 ] && [ \"\$prog\" -eq 0 ]; then
            echo \"\$(date): 所有数据库下载完成!\" >> \${LOG_DIR}/monitor.log
            break
        fi

        # 检测下载进程是否已死
        if [ -f ${PID_FILE} ]; then
            dp=\$(cat ${PID_FILE})
            if ! kill -0 \$dp 2>/dev/null; then
                # 下载进程结束，等60秒看是否有后续
                sleep 60
                active2=\$(bash \${MONITOR_SCRIPT} --json 2>/dev/null | jq -r '.active_downloads' 2>/dev/null || echo 0)
                if [ \"\$active2\" -eq 0 ]; then
                    bash \${MONITOR_SCRIPT} > \${LOG_DIR}/final_status.txt 2>/dev/null
                    echo \"\$(date): 下载进程已退出，监控结束\" >> \${LOG_DIR}/monitor.log
                    break
                fi
            fi
        fi

        sleep 300  # 5分钟间隔
    done
" > "${LOG_DIR}/monitor.log" 2>&1 &
MONITOR_PID=$!
echo "$MONITOR_PID" > "${MONITOR_PID_FILE}"
echo "  ✔ 监控进程 PID=$MONITOR_PID"
echo "  监控日志: ${LOG_DIR}/monitor.log"
echo "  历史记录: ${LOG_DIR}/.download_history.csv"

# ── 3. 注册 cron 兜底监控 (每15分钟) ──
echo ""
echo "[3/3] 注册 cron 兜底监控 (每15分钟)..."
CRON_CMD="*/15 * * * * bash ${MONITOR_SCRIPT} >> ${LOG_DIR}/cron_monitor.log 2>&1"
# 只添加不重复的
(crontab -l 2>/dev/null | grep -v "monitor_downloads.sh"; echo "$CRON_CMD") | crontab - 2>/dev/null && echo "  ✔ Cron 已注册" || echo "  ⚠ Cron 注册失败 (可能无 crond)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  启动完成!                                              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  下载 PID:  ${DOWNLOAD_PID}                                      ║"
echo "║  监控 PID:  ${MONITOR_PID}                                      ║"
echo "║                                                        ║"
echo "║  实时查看:                                              ║"
echo "║    tail -f ${LOG_DIR}/download_master.log"
echo "║                                                        ║"
echo "║  查看状态:                                              ║"
echo "║    bash scripts/cloud/monitor_downloads.sh                    ║"
echo "║                                                        ║"
echo "║  查看进度历史:                                          ║"
echo "║    column -t -s, ${LOG_DIR}/.download_history.csv"
echo "║                                                        ║"
echo "║  停止所有:                                              ║"
echo "║    kill ${DOWNLOAD_PID} ${MONITOR_PID}"
echo "╚══════════════════════════════════════════════════════════╝"
