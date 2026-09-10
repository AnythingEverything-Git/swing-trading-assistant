output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.tradepilot.id
}

output "public_ip" {
  description = "Reachable IP (Elastic IP when enabled)."
  value       = var.create_elastic_ip ? aws_eip.tradepilot[0].public_ip : aws_instance.tradepilot.public_ip
}

output "ssh_command" {
  description = "SSH as ubuntu (default AMI user)."
  value       = "ssh -i <your-private-key.pem> ubuntu@${var.create_elastic_ip ? aws_eip.tradepilot[0].public_ip : aws_instance.tradepilot.public_ip}"
}

output "api_base_url" {
  description = "Direct API URL (also proxied via UI on port 80)."
  value       = "http://${var.create_elastic_ip ? aws_eip.tradepilot[0].public_ip : aws_instance.tradepilot.public_ip}:8001"
}

output "ui_url" {
  description = "Production UI (nginx on port 80)."
  value       = "http://${var.create_elastic_ip ? aws_eip.tradepilot[0].public_ip : aws_instance.tradepilot.public_ip}/"
}

output "next_steps" {
  value = <<-EOT
    1. Wait ~2–3 min for cloud-init (Docker install).
    2. SSH in with ssh_command above.
    3. If you did not set git_repo_url: copy the repo to /opt/tradepilot.
    4. Create /opt/tradepilot/.env from ops/vps/env.vps.example (Upstox token + DB password).
    5. cd /opt/tradepilot && chmod +x ops/vps/*.sh && docker compose up -d --build
    6. docker compose exec -w /app api python -m alembic -c alembic.ini upgrade head
    7. Open ui_url in the browser (Live banner). API also on :8001.
    8. Install crontab + run_initial_catchup.sh — see ops/vps/README.md
  EOT
}
