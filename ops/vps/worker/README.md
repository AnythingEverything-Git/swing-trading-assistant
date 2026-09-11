# Ephemeral Free Tier–oriented backfill worker
#
# Start → run staged Nifty 50 / 100 remaining / 500 remaining → destroy.
# No Elastic IP. 8 GB disk deleted on terminate.
#
# Prerequisites:
# - tradepilot-live running in same VPC/region
# - live docker-compose publishes Postgres :5432 (SG allows worker SG only)
# - terraform.tfvars filled (key_name, ssh_ingress_cidr)
#
# From repo root (Git Bash / WSL / Linux):
#
#   export TRADEPILOT_PEM=/path/to/ec2KeyPair.pem
#   export TRADEPILOT_LIVE_ENV=/path/to/live.env   # UPSTOX_* + POSTGRES_PASSWORD
#   ./ops/vps/worker/start_backfill_worker.sh
#   ./ops/vps/worker/run_staged_backfill.sh --stage NIFTY_50
#   ./ops/vps/worker/run_staged_backfill.sh --stage NIFTY_100_REMAINING
#   ./ops/vps/worker/run_staged_backfill.sh --stage NIFTY_500_REMAINING
#   ./ops/vps/worker/stop_backfill_worker.sh
#
# Free Tier note: live already uses most of 750 micro-hours + 30GB EBS.
# Worker adds prorated compute/EBS only while running — destroy immediately after.
