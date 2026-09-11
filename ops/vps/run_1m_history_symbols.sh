#!/usr/bin/env bash
# Retry 1m history for specific symbols (e.g. HEG,HFCL after instrument-key fixes).
# Usage: SYMBOLS=HEG,HFCL /opt/tradepilot/ops/vps/run_1m_history_symbols.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

SYMBOLS="${SYMBOLS:-HEG,HFCL}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-28}"
LOG="$LOG_DIR/1m-history-symbols.log"

exec >>"$LOG" 2>&1
log "START 1m history symbols=${SYMBOLS} lookback=${LOOKBACK_DAYS}"
scheduler_heartbeat host_1m_history running "symbols ${SYMBOLS}" "SYMBOLS"
if api_python scripts/run_1m_history_stage.py \
  --stage SYMBOLS \
  --symbols "$SYMBOLS" \
  --lookback-days "$LOOKBACK_DAYS"; then
  log "DONE 1m history symbols=${SYMBOLS}"
  scheduler_heartbeat host_1m_history ok "symbols ${SYMBOLS} done" "SYMBOLS"
else
  log "FAIL 1m history symbols=${SYMBOLS}"
  scheduler_heartbeat host_1m_history failed "symbols ${SYMBOLS} failed" "SYMBOLS"
  exit 1
fi
