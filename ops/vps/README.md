# TradePilot VPS — always-on NSE live data

Your Windows PC can be **off**. A Linux VPS runs Postgres + API (in-app schedulers) + cron CLI jobs.

Also see: [docs/LIVE_OPS.md](../../docs/LIVE_OPS.md) · [docs/AWS_INFRA.md](../../docs/AWS_INFRA.md) · [docs/ENVIRONMENTS.md](../../docs/ENVIRONMENTS.md) · [docs/RELEASE_PLAN.md](../../docs/RELEASE_PLAN.md)

---

## 1. Provision (you do this once)

**AWS (recommended):** use Terraform under [`terraform/`](./terraform/) — creates Mumbai EC2, SG (22+8001), 80 GB disk, Elastic IP, and installs Docker via cloud-init. Then skip manual steps 1–3 below and continue from step 4.

1. Create a **Linux VPS** (Ubuntu 22.04+), Mumbai preferred, **2 vCPU / 4–8 GB RAM / 80+ GB disk**.
2. Firewall: allow **22** (SSH), **8001** (API; restrict to your home IP if possible). Postgres is published on `:5432` for the ephemeral worker SG only — never open 5432 to `0.0.0.0/0`.
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

7b. **Make Nifty 500 perfect for today** (Free Tier desk; preferred over NSE_ALL):

```bash
# Pause in-app 1m so host job owns Upstox + CPU
sed -i 's/^INTRADAY_1M_REFRESH_ENABLED=.*/INTRADAY_1M_REFRESH_ENABLED=false/' /opt/tradepilot/.env
docker compose -f /opt/tradepilot/docker-compose.yml --project-directory /opt/tradepilot up -d api

nohup /opt/tradepilot/ops/vps/run_nifty500_perfect_today.sh &
tail -f /var/log/tradepilot/nifty500-perfect-today.log
```

Then re-enable light in-app (`NIFTY_50`, limit 50). For full NSE_ALL catch-up (heavy), see `run_nse_all_perfect_today.sh`.

8. Install **cron** (IST):

```bash
crontab -e
```

Paste:

```cron
CRON_TZ=Asia/Kolkata
TRADEPILOT_ROOT=/opt/tradepilot

# After OR — Nifty 500 today 1m (Free Tier). Override UNIVERSE=NSE_ALL if needed.
25 9 * * 1-5  /opt/tradepilot/ops/vps/run_1m_today.sh

# Readiness gate + SES email if red (amber = provider lag, no email by default)
35 9 * * 1-5  /opt/tradepilot/ops/vps/check_nifty500_readiness.sh
0 12 * * 1-5  /opt/tradepilot/ops/vps/check_nifty500_readiness.sh
50 16 * * 1-5 /opt/tradepilot/ops/vps/check_nifty500_readiness.sh

# Safety 1d watermark
45 16 * * 1-5  /opt/tradepilot/ops/vps/run_1d_watermark.sh

# Paced 1d retry for N500 symbols behind provider_max (429 backoff)
0 17 * * 1-5  /opt/tradepilot/ops/vps/run_1d_n500_paced.sh

# API /health watchdog — restart api after 3 consecutive fails
*/5 * * * *   /opt/tradepilot/ops/vps/watchdog_api_health.sh

# Weekly master + Nifty 500 EQ+BE instrument keys
0 10 * * 0  /opt/tradepilot/ops/vps/run_universe_rebuild.sh
```

**Amber vs red:** `GET /api/v1/ops/readiness?universe=NIFTY_500` — **green** all gates ok; **amber** aligned to Upstox `provider_1d_max` but calendar behind (not our gap); **red** our lag / token / keys / stuck mutex. Account → Ops shows the readiness strip.

**Manual recovery:** `run_1d_n500_paced.sh`, `run_1m_today.sh` / `run_nifty500_perfect_today.sh`, `docker compose restart api` (or reboot). Smoke: `ops/vps/smoke_nifty500_readiness.sh`.
---

## 2. What runs when your PC is off

| When (IST) | Mechanism | Job |
|------------|-----------|-----|
| 09:10–15:15 | API in-app loop | 1m refresh **NIFTY_50** (limit 50, every 600s) |
| 09:25 | Cron | `refresh_intraday_candles.py --mode today --universe NIFTY_500` |
| 09:35 / 12:00 / 16:50 | Cron | readiness check + email if **red** |
| 16:15 | API in-app | 1d watermark `NSE_ALL` |
| 16:45 | Cron | 1d watermark safety net |
| 17:00 | Cron | paced 1d N500 retry (429 backoff) |
| every 5 min | Cron | `/health` watchdog → `compose restart api` |
| Sunday 10:00 | Cron | universe rebuild + `refresh_instrument_key_map.py` |

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
- [ ] Cron installed (09:25 / readiness / 16:45 / 17:00 paced / watchdog / Sun 10:00)
- [ ] `run_initial_catchup.sh` started; `symbols_with_1m` rising
- [ ] Laptop `VITE_API_BASE_URL` points at VPS
- [ ] Token calendar reminder imported

**Go / date / notes:** ________

---

## 6. Ephemeral staged 1m backfill worker (Free Tier)

Live (`tradepilot-live`) already uses most Free Tier micro-hours and ~30 GB EBS. Do **not** leave a second micro running.

| Do | Don’t |
|----|--------|
| `t3.micro` + **8 GB** disk, **no EIP** | Second always-on instance or second EIP |
| Stages: **Nifty 50 → 100 remaining → 500 remaining** | One-shot NSE_ALL inside the live API process |
| `stop_backfill_worker.sh` (`terraform destroy`) when done | Leave worker **stopped** (disk still bills) |

Scripts: [`worker/`](./worker/) · Terraform: [`terraform-worker/`](./terraform-worker/) · Docs: [`docs/AWS_INFRA.md`](../../docs/AWS_INFRA.md) §7.

```bash
export TRADEPILOT_PEM=/path/to/ec2KeyPair.pem
export TRADEPILOT_LIVE_ENV=/path/to/live.env
./ops/vps/worker/start_backfill_worker.sh
./ops/vps/worker/run_staged_backfill.sh --stage NIFTY_50
./ops/vps/worker/stop_backfill_worker.sh
```

Ops UI (Account → Ops) has the three stage buttons for small on-box runs; prefer the worker for Free Tier safety.
