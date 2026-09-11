#!/usr/bin/env bash
# Start ephemeral t3.micro backfill worker (terraform apply). Terminate when done.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TF_DIR="$ROOT/ops/vps/terraform-worker"
PEM="${TRADEPILOT_PEM:-$HOME/Downloads/AWSec2/ec2KeyPair.pem}"
# Windows default override when run from Git Bash / WSL path may differ — set TRADEPILOT_PEM.

cd "$TF_DIR"
if [[ ! -f terraform.tfvars ]]; then
  echo "Missing $TF_DIR/terraform.tfvars — copy terraform.tfvars.example and fill key_name + ssh_ingress_cidr"
  exit 1
fi

terraform init -input=false
terraform apply -auto-approve

PUBLIC_IP="$(terraform output -raw public_ip)"
LIVE_PRIV="$(terraform output -raw live_private_ip)"
echo "Worker public_ip=$PUBLIC_IP live_private_ip=$LIVE_PRIV"
echo "$PUBLIC_IP" > /tmp/tradepilot-backfill-public-ip
echo "$LIVE_PRIV" > /tmp/tradepilot-backfill-live-private-ip

echo "Waiting for SSH..."
for _ in $(seq 1 36); do
  if ssh -i "$PEM" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
    ubuntu@"$PUBLIC_IP" "cloud-init status --wait >/dev/null 2>&1 || true; test -d /opt/tradepilot"; then
    break
  fi
  sleep 10
done

echo "Syncing repo (no .env secrets from laptop demo)..."
# shellcheck disable=SC2086
tar -C "$ROOT" -czf /tmp/tradepilot-worker.tgz \
  --exclude=node_modules --exclude=.git --exclude=__pycache__ --exclude=.venv \
  --exclude=dist --exclude=.terraform --exclude='*.tfstate*' \
  backend ops Dockerfile docker-compose.yml alembic.ini .dockerignore

scp -i "$PEM" -o StrictHostKeyChecking=accept-new \
  /tmp/tradepilot-worker.tgz ubuntu@"$PUBLIC_IP":/tmp/tradepilot-worker.tgz
ssh -i "$PEM" ubuntu@"$PUBLIC_IP" \
  "sudo mkdir -p /opt/tradepilot && sudo tar -xzf /tmp/tradepilot-worker.tgz -C /opt/tradepilot && sudo chown -R ubuntu:ubuntu /opt/tradepilot"

echo "Worker ready. Next: ops/vps/worker/run_staged_backfill.sh --stage NIFTY_50"
echo "Then: ops/vps/worker/stop_backfill_worker.sh"
