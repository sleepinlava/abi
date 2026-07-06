#!/usr/bin/env bash
# ── ABI Cloud — Run command then shutdown ──────────────────────────────────
# Wraps any long-running command so that:
#   1. All stdout/stderr is duplicated to a timestamped log file.
#   2. On exit (success or failure), the host shuts down automatically.
#
# Usage:
#   bash scripts/cloud/run_with_shutdown.sh -- python train.py
#   bash scripts/cloud/run_with_shutdown.sh --delay 60 -- abi run --type ... --confirm
#   bash scripts/cloud/run_with_shutdown.sh --no-shutdown -- abi dry-run --type ...
#
# The command is run in the foreground so you can still see live output on the
# terminal.  After it exits the machine powers off.  Logs survive in
# ${ABI_LOG_DIR} (default: <repo>/logs/cloud).
#
# Options:
#   --delay SECONDS    Grace period before shutdown (default: 1 minute).
#                      Useful so you can Ctrl-C the shutdown itself if needed.
#   --no-shutdown      Run the command normally — no shutdown at the end.
#   -h|--help          Show this message.
#
# Environment:
#   ABI_LOG_DIR        Log directory (default: <repo>/logs/cloud)
#   SHUTDOWN_BIN       Path to shutdown (default: /usr/bin/shutdown)
# ───────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Resolve project root ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABI_PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

: "${ABI_LOG_DIR:=${ABI_PROJECT_ROOT}/logs/cloud}"
: "${SHUTDOWN_BIN:=/usr/bin/shutdown}"

# ── Parse wrapper options ─────────────────────────────────────────────────
DELAY=60
DO_SHUTDOWN=true
COMMAND=()
SEPARATOR_FOUND=false

while [[ $# -gt 0 ]]; do
  if [[ "${SEPARATOR_FOUND}" == "true" ]]; then
    COMMAND+=("$1")
    shift
    continue
  fi
  case "$1" in
    --delay)
      DELAY="$2"; shift 2 ;;
    --no-shutdown)
      DO_SHUTDOWN=false; shift ;;
    --)
      SEPARATOR_FOUND=true; shift ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *)
      # If we hit an unrecognised flag before --, treat it as part of the
      # command.  This lets users omit -- when they don't have conflicting
      # flags.
      COMMAND+=("$1"); SEPARATOR_FOUND=true; shift ;;
  esac
done

if [[ ${#COMMAND[@]} -eq 0 ]]; then
  echo "ERROR: No command provided."
  echo "Usage: bash $0 [--delay N] [--no-shutdown] -- <command...>"
  exit 1
fi

# ── Logging setup ─────────────────────────────────────────────────────────
mkdir -p "${ABI_LOG_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${ABI_LOG_DIR}/run.${TIMESTAMP}.log"

echo "═══════════════════════════════════════════════════════════════"
echo "  ABI Run + Shutdown Wrapper"
echo "═══════════════════════════════════════════════════════════════"
echo "  Log file   : ${LOG_FILE}"
echo "  Command    : ${COMMAND[*]}"
echo "  Shutdown   : ${DO_SHUTDOWN} (delay=${DELAY}s)"
echo "  Started at : $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Run the command ───────────────────────────────────────────────────────
EXIT_CODE=0

{
  echo "COMMAND: ${COMMAND[*]}"
  echo "START:   $(date -Iseconds)"
  echo "───────────────────────────────────────────────────────────────"
} >> "${LOG_FILE}"

# Tee to both terminal and log file using a named pipe so we capture the
# exit code correctly.
PIPE_DIR="$(mktemp -d)"
trap 'rm -rf ${PIPE_DIR}' EXIT
PIPE="${PIPE_DIR}/pipe"
mkfifo "${PIPE}"

# Background tee process: reads from pipe, writes to both terminal and log.
tee -a "${LOG_FILE}" < "${PIPE}" &
TEE_PID=$!

# Run the actual command, redirecting stdout+stderr to the pipe.
# Using `set +e` so we capture the real exit code even on failure.
set +e
"${COMMAND[@]}" >"${PIPE}" 2>&1
EXIT_CODE=$?
set -e

# Wait for tee to flush.
exec 3>&-
wait "${TEE_PID}" 2>/dev/null || true

{
  echo "───────────────────────────────────────────────────────────────"
  echo "END:     $(date -Iseconds)"
  echo "EXIT_CODE: ${EXIT_CODE}"
} >> "${LOG_FILE}"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Command finished with exit code: ${EXIT_CODE}"
echo "  Full log saved to: ${LOG_FILE}"
echo "  Finished at: $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════"

# ── Shutdown ──────────────────────────────────────────────────────────────
if [[ "${DO_SHUTDOWN}" != "true" ]]; then
  echo ""
  echo "[INFO] --no-shutdown was set. Skipping shutdown. Machine stays up."
  exit "${EXIT_CODE}"
fi

# Check that shutdown binary exists.
if [[ ! -x "${SHUTDOWN_BIN}" ]]; then
  echo ""
  echo "[ERROR] Shutdown binary not found at ${SHUTDOWN_BIN}."
  echo "        Install it or set SHUTDOWN_BIN to the correct path."
  echo "        Machine will NOT shut down."
  exit "${EXIT_CODE}"
fi

echo ""
echo "───────────────────────────────────────────────────────────────"
echo "  Shutting down in ${DELAY} seconds..."
echo "  To cancel: /usr/bin/shutdown -c   (or Ctrl-C if still attached)"
echo "───────────────────────────────────────────────────────────────"

# Sync filesystems to reduce risk of log corruption.
sync

# Schedule shutdown with a grace period.
# Using --no-wall to reduce noise; the log file is the authoritative record.
"${SHUTDOWN_BIN}" -h +$((DELAY / 60)) "ABI run-wrapper: command exited with code ${EXIT_CODE}, auto-shutdown triggered." 2>&1 \
  | tee -a "${LOG_FILE}" || {
    echo "[WARN] shutdown command failed. Trying 'shutdown now'..."
    "${SHUTDOWN_BIN}" -h now 2>&1 | tee -a "${LOG_FILE}" || true
  }

exit "${EXIT_CODE}"
