#!/usr/bin/env bash
# Shared paths for TradePilot VPS cron wrappers.
set -euo pipefail

# Install path on the VPS (override when calling scripts).
export TRADEPILOT_ROOT="${TRADEPILOT_ROOT:-/opt/tradepilot}"
export COMPOSE_FILE="${COMPOSE_FILE:-$TRADEPILOT_ROOT/docker-compose.yml}"
export LOG_DIR="${TRADEPILOT_LOG_DIR:-/var/log/tradepilot}"

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
