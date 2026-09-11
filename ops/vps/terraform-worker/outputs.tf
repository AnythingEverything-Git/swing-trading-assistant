output "instance_id" {
  value = aws_instance.backfill.id
}

output "public_ip" {
  value = aws_instance.backfill.public_ip
}

output "private_ip" {
  value = aws_instance.backfill.private_ip
}

output "live_private_ip" {
  value = local.live_private_ip
}

output "ssh_example" {
  value = "ssh -i <pem> ubuntu@${aws_instance.backfill.public_ip}"
}

output "database_url_hint" {
  value = "postgresql+psycopg://postgres:<PASSWORD>@${local.live_private_ip}:5432/swingdb"
}

output "heartbeat_base" {
  value = "http://${local.live_private_ip}:8001"
}
