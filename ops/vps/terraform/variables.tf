variable "aws_region" {
  description = "AWS region (Mumbai preferred for Upstox latency)."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Name prefix for resources."
  type        = string
  default     = "tradepilot"
}

variable "instance_type" {
  description = "EC2 size. Free Tier: t3.micro (or t2.micro). Paid: t3.small / t3.medium."
  type        = string
  default     = "t3.micro"
}

variable "root_volume_gb" {
  description = "Root EBS size in GB. Free Tier allowance is typically 30 GB total."
  type        = number
  default     = 30
}

variable "key_name" {
  description = "Existing EC2 key pair name in this region (for SSH)."
  type        = string
}

variable "ssh_ingress_cidr" {
  description = "CIDR allowed to SSH (22). Prefer your home /32."
  type        = string
}

variable "api_ingress_cidr" {
  description = "CIDR allowed to hit the direct API (8001). Prefer your home /32."
  type        = string
}

variable "web_ingress_cidr" {
  description = "CIDR allowed to hit the production UI (80). Use 0.0.0.0/0 for public access."
  type        = string
  default     = "0.0.0.0/0"
}

variable "create_elastic_ip" {
  description = "Allocate a static Elastic IP for the instance."
  type        = bool
  default     = true
}

variable "git_repo_url" {
  description = "Optional HTTPS git URL to clone into /opt/tradepilot on first boot. Leave empty to scp/rsync later."
  type        = string
  default     = ""
}

variable "git_ref" {
  description = "Git branch/tag to checkout when git_repo_url is set."
  type        = string
  default     = "main"
}
