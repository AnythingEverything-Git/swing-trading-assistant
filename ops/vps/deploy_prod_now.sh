#!/usr/bin/env bash
set -euo pipefail
ROOT="/d/Study/GenAI/swing-trading-assistant"
PEM="/c/Users/User/Downloads/AWSec2/ec2KeyPair.pem"
REMOTE="ubuntu@13.235.110.243"
TGZ="/tmp/tradepilot-deploy.tgz"

cd "$ROOT"
tar --exclude='node_modules' --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
  --exclude='dist' --exclude='.env' --exclude='*.pyc' \
  -czf "$TGZ" \
  backend frontend ops/vps \
  Dockerfile docker-compose.yml alembic.ini .dockerignore

scp -i "$PEM" "$TGZ" "${REMOTE}:/tmp/tradepilot-deploy.tgz"

ssh -i "$PEM" "$REMOTE" 'set -e
  cd /opt/tradepilot
  tar -xzf /tmp/tradepilot-deploy.tgz
  find ops/vps -name "*.sh" -exec sed -i "s/\r$//" {} \;
  chmod +x ops/vps/*.sh || true
  docker compose build api web
  docker compose up -d api web
  for i in $(seq 1 25); do
    curl -sf http://127.0.0.1:8001/health >/dev/null && break
    sleep 2
  done
  docker compose exec -T -w /app api python -m alembic -c alembic.ini upgrade head
  docker compose exec -T -w /app api python -m alembic -c alembic.ini current
  echo "--- health ---"
  curl -sf http://127.0.0.1:8001/health; echo
  curl -sf http://127.0.0.1/ >/dev/null && echo WEB_OK
  echo "--- product status ---"
  curl -sf http://127.0.0.1:8001/api/v1/product/status | head -c 240; echo
  echo "--- sla smoke ---"
  curl -sf http://127.0.0.1:8001/api/v1/product/status >/dev/null || true
  curl -sf "http://127.0.0.1:8001/api/v1/market-data/quotes?symbols=RELIANCE,TCS,INFY" >/dev/null || true
  bash ops/vps/smoke_sla_3s.sh
  echo DEPLOY_OK
'
