# TradePilot VPS — always-on NSE live data

Your Windows PC can be **off**. A Linux VPS runs Postgres + API (in-app schedulers) + cron CLI jobs.

Also see: [docs/LIVE_OPS.md](../../docs/LIVE_OPS.md) · [docs/AWS_INFRA.md](../../docs/AWS_INFRA.md) · [docs/ENVIRONMENTS.md](../../docs/ENVIRONMENTS.md) · [docs/RELEASE_PLAN.md](../../docs/RELEASE_PLAN.md)

---

## 1. Provision (you do this once)

**AWS (recommended):** use Terraform under [`terraform/`](./terraform/) — creates Mumbai EC2, SG (22+8001), 80 GB disk, Elastic IP, and installs Docker via cloud-init. Then skip manual steps 1–3 below and continue from step 4.

1. Create a **Linux VPS** (Ubuntu 22.04+), Mumbai preferred, **2 vCPU / 4–8 GB RAM / 80+ GB disk**.
2. Firewall: allow **22** (SSH), **8001** (API; restrict to your home IP if possible). Do **not** publish Postgres publicly (Compose binds `127.0.0.1:5432`).
3. Install Docker Engine + Compose plugin.
4. Clone or copy this repo to `/opt/tradepilot`:

```bash
sudo mkdir -p /opt/tradepilot /var/log/tradepilot
sudo chown "$USER:$USER" /opt/tradepilot /var/log/tradepilot
# scp/rsync your repo here, or: git clone <url> /opt/tradepilot
cd /opt/tradepilot
```

5. Create `.env` from the example (fill secrets):

```bash
cp ops/vps/env.vps.example .env
nano .env   # UPSTOX_ACCESS_TOKEN, POSTGRES_PASSWORD, etc.
```

Ensure at least:

```env
MARKET_DATA_SOURCE=upstox
UPSTOX_ACCESS_TOKEN=...
MARKET_DATA_REFRESH_UNIVERSE=NSE_ALL
INTRADAY_1M_REFRESH_UNIVERSE=NSE_ALL
INTRADAY_1M_REFRESH_LIMIT=3000
INTRADAY_1M_REFRESH_INTERVAL_SEC=600
```

6. Make scripts executable and start the stack:

```bash
chmod +x ops/vps/*.sh
docker compose build
docker compose up -d
# alembic.ini lives at /app; script_location=backend/alembic
docker compose exec -w /app api python -m alembic -c alembic.ini upgrade head
curl -s http://127.0.0.1:8001/api/v1/product/status
```

Expect `data_source=upstox` and `live_ready=true`.

7. **Initial catch-up** (1d watermark → 1m today → 1m watermark; long — overnight OK):

```bash
nohup /opt/tradepilot/ops/vps/run_initial_catchup.sh &
tail -f /var/log/tradepilot/initial-catchup.log
```

8. Install **cron** (IST):

```bash
crontab -e
```

Paste:

```cron
CRON_TZ=Asia/Kolkata
TRADEPILOT_ROOT=/opt/tradepilot

# After OR — full NSE today 1m
25 9 * * 1-5  /opt/tradepilot/ops/vps/run_1m_today.sh

# Safety 1d watermark
45 16 * * 1-5  /opt/tradepilot/ops/vps/run_1d_watermark.sh

# Weekly master
0 10 * * 0  /opt/tradepilot/ops/vps/run_universe_rebuild.sh
```

---

## 2. What runs when your PC is off

| When (IST) | Mechanism | Job |
|------------|-----------|-----|
| 09:10–15:15 | API in-app loop | 1m refresh `NSE_ALL` (limit 3000, every 600s) |
| 09:25 | Cron | `refresh_intraday_candles.py --mode today --universe NSE_ALL` |
| 16:15 | API in-app | 1d watermark `NSE_ALL` |
| 16:45 | Cron | 1d watermark safety net |
| Sunday 10:00 | Cron | `build_nse_universe_from_upstox.py` |

Logs: `/var/log/tradepilot/*.log`

---

## 3. Token refresh (VPS `.env`)

1. Mint new Upstox access token.
2. Edit `/opt/tradepilot/.env` → `UPSTOX_ACCESS_TOKEN=...`
3. Restart API:

```bash
/opt/tradepilot/ops/vps/restart_api_token.sh
```

Import calendar nudges: [`ops/upstox-token-refresh-reminder.ics`](../upstox-token-refresh-reminder.ics).

---

## 4. Laptop UI → remote API

On your Windows machine, `frontend/.env.local`:

```env
VITE_API_BASE_URL=http://<VPS_PUBLIC_IP>:8001
```

Restart Vite. Laptop can be off while VPS keeps ingesting.

---

## 5. Provision checklist (sign off)

- [ ] VPS created (Mumbai, enough disk)
- [ ] Docker + Compose installed
- [ ] Repo at `/opt/tradepilot` with `.env` (upstox + NSE_ALL refresh)
- [ ] `docker compose up -d` healthy; `live_ready=true`
- [ ] Alembic migrated
- [ ] Cron installed (09:25 / 16:45 / Sun 10:00)
- [ ] `run_initial_catchup.sh` started; `symbols_with_1m` rising
- [ ] Laptop `VITE_API_BASE_URL` points at VPS
- [ ] Token calendar reminder imported

**Go / date / notes:** ________
