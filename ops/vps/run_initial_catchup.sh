#!/usr/bin/env bash
# One-time / catch-up: 1d watermark then 1m today for NSE_ALL (long-running).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

LOG="$LOG_DIR/initial-catchup.log"
exec >>"$LOG" 2>&1

log "=== Initial NSE_ALL catch-up ==="
log "1/3 1d watermark"
acquire_lock /tmp/tp-1d.lock
api_python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
log "2/3 1m today (may take many hours)"
# Release 1d lock before taking today lock (same shell: reopen FD)
exec 9>&-
acquire_lock /tmp/tp-1m-today.lock
api_python scripts/refresh_intraday_candles.py --mode today --universe NSE_ALL
log "3/3 1m watermark (ongoing sessions)"
exec 9>&-
acquire_lock /tmp/tp-1m-watermark.lock
api_python scripts/refresh_intraday_candles.py --mode watermark --universe NSE_ALL
log "=== Catch-up finished — check /api/v1/product/status symbols_with_1m ==="
curl -fsS "http://127.0.0.1:8001/api/v1/product/status" || true
echo
