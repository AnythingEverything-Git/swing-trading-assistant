#!/usr/bin/env bash
# Weekly: rebuild NSE cash+ETF master + instrument keys from Upstox.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

LOCK=/tmp/tp-universe.lock
LOG="$LOG_DIR/universe-rebuild.log"

exec >>"$LOG" 2>&1
log "START universe rebuild"
acquire_lock "$LOCK"
api_python scripts/build_nse_universe_from_upstox.py
log "DONE universe rebuild"
