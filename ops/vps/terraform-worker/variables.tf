variable "aws_region" {
  description = "Must match tradepilot-live (Mumbai)."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  type    = string
  default = "tradepilot"
}

variable "instance_type" {
  description = "Keep t3.micro for Free Tier eligibility; terminate after job."
  type        = string
  default     = "t3.micro"
}

variable "root_volume_gb" {
  description = "Small disk; delete_on_termination. Live already uses ~30GB Free Tier EBS."
  type        = number
  default     = 8
}

variable "key_name" {
  description = "Same EC2 key pair as tradepilot-live."
  type        = string
}

variable "ssh_ingress_cidr" {
  description = "Home /32 for SSH to worker."
  type        = string
}

variable "live_instance_name" {
  description = "Name tag of the always-on live instance."
  type        = string
  default     = "tradepilot-live"
}
