# TradePilot AWS infrastructure & Console guide

Personal always-on NSE data host. Managed by Terraform under [`ops/vps/terraform/`](../ops/vps/terraform/).  
App deploy / cron: [`ops/vps/README.md`](../ops/vps/README.md) · Live ops: [`LIVE_OPS.md`](./LIVE_OPS.md)  
**Local vs production:** [`ENVIRONMENTS.md`](./ENVIRONMENTS.md) · **Promote / smoke:** [`RELEASE_PLAN.md`](./RELEASE_PLAN.md)

**Region:** Asia Pacific (Mumbai) — `ap-south-1`  
**Account (this deploy):** use the same AWS account as your CLI (`aws sts get-caller-identity`)

> IDs below are from the current Free Tier deploy. After `terraform apply` / replace, refresh them with Console search or `cd ops/vps/terraform && terraform output`.

---

## 1. What we run (architecture)

```text
Internet (your home IP only)
        │
        ├─ TCP 22  ──► EC2 SSH (ubuntu)
        └─ TCP 8001 ──► TradePilot API (Docker)
                              │
                              ├─ Postgres (Docker, bound to 127.0.0.1 only)
                              ├─ In-app schedulers (1d @ 16:15 IST, 1m market hours)
                              └─ Cron CLI jobs (today 1m / 1d safety / weekly universe)
```

| Layer | Where | Notes |
|-------|--------|--------|
| Compute | EC2 `tradepilot-live` | Ubuntu 22.04, Docker Compose |
| Disk | EBS gp3 root | Free Tier target **30 GB** |
| Network | Default VPC + public subnet | Elastic IP for stable address |
| Firewall | Security group `tradepilot-*` | SSH + API from your `/32` only |
| Secrets | `/opt/tradepilot/.env` on the instance | **Not** in Terraform / Console Secrets Manager |
| UI | Your laptop | `VITE_API_BASE_URL=http://<EIP>:8001` |

**Not in AWS (by design):** RDS, ALB, CloudFront, S3 app hosting, ECS/EKS.

---

## 2. Inventory (current Free Tier deploy)

| Resource | Identifier | Expected |
|----------|------------|----------|
| EC2 instance | `i-07403ca20542ab28b` | Name tag `tradepilot-live`, type **`t3.micro`**, state **running** |
| Elastic IP | `13.235.110.243` (`eipalloc-0fea1206fe438ade4`) | Name tag `tradepilot-eip`, associated to the instance |
| Security group | `sg-0bdb091dc79a89057` | Ingress **22** + **8001** from your home `/32` |
| EBS volume | `vol-00969d67a2fcdebae` | **30 GB** gp3, encrypted, attached as root |
| Key pair | `ec2KeyPair` | Used for SSH (private key stays on your PC) |
| API URL | `http://13.235.110.243:8001` | Laptop UI + health checks |
| **UI URL** | **`http://13.235.110.243/`** | Production nginx (same Free Tier box) |
| Tags (all TF resources) | `Project=tradepilot`, `Purpose=always-on-nse-data`, `ManagedBy=terraform` | Filter in Console |

On-box paths: `/opt/tradepilot` (app), `/var/log/tradepilot` (cron logs).

---

## 3. AWS Console walkthrough

