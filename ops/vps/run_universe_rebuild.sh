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
scheduler_job_enabled cron_universe || exit 0
scheduler_heartbeat cron_universe running "universe rebuild starting"
if ! acquire_lock "$LOCK"; then
  scheduler_heartbeat cron_universe skipped "lock held"
  exit 0
fi
if api_python scripts/build_nse_universe_from_upstox.py \
  && api_python scripts/refresh_instrument_key_map.py; then
  log "DONE universe rebuild + Nifty 500 EQ+BE keys"
  scheduler_heartbeat cron_universe ok "universe rebuild + keys done"
else
  log "FAIL universe rebuild"
  scheduler_heartbeat cron_universe failed "universe rebuild failed"
  exit 1
fi
