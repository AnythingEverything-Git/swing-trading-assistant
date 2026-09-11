#!/usr/bin/env bash
# Weekday morning: ingest today's 1m bars (after OR forms ~09:20 IST).
# Free Tier default: NIFTY_500. Override: UNIVERSE=NSE_ALL ./run_1m_today.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

UNIVERSE="${UNIVERSE:-NIFTY_500}"
LOCK=/tmp/tp-1m-today.lock
LOG="$LOG_DIR/1m-today.log"

exec >>"$LOG" 2>&1
log "START 1m today ${UNIVERSE}"
scheduler_job_enabled cron_1m_today || exit 0
scheduler_heartbeat cron_1m_today running "1m today ${UNIVERSE} starting"
if ! acquire_lock "$LOCK"; then
  scheduler_heartbeat cron_1m_today skipped "lock held"
  exit 0
fi
if api_python scripts/refresh_intraday_candles.py --mode today --universe "$UNIVERSE"; then
  log "DONE 1m today ${UNIVERSE}"
  scheduler_heartbeat cron_1m_today ok "1m today ${UNIVERSE} done"
else
  log "FAIL 1m today ${UNIVERSE}"
  scheduler_heartbeat cron_1m_today failed "1m today ${UNIVERSE} failed"
  exit 1
fi
