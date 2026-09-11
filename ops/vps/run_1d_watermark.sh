#!/usr/bin/env bash
# Weekday safety net: 1d watermark NSE_ALL if in-app 16:15 job was missed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

LOCK=/tmp/tp-1d.lock
LOG="$LOG_DIR/1d-watermark.log"

exec >>"$LOG" 2>&1
log "START 1d watermark NSE_ALL"
scheduler_job_enabled cron_1d || exit 0
scheduler_heartbeat cron_1d running "1d watermark starting"
if ! acquire_lock "$LOCK"; then
  scheduler_heartbeat cron_1d skipped "lock held"
  exit 0
fi
if api_python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL; then
  log "DONE 1d watermark NSE_ALL"
  scheduler_heartbeat cron_1d ok "1d watermark done"
else
  log "FAIL 1d watermark NSE_ALL"
  scheduler_heartbeat cron_1d failed "1d watermark failed"
  exit 1
fi
