#!/usr/bin/env bash
# Paced 1d catch-up for NIFTY_500 symbols behind provider_1d_max (429-safe).
# Cron: weekdays 17:00 IST (after 16:45 safety watermark).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

UNIVERSE="${UNIVERSE:-NIFTY_500}"
LOCK=/tmp/tp-1d-paced.lock
LOG="$LOG_DIR/1d-n500-paced.log"
JOB_ID=cron_1d_paced

exec >>"$LOG" 2>&1
log "START paced 1d ${UNIVERSE}"
scheduler_job_enabled "$JOB_ID" || exit 0

# Refuse if in-app refresh mutex held (Ops /health-ish via schedulers strip).
mutex_held=$(
  curl -fsS "${TRADEPILOT_API_BASE}/api/v1/ops/schedulers" 2>/dev/null \
    | grep -o '"refresh_mutex_held"[[:space:]]*:[[:space:]]*true' || true
)
if [[ -n "$mutex_held" ]]; then
  log "SKIP (refresh_mutex_held)"
  scheduler_heartbeat "$JOB_ID" skipped "refresh mutex held"
  exit 0
fi

# Also skip if another host 1d / today job holds flock.
if ! acquire_lock "$LOCK"; then
  scheduler_heartbeat "$JOB_ID" skipped "lock held"
  exit 0
fi
# Share exclusivity with full 1d watermark when present.
exec 8>/tmp/tp-1d.lock
if ! flock -n 8; then
  log "SKIP (tp-1d.lock held by watermark)"
  scheduler_heartbeat "$JOB_ID" skipped "1d watermark lock held"
  exit 0
fi

scheduler_heartbeat "$JOB_ID" running "paced 1d starting" "retry"
if api_python scripts/run_1d_n500_paced.py --universe "$UNIVERSE"; then
  log "DONE paced 1d ${UNIVERSE}"
  scheduler_heartbeat "$JOB_ID" ok "paced 1d done" "done"
else
  log "FAIL paced 1d ${UNIVERSE}"
  scheduler_heartbeat "$JOB_ID" failed "paced 1d failed"
  exit 1
fi
