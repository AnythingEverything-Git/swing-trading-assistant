#!/usr/bin/env bash
# Shared paths for TradePilot VPS cron wrappers.
set -euo pipefail

# Install path on the VPS (override when calling scripts).
export TRADEPILOT_ROOT="${TRADEPILOT_ROOT:-/opt/tradepilot}"
export COMPOSE_FILE="${COMPOSE_FILE:-$TRADEPILOT_ROOT/docker-compose.yml}"
export LOG_DIR="${TRADEPILOT_LOG_DIR:-/var/log/tradepilot}"
export TRADEPILOT_API_BASE="${TRADEPILOT_API_BASE:-http://127.0.0.1:8001}"

mkdir -p "$LOG_DIR"

compose() {
  docker compose -f "$COMPOSE_FILE" --project-directory "$TRADEPILOT_ROOT" "$@"
}

# Run a Python script inside the api container (same env + DB as the live API).
api_python() {
  compose exec -T api python "$@"
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

# POST job heartbeat to the ops schedulers API (best-effort; never fails the job).
# Usage: scheduler_heartbeat <job_id> <status> [detail] [phase]
scheduler_heartbeat() {
  local job_id=$1
  local status=$2
  local detail=${3:-}
  local phase=${4:-}
  local running_json=false
  if [[ "$status" == "running" ]]; then
    running_json=true
  fi
  local payload
  payload=$(printf '{"job_id":"%s","status":"%s","running":%s' "$job_id" "$status" "$running_json")
  if [[ -n "$detail" ]]; then
    detail=${detail//\\/\\\\}
    detail=${detail//\"/\\\"}
    payload+=$(printf ',"detail":"%s"' "$detail")
  fi
  if [[ -n "$phase" ]]; then
    phase=${phase//\\/\\\\}
    phase=${phase//\"/\\\"}
    payload+=$(printf ',"phase":"%s"' "$phase")
  fi
  payload+='}'
  curl -fsS -X POST \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "${TRADEPILOT_API_BASE}/api/v1/ops/schedulers/heartbeat" >/dev/null 2>&1 || true
}

# Return 0 if Ops dashboard has the job enabled (default true if API unreachable).
# Usage: scheduler_job_enabled <job_id> || exit 0
scheduler_job_enabled() {
  local job_id=$1
  local body
  body=$(curl -fsS "${TRADEPILOT_API_BASE}/api/v1/ops/schedulers/${job_id}" 2>/dev/null || true)
  if [[ -z "$body" ]]; then
    return 0
  fi
  if printf '%s' "$body" | grep -q '"enabled"[[:space:]]*:[[:space:]]*false'; then
    log "SKIP (disabled in Ops): $job_id"
    scheduler_heartbeat "$job_id" skipped "disabled in Ops dashboard"
    return 1
  fi
  return 0
}

# Hold an exclusive non-blocking lock on FD 9 for the rest of the script.
# Usage: acquire_lock /tmp/tp-foo.lock || exit 1
acquire_lock() {
  local lock_file=$1
  exec 9>"$lock_file"
  if ! flock -n 9; then
    log "SKIP (lock held): $lock_file"
    return 1
  fi
}
