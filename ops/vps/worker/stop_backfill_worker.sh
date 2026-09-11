#!/usr/bin/env bash
# Terminate ephemeral backfill worker (terraform destroy). Do not leave stopped with disk.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TF_DIR="$ROOT/ops/vps/terraform-worker"
cd "$TF_DIR"
terraform destroy -auto-approve
rm -f /tmp/tradepilot-backfill-public-ip /tmp/tradepilot-backfill-live-private-ip
echo "Worker destroyed (instance + 8GB disk)."
