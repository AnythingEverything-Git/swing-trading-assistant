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
acquire_lock "$LOCK"
api_python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
log "DONE 1d watermark NSE_ALL"
