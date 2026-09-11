#!/usr/bin/env bash
# Smoke: readiness API shape + gate list (run on VPS or any host that can reach the API).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

UNIVERSE="${UNIVERSE:-NIFTY_500}"
URL="${TRADEPILOT_API_BASE}/api/v1/ops/readiness?universe=${UNIVERSE}"

echo "GET $URL"
body=$(curl -fsS "$URL")
export TP_READINESS_JSON="$body"
python3 - <<'PY'
import json, os
payload = json.loads(os.environ["TP_READINESS_JSON"])
required = {"universe", "ready", "status", "as_of", "gates", "recommendations", "provider_1d_max"}
missing = required - set(payload)
assert not missing, f"missing keys: {missing}"
assert payload["status"] in ("green", "amber", "red"), payload["status"]
gate_ids = {g["id"] for g in payload["gates"]}
for need in ("live", "swing_1d", "history_1m", "today_1m", "keys", "host"):
    assert need in gate_ids, f"missing gate {need}"
print("ok status=%s ready=%s gates=%s" % (payload["status"], payload["ready"], sorted(gate_ids)))
print("provider_1d_max=%s" % payload.get("provider_1d_max"))
for g in payload["gates"]:
    print("  [%s] %s — %s" % (g["status"], g["id"], g["detail"][:120]))
PY

echo "health:"
curl -fsS "${TRADEPILOT_API_BASE}/health"
echo
echo "smoke_nifty500_readiness DONE"
