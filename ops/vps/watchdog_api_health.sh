#!/usr/bin/env bash
# /health watchdog — restart api after N consecutive failures; email once per incident.
# Cron: every 5 minutes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

LOG="$LOG_DIR/api-watchdog.log"
STATE_FILE="${TRADEPILOT_WATCHDOG_STATE:-/tmp/tp-api-watchdog.failcount}"
JOB_ID=cron_watchdog
FAIL_THRESHOLD="${WATCHDOG_FAIL_THRESHOLD:-3}"

exec >>"$LOG" 2>&1
scheduler_job_enabled "$JOB_ID" || exit 0

ok=0
if curl -fsS --max-time 8 "${TRADEPILOT_API_BASE}/health" >/dev/null 2>&1; then
  ok=1
fi

if [[ "$ok" -eq 1 ]]; then
  if [[ -f "$STATE_FILE" ]]; then
    prev=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
    if [[ "${prev:-0}" -gt 0 ]]; then
      log "health recovered (was failcount=${prev})"
      scheduler_heartbeat "$JOB_ID" ok "health recovered"
    fi
  fi
  echo 0 >"$STATE_FILE"
  exit 0
fi

count=0
if [[ -f "$STATE_FILE" ]]; then
  count=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi
count=$((count + 1))
echo "$count" >"$STATE_FILE"
log "health FAIL count=${count}/${FAIL_THRESHOLD}"
scheduler_heartbeat "$JOB_ID" failed "health fail count=${count}"

if (( count < FAIL_THRESHOLD )); then
  exit 1
fi

log "Restarting api via docker compose (threshold reached)"
if compose restart api; then
  log "api restart issued"
  sleep 20
  if curl -fsS --max-time 10 "${TRADEPILOT_API_BASE}/health" >/dev/null 2>&1; then
    echo 0 >"$STATE_FILE"
    scheduler_heartbeat "$JOB_ID" ok "api restarted and healthy"
    api_python scripts/send_ops_alert.py \
      --title "TradePilot API restarted by watchdog" \
      --body "Host $(hostname): /health failed ${count} times; docker compose restart api succeeded." || true
  else
    scheduler_heartbeat "$JOB_ID" failed "restarted but still unhealthy"
    api_python scripts/send_ops_alert.py \
      --title "TradePilot API still unhealthy after watchdog restart" \
      --body "Host $(hostname): restart api ran but /health still failing. Consider reboot." || true
  fi
else
  scheduler_heartbeat "$JOB_ID" failed "compose restart failed"
  api_python scripts/send_ops_alert.py \
    --title "TradePilot watchdog could not restart API" \
    --body "Host $(hostname): docker compose restart api failed after /health failures." || true
fi
exit 1
