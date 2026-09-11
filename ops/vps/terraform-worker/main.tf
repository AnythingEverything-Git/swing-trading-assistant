data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_instances" "live" {
  filter {
    name   = "tag:Name"
    values = [var.live_instance_name]
  }

  filter {
    name   = "instance-state-name"
    values = ["running"]
  }
}

data "aws_instance" "live" {
  instance_id = sort(data.aws_instances.live.ids)[0]
}

data "aws_security_groups" "live" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "group-name"
    values = ["${var.project_name}-*"]
  }
}

locals {
  live_sg_id         = sort(data.aws_security_groups.live.ids)[0]
  live_private_ip    = data.aws_instance.live.private_ip
  subnet_id          = data.aws_instance.live.subnet_id
}

resource "aws_security_group" "backfill" {
  name_prefix = "${var.project_name}-backfill-"
  description = "Ephemeral TradePilot 1m backfill worker (SSH only)."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_ingress_cidr]
  }

  egress {
    description = "All egress (Upstox, apt, live Postgres/API)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-backfill-sg"
  }
}

# Allow worker → live Postgres (compose must bind beyond 127.0.0.1; SG still blocks public).
resource "aws_security_group_rule" "live_postgres_from_worker" {
  type                     = "ingress"
  description              = "Ephemeral backfill worker to Postgres"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = local.live_sg_id
  source_security_group_id = aws_security_group.backfill.id
}

# Allow worker → live API heartbeats (Ops progress).
resource "aws_security_group_rule" "live_api_from_worker" {
  type                     = "ingress"
  description              = "Ephemeral backfill worker to API heartbeats"
  from_port                = 8001
  to_port                  = 8001
  protocol                 = "tcp"
  security_group_id        = local.live_sg_id
  source_security_group_id = aws_security_group.backfill.id
}

resource "aws_instance" "backfill" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = var.key_name
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.backfill.id]
  associate_public_ip_address = true

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    project_name = var.project_name
  })

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = {
    Name = "${var.project_name}-backfill"
  }
}
