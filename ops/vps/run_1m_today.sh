#!/usr/bin/env bash
# Weekday morning: ingest today's 1m bars for NSE_ALL (after OR forms ~09:20 IST).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

LOCK=/tmp/tp-1m-today.lock
LOG="$LOG_DIR/1m-today.log"

exec >>"$LOG" 2>&1
log "START 1m today NSE_ALL"
acquire_lock "$LOCK"
api_python scripts/refresh_intraday_candles.py --mode today --universe NSE_ALL
log "DONE 1m today NSE_ALL"
