#!/usr/bin/env bash
# Run one staged 1m history backfill on the ephemeral worker (writes to live Postgres).
set -euo pipefail

STAGE="NIFTY_50"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)
      STAGE="${2:?--stage requires a value}"
      shift 2
      ;;
    *)
      STAGE="$1"
      shift
      ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TF_DIR="$ROOT/ops/vps/terraform-worker"
PEM="${TRADEPILOT_PEM:-$HOME/Downloads/AWSec2/ec2KeyPair.pem}"
LIVE_ENV_HINT="${TRADEPILOT_LIVE_ENV:-}"

cd "$TF_DIR"
PUBLIC_IP="$(terraform output -raw public_ip)"
LIVE_PRIV="$(terraform output -raw live_private_ip)"
HEARTBEAT="http://${LIVE_PRIV}:8001"

if [[ -z "$LIVE_ENV_HINT" ]]; then
  echo "Set TRADEPILOT_LIVE_ENV to a path of live .env (UPSTOX_* + POSTGRES_PASSWORD)."
  echo "Example: export TRADEPILOT_LIVE_ENV=/path/to/live.env"
  exit 1
fi

WORKER_ENV=$(mktemp)
{
  grep -E '^(UPSTOX_|MARKET_DATA_SOURCE|POSTGRES_PASSWORD)=' "$LIVE_ENV_HINT" || true
  PGPASS="$(grep -E '^POSTGRES_PASSWORD=' "$LIVE_ENV_HINT" | cut -d= -f2- || echo postgres)"
  echo "MARKET_DATA_SOURCE=upstox"
  echo "DATABASE_URL=postgresql+psycopg://postgres:${PGPASS}@${LIVE_PRIV}:5432/swingdb"
  echo "TRADEPILOT_HEARTBEAT_BASE=${HEARTBEAT}"
  echo "ENVIRONMENT=production"
} >"$WORKER_ENV"

scp -i "$PEM" -o StrictHostKeyChecking=accept-new "$WORKER_ENV" ubuntu@"$PUBLIC_IP":/opt/tradepilot/.env
rm -f "$WORKER_ENV"

ssh -i "$PEM" -o StrictHostKeyChecking=accept-new ubuntu@"$PUBLIC_IP" \
  bash -s -- "$STAGE" "$HEARTBEAT" <<'REMOTE'
set -euo pipefail
STAGE="$1"
HEARTBEAT="$2"
cd /opt/tradepilot
docker build -t tradepilot-backfill .
docker run --rm --network host \
  --env-file /opt/tradepilot/.env \
  -e "TRADEPILOT_HEARTBEAT_BASE=${HEARTBEAT}" \
  -e "PYTHONPATH=/app/backend" \
  tradepilot-backfill \
  python scripts/run_1m_history_stage.py \
    --stage "${STAGE}" \
    --lookback-days 28 \
    --pause 0.2 \
    --heartbeat-base "${HEARTBEAT}"
REMOTE

echo "Stage $STAGE finished on worker. Check Ops → host_1m_history progress."