Open the console: [https://console.aws.amazon.com/](https://console.aws.amazon.com/)  
**Always set the region to Mumbai (`ap-south-1`)** in the top-right (resources won’t show in other regions).

### 3.1 EC2 instance (is the box up?)

1. Search **EC2** → **Instances**.
2. Filter by tag **Name** = `tradepilot-live`, or paste instance id `i-07403ca20542ab28b`.
3. Check:
   - **Instance state:** `running`
   - **Instance type:** `t3.micro` (Free Tier–oriented)
   - **Public IPv4:** `13.235.110.243`
   - **Security groups:** `tradepilot-…`
   - **Key pair name:** `ec2KeyPair`
4. Open **Storage** tab → root volume ~ **30 GiB** gp3.
5. Open **Monitoring** tab → CPU / status checks (spike during catch-up is normal).

**Actions you might use later:** Instance state → Stop (API goes dark; EIP stays if associated) · Reboot · Connect (EC2 Instance Connect only if enabled; we use SSH + PEM).

### 3.2 Elastic IP (stable address)

1. EC2 → **Network & Security** → **Elastic IPs**.
2. Find `13.235.110.243` / Name `tradepilot-eip`.
3. Confirm **Associated instance ID** = your `tradepilot-live` instance.

Keep the EIP **associated** while the instance runs (idle unattached EIPs can incur charges).

### 3.3 Security group (who can reach you?)

1. EC2 → **Security Groups** → `sg-0bdb091dc79a89057` (or search `tradepilot`).
2. **Inbound rules** should include:
   - TCP **22** from your home IP `/32` (SSH — keep private)
   - TCP **8001** from your home IP `/32` (direct API — keep private)
   - TCP **80** from **`0.0.0.0/0`** (public UI; nginx also proxies `/api`)
3. **Outbound:** all traffic (Upstox, apt, SES).

If the UI can’t reach the API after a home ISP change: update both inbound CIDRs to your new IP (`https://checkip.amazonaws.com`), then `terraform apply` or edit rules here.

### 3.4 EBS volume (disk / Free Tier)

1. EC2 → **Elastic Block Store** → **Volumes**.
2. Open `vol-00969d67a2fcdebae` (or the volume attached to the instance).
3. Confirm **Size** = 30 GiB, **Volume type** = gp3, **State** = in-use.

Growing past 30 GB usually exits Free Tier storage allowance.

### 3.5 Key pairs

1. EC2 → **Key pairs** → `ec2KeyPair`.
2. You cannot download the private key again; keep `ec2KeyPair.pem` safe on your PC.

### 3.6 VPC (default only)

1. VPC → **Your VPCs** → default VPC in `ap-south-1`.
2. No custom VPC was created; instance sits in a default public subnet.

### 3.7 Billing & Free Tier

1. Search **Billing** → **Bills** / **Free Tier**.
2. Confirm EC2 Linux micro hours and EBS GB are within your plan.
3. Optional: **Budgets** → create a small monthly budget + email alert.

### 3.8 What you will *not* find

| Service | Why empty |
|---------|-----------|
| RDS | Postgres is Docker on the EC2 host |
| ECS / EKS / Lambda | Single EC2 + Compose |
| Load Balancers | Direct EIP:8001 |
| Secrets Manager | Secrets live in instance `.env` |

### 3.9 Connect to Postgres from your laptop (SSH tunnel)

Do **not** open port 5432 on the security group. Tunnel through SSH instead.

**1. Start the tunnel** (PowerShell — leave this window open):

```powershell
ssh -i "C:\Users\User\Downloads\AWSec2\ec2KeyPair.pem" `
  -L 5433:127.0.0.1:5432 `
  -N ubuntu@13.235.110.243
```

**2. Read DB password on the VPS** (separate SSH session):

```bash
grep POSTGRES_PASSWORD /opt/tradepilot/.env
```

**3. Local client** (DBeaver / pgAdmin / DataGrip / `psql`):

| Field | Value |
|-------|--------|
| Host | `127.0.0.1` |
| Port | `5433` (local tunnel; remote is 5432) |
| Database | `swingdb` |
| User | `postgres` |
| Password | value of `POSTGRES_PASSWORD` from `.env` |
| SSL | off (traffic is already inside SSH) |

`psql` example:

```powershell
psql "host=127.0.0.1 port=5433 dbname=swingdb user=postgres"
```

Compose binds Postgres to `127.0.0.1:5432` on the instance only — see [`docker-compose.yml`](../docker-compose.yml).

---

## 4. Quick health checks (Console + browser)

| Check | How |
|-------|-----|
| Instance running | EC2 → Instances → `tradepilot-live` |
| API from laptop | Browser or `curl http://13.235.110.243:8001/health` |
| Live data | `curl http://13.235.110.243:8001/api/v1/product/status` → `live_ready=true` |
| UI | Vite with `VITE_API_BASE_URL=http://13.235.110.243:8001` → banner **Live** |

SSH (from your PC):

```powershell
ssh -i "C:\Users\User\Downloads\AWSec2\ec2KeyPair.pem" ubuntu@13.235.110.243
cd /opt/tradepilot && docker compose ps
```

---

## 5. Terraform ↔ Console map

| Terraform resource | Console place |
|--------------------|---------------|
| `aws_instance.tradepilot` | EC2 → Instances |
| `aws_eip.tradepilot` | EC2 → Elastic IPs |
| `aws_security_group.tradepilot` | EC2 → Security Groups |
| root `volume_size` / type | EC2 → Volumes |
| `key_name` | EC2 → Key pairs |

Change sizing / CIDRs in `ops/vps/terraform/terraform.tfvars`, then:

```bash
cd ops/vps/terraform
terraform plan
terraform apply
```

Destroy everything (stops charges for this stack): `terraform destroy`.

---

## 6. Free Tier reminders

- Prefer **`t3.micro`** + **≤ 30 GB** EBS while eligible.
- One always-on instance ≈ 730–744 hours/month (within typical 750 hr micro allowance).
- Do not leave an **unattached** Elastic IP sitting around.
- Candle growth can fill 30 GB — monitor volume size / disk `%` on the host (`df -h`).

Details: [`ops/vps/terraform/README.md`](../ops/vps/terraform/README.md).
