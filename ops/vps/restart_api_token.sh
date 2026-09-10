#!/usr/bin/env bash
# After updating UPSTOX_ACCESS_TOKEN in $TRADEPILOT_ROOT/.env — restart API only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

log "Restarting api to load new .env token"
compose up -d --force-recreate api
compose ps
curl -fsS "http://127.0.0.1:8001/api/v1/product/status" | head -c 500 || true
echo
log "Done — confirm live_ready=true"
