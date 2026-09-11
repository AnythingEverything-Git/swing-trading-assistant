#!/usr/bin/env bash
# Bring NIFTY_500 to "perfect for today" on Free Tier (host-side, exclusive locks).
#
# Definition of done (IST trading day):
#   1) Pause heavy in-app 1m (optional; recommended)
#   2) 1m today for NIFTY_500 (full session so far)
#   3) 1m watermark pass(es) until after cash close (~15:30) — NIFTY_500 only
#   4) 1d watermark after 16:15 (NSE_ALL superset OK for swing)
#   5) Leave light in-app 1m (NIFTY_50) enabled
#
# Usage:
#   nohup /opt/tradepilot/ops/vps/run_nifty500_perfect_today.sh &
#   tail -f /var/log/tradepilot/nifty500-perfect-today.log
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

UNIVERSE="${UNIVERSE:-NIFTY_500}"
LOG="$LOG_DIR/nifty500-perfect-today.log"
exec >>"$LOG" 2>&1

status_snapshot() {
  curl -fsS "http://127.0.0.1:8001/api/v1/product/status" || true
  echo
}

ist_minutes_now() {
  TZ=Asia/Kolkata date +%H:%M | awk -F: '{ print ($1 * 60) + $2 }'
}

wait_until_ist() {
  local target_h=$1
  local target_m=$2
  local target=$((target_h * 60 + target_m))
  while true; do
    local now
    now="$(ist_minutes_now)"
    if (( now >= target )); then
      break
    fi
    local sleep_m=$(( (target - now) < 5 ? 60 : 300 ))
    log "Waiting until ${target_h}:$(printf '%02d' "$target_m") IST (sleep ${sleep_m}s)"
    sleep "$sleep_m"
  done
}

log "=== ${UNIVERSE} perfect-today start ==="
scheduler_job_enabled host_catchup || exit 0

mutex_held=$(
  curl -fsS "${TRADEPILOT_API_BASE}/api/v1/ops/schedulers" 2>/dev/null \
    | grep -o '"refresh_mutex_held"[[:space:]]*:[[:space:]]*true' || true
)
if [[ -n "$mutex_held" ]]; then
  log "SKIP (refresh_mutex_held) — retry later"
  scheduler_heartbeat host_catchup skipped "refresh mutex held"
  exit 0
fi

scheduler_heartbeat host_catchup running "nifty500-perfect-today" "1m_today"
status_snapshot

log "1/4 1m today ${UNIVERSE}"
acquire_lock /tmp/tp-1m-today.lock
api_python scripts/refresh_intraday_candles.py --mode today --universe "$UNIVERSE"
exec 9>&-
log "1m today finished"
status_snapshot

log "2/4 1m watermark loop until ~15:35 IST (${UNIVERSE})"
scheduler_heartbeat host_catchup running "nifty500-perfect-today" "1m_watermark_loop"
while true; do
  acquire_lock /tmp/tp-1m-watermark.lock
  api_python scripts/refresh_intraday_candles.py --mode watermark --universe "$UNIVERSE"
  exec 9>&-
  status_snapshot
  now="$(ist_minutes_now)"
  if (( now >= (15 * 60 + 35) )); then
    log "Past 15:35 IST — final 1m watermark done"
    break
  fi
  log "1m watermark pass done; sleep 10m then repeat"
  sleep 600
done

log "3/4 wait for 16:15 IST then 1d watermark NSE_ALL"
scheduler_heartbeat host_catchup running "nifty500-perfect-today waiting 16:15" "wait_1d"
wait_until_ist 16 15
scheduler_heartbeat host_catchup running "nifty500-perfect-today" "1d_watermark"
acquire_lock /tmp/tp-1d.lock
api_python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
exec 9>&-
log "1d watermark finished"
status_snapshot

log "4/4 optional post-close 1m watermark (${UNIVERSE})"
scheduler_heartbeat host_catchup running "nifty500-perfect-today" "1m_watermark_final"
acquire_lock /tmp/tp-1m-watermark.lock
api_python scripts/refresh_intraday_candles.py --mode watermark --universe "$UNIVERSE"
exec 9>&-
status_snapshot

log "=== ${UNIVERSE} perfect-today FINISHED ==="
log "Expect: last_1m near session end for N500, last_candle_time=today's 1d, stale_risk=Low"
log "Re-enable light in-app: INTRADAY_1M_REFRESH_ENABLED=true UNIVERSE=NIFTY_50 LIMIT=50"
scheduler_heartbeat host_catchup ok "nifty500-perfect-today finished" "done"
