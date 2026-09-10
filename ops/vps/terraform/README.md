# Terraform — TradePilot always-on EC2 (AWS Free Tier–oriented)

Provisions a Mumbai Ubuntu 22.04 box with Docker, security group (22 + 8001), **30 GB** disk, optional Elastic IP, and 2 GB swap (for `t3.micro`). Application secrets (`.env`) and `docker compose up` stay manual — see [../README.md](../README.md).

**Console walkthrough + live inventory:** [docs/AWS_INFRA.md](../../../docs/AWS_INFRA.md)

## Free Tier checklist

Stay inside Free Tier **only if** all of these are true:

| Item | Free Tier target | Notes |
|------|------------------|--------|
| Instance | **`t3.micro`** (or `t2.micro`) | **Not** `t3.medium` / `t3.small` on older 12‑month plans |
| Hours | ≤ **750 / month** | One always-on instance ≈ OK |
| EBS | ≤ **30 GB** total | Candles will fill disk; prune or pay later |
| EIP | Attached to running instance | Idle EIPs are billed |
| Account | Still in Free Tier window | Check Billing → Free Tier |

Confirm eligibility in the [AWS Free Tier](https://aws.amazon.com/free/) / EC2 console for **your** account age (rules changed around July 2025).

**Tradeoff:** `t3.micro` (1 GB RAM) is tight for full NSE_ALL + Postgres. Swap is added on boot; prefer slower 1m intervals / lower limits if the box OOMs.

## Prerequisites

1. [AWS CLI](https://docs.aws.amazon.com/cli/) configured (`aws configure`) with rights to EC2, VPC, EIP in `ap-south-1`.
2. [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.5.
3. An **EC2 key pair** in `ap-south-1`.
4. Your home public IP `/32` for SSH/API lockdown.

## Apply

```bash
cd ops/vps/terraform
cp terraform.tfvars.example terraform.tfvars
# edit: key_name, ssh_ingress_cidr, api_ingress_cidr

terraform init
terraform plan
terraform apply
```

Outputs: `public_ip`, `ssh_command`, `api_base_url`.

Wait 2–3 minutes for cloud-init, then continue from **§1 step 4** in [../README.md](../README.md).

## Resize from a paid box (t3.medium / 80 GB → Free Tier)

Shrinking the root volume **recreates** the instance (candle DB on disk is lost). Snapshot first if you care about data, then:

```bash
terraform apply
# expect: destroy/recreate aws_instance (volume_size 80 → 30, type → t3.micro)
```

Re-copy `/opt/tradepilot`, recreate `.env`, `docker compose up`, re-run catch-up.

## Destroy

```bash
terraform destroy
```

## What this does / does not

| Does | Does not |
|------|----------|
| EC2 + SG + EIP + Docker + swap | Guarantee $0 if account is past Free Tier |
| Lock SSH/API to your CIDR | Open Postgres publicly |
| Default Free Tier sizing | Put Upstox token in Terraform |
