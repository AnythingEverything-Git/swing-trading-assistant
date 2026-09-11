#!/usr/bin/env bash
# Poll Nifty 500 readiness; email on red (amber = provider lag, no email by default).
# Cron IST: 09:35, 12:00, 16:50 weekdays.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

UNIVERSE="${UNIVERSE:-NIFTY_500}"
LOG="$LOG_DIR/nifty500-readiness.log"
JOB_ID=cron_readiness
EMAIL_ON_AMBER="${EMAIL_ON_AMBER:-0}"

exec >>"$LOG" 2>&1
log "START readiness check ${UNIVERSE}"
scheduler_job_enabled "$JOB_ID" || exit 0
scheduler_heartbeat "$JOB_ID" running "readiness check" "poll"

body_file=$(mktemp)
trap 'rm -f "$body_file"' EXIT
if ! curl -fsS "${TRADEPILOT_API_BASE}/api/v1/ops/readiness?universe=${UNIVERSE}" >"$body_file"; then
  log "FAIL readiness API unreachable"
  scheduler_heartbeat "$JOB_ID" failed "readiness API unreachable"
  api_python scripts/send_ops_alert.py \
    --title "TradePilot readiness API down" \
    --body "GET /api/v1/ops/readiness failed on $(hostname). Check API / run watchdog." || true
  exit 1
fi

status=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status",""))' "$body_file" 2>/dev/null || true)
ready=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("ready",""))' "$body_file" 2>/dev/null || true)
log "status=${status} ready=${ready}"

# Copy JSON into the api container (compose exec can't see host mktemp path reliably).
# Prefer piping via stdin when available; fall back to docker cp into a known path.
copy_alert_json() {
  local host_path=$1
  compose cp "$host_path" api:/tmp/tp-readiness-alert.json >/dev/null 2>&1 || {
    # Older compose: stream via exec
    compose exec -T api sh -c 'cat > /tmp/tp-readiness-alert.json' <"$host_path"
  }
}

if [[ "$status" == "red" ]]; then
  scheduler_heartbeat "$JOB_ID" failed "readiness red" "alert"
  copy_alert_json "$body_file"
  api_python scripts/send_ops_alert.py \
    --title "TradePilot Nifty 500 readiness RED" \
    --body-file /tmp/tp-readiness-alert.json || true
  exit 1
fi

if [[ "$status" == "amber" && "$EMAIL_ON_AMBER" == "1" ]]; then
  copy_alert_json "$body_file"
  api_python scripts/send_ops_alert.py \
    --title "TradePilot Nifty 500 readiness AMBER (provider lag)" \
    --body-file /tmp/tp-readiness-alert.json || true
fi

scheduler_heartbeat "$JOB_ID" ok "status=${status}" "done"
log "DONE readiness status=${status}"
