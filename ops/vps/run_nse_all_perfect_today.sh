#!/usr/bin/env bash
# Bring NSE_ALL to "perfect for today" on Free Tier (host-side, exclusive locks).
#
# Definition of done (IST trading day):
#   1) 1m today for NSE_ALL (full session so far)
#   2) 1m watermark pass(es) until after cash close (~15:30)
#   3) 1d watermark after 16:15 (today's daily bar + any lag)
#
# Recommended first: pause in-app 1m loop so this job owns Upstox + CPU:
#   INTRADAY_1M_REFRESH_ENABLED=false in /opt/tradepilot/.env && recreate api
#
# Usage:
#   nohup /opt/tradepilot/ops/vps/run_nse_all_perfect_today.sh &
#   tail -f /var/log/tradepilot/nse-all-perfect-today.log
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

LOG="$LOG_DIR/nse-all-perfect-today.log"
exec >>"$LOG" 2>&1

status_snapshot() {
  curl -fsS "http://127.0.0.1:8001/api/v1/product/status" || true
  echo
}

# Minutes since midnight IST
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

log "=== NSE_ALL perfect-today start ==="
scheduler_job_enabled host_catchup || exit 0
scheduler_heartbeat host_catchup running "perfect-today" "1m_today"
status_snapshot

log "1/4 1m today NSE_ALL"
acquire_lock /tmp/tp-1m-today.lock
api_python scripts/refresh_intraday_candles.py --mode today --universe NSE_ALL
exec 9>&-
log "1m today finished"
status_snapshot

log "2/4 1m watermark loop until ~15:35 IST"
scheduler_heartbeat host_catchup running "perfect-today" "1m_watermark_loop"
while true; do
  acquire_lock /tmp/tp-1m-watermark.lock
  api_python scripts/refresh_intraday_candles.py --mode watermark --universe NSE_ALL
  exec 9>&-
  status_snapshot
  now="$(ist_minutes_now)"
  # Stop looping after cash close + small buffer
  if (( now >= (15 * 60 + 35) )); then
    log "Past 15:35 IST — final 1m watermark done"
    break
  fi
  log "1m watermark pass done; sleep 10m then repeat"
  sleep 600
done

log "3/4 wait for 16:15 IST then 1d watermark NSE_ALL"
scheduler_heartbeat host_catchup running "perfect-today waiting 16:15" "wait_1d"
wait_until_ist 16 15
scheduler_heartbeat host_catchup running "perfect-today" "1d_watermark"
acquire_lock /tmp/tp-1d.lock
api_python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
exec 9>&-
log "1d watermark finished"
status_snapshot

log "4/4 optional post-close 1m watermark"
scheduler_heartbeat host_catchup running "perfect-today" "1m_watermark_final"
acquire_lock /tmp/tp-1m-watermark.lock
api_python scripts/refresh_intraday_candles.py --mode watermark --universe NSE_ALL
exec 9>&-
status_snapshot

log "=== NSE_ALL perfect-today FINISHED ==="
log "Expect: symbols_with_1m≈universe, last_1m near session end, last_candle_time=today's 1d, stale_risk=Low"
scheduler_heartbeat host_catchup ok "perfect-today finished" "done"
