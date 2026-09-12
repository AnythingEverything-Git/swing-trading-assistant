#!/usr/bin/env bash
# Validate Swing + Intraday interactive HTTP events against 3s SLA (accuracy unchanged).
set -euo pipefail
BASE="${TRADEPILOT_API_BASE:-http://127.0.0.1:8001}"
LIMIT_MS="${SLA_LIMIT_MS:-3000}"
FAIL=0

# Last weekday (IST) for board smoke on weekends
SESSION_DAY=$(python3 - <<'PY'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
d = datetime.now(ZoneInfo("Asia/Kolkata")).date()
while d.weekday() >= 5:
    d -= timedelta(days=1)
print(d.isoformat())
PY
)

time_get() {
  local label=$1
  local url=$2
  local start end elapsed code
  start=$(date +%s%3N)
  code=$(curl -sS -o /tmp/tp-sla-body.json -w "%{http_code}" --max-time 30 "$url" || echo 000)
  end=$(date +%s%3N)
  elapsed=$((end - start))
  if [[ "$elapsed" -gt "$LIMIT_MS" ]]; then
    echo "FAIL ${label} ${elapsed}ms status=${code} (limit ${LIMIT_MS})"
    FAIL=1
  elif [[ ! "$code" =~ ^2 ]]; then
    echo "FAIL ${label} ${elapsed}ms status=${code} (expected 2xx)"
    FAIL=1
  else
    echo "OK   ${label} ${elapsed}ms status=${code}"
  fi
}

time_post() {
  local label=$1
  local url=$2
  local body=$3
  local start end elapsed code
  start=$(date +%s%3N)
  code=$(curl -sS -o /tmp/tp-sla-body.json -w "%{http_code}" --max-time 30 \
    -H "Content-Type: application/json" -d "$body" "$url" || echo 000)
  end=$(date +%s%3N)
  elapsed=$((end - start))
  if [[ "$elapsed" -gt "$LIMIT_MS" ]]; then
    echo "FAIL ${label} ${elapsed}ms status=${code} (limit ${LIMIT_MS})"
    FAIL=1
  elif [[ ! "$code" =~ ^2 ]]; then
    echo "FAIL ${label} ${elapsed}ms status=${code} (expected 2xx)"
    FAIL=1
  else
    echo "OK   ${label} ${elapsed}ms status=${code}"
  fi
}

echo "SLA smoke against ${BASE} (limit ${LIMIT_MS}ms) session_day=${SESSION_DAY}"

time_get health "${BASE}/health"
time_get scan_runs "${BASE}/api/v1/scan/runs?limit=5"
time_get universe_supported "${BASE}/api/v1/universe/supported"
time_get universe_presets "${BASE}/api/v1/universe/presets"
time_get intraday_rules "${BASE}/api/v1/intraday/rules"
time_get sessions_list "${BASE}/api/v1/intraday/sessions?limit=5"
time_get alerts_status "${BASE}/api/v1/alerts/status"
time_get product_status "${BASE}/api/v1/product/status"

time_post universe_preview "${BASE}/api/v1/universe/preview" \
  '{"universe":"NIFTY_500","filters":{"asset_class":"ALL"}}'

time_post universe_coverage "${BASE}/api/v1/universe/coverage" \
  '{"universe":"NIFTY_500","filters":{"asset_class":"ALL"},"limit":100}'

time_post morning_board_post "${BASE}/api/v1/intraday/morning-board" \
  "{\"universe\":\"NIFTY_500\",\"source\":\"persisted\",\"session_date\":\"${SESSION_DAY}\",\"filters\":{\"asset_class\":\"ALL\",\"exclude_surveillance\":true,\"exclude_corporate_actions\":true}}"

time_get morning_board_get "${BASE}/api/v1/intraday/morning-board?universe=NIFTY_500&source=persisted&session_date=${SESSION_DAY}"

TODAY=$(date -u +%Y-%m-%d)
START=$(python3 - <<'PY'
from datetime import date, timedelta
print((date.today()-timedelta(days=270)).isoformat())
PY
)
time_post scan_accept "${BASE}/api/v1/scan/opportunities" \
  "{\"universe\":\"NIFTY_50\",\"timeframe\":\"1d\",\"start\":\"${START}T00:00:00Z\",\"end\":\"${TODAY}T00:00:00Z\",\"top_n\":5}"

time_post strategy_evaluate "${BASE}/api/v1/strategy/evaluate" \
  "{\"symbol\":\"RELIANCE\",\"timeframe\":\"1d\",\"start\":\"${START}T00:00:00Z\",\"end\":\"${TODAY}T00:00:00Z\"}" || true

time_get quotes "${BASE}/api/v1/market-data/quotes?symbols=RELIANCE,TCS,INFY" || true

time_post ensure_1m_accept "${BASE}/api/v1/intraday/ingest/ensure-1m" \
  '{"symbols":["RELIANCE","TCS"]}'

time_post session_run_accept "${BASE}/api/v1/intraday/sessions/run" \
  "{\"universe\":\"NIFTY_50\",\"source\":\"persisted\",\"session_date\":\"${SESSION_DAY}\",\"sync\":false}"

if [[ "$FAIL" -ne 0 ]]; then
  echo "SLA smoke FAILED"
  exit 1
fi
echo "SLA smoke PASSED"
