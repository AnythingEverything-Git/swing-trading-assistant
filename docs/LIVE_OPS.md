# Live ops — personal live market (no demo)

Keep TradePilot on **Upstox live** candles.

| Mode | When to use |
|------|-------------|
| **Always-on VPS** (recommended) | PC can be **off** — ingest + schedulers on a Linux cloud host |
| **Laptop market hours** | API only while your Windows PC is awake |

**VPS deploy + cron:** [`ops/vps/README.md`](../ops/vps/README.md)  
**Environments (local vs AWS):** [`ENVIRONMENTS.md`](./ENVIRONMENTS.md)  
**Release promote + smoke:** [`RELEASE_PLAN.md`](./RELEASE_PLAN.md)  
**AWS infra + Console guide:** [`AWS_INFRA.md`](./AWS_INFRA.md)  
Related: [OPS_SCHEDULERS.md](./OPS_SCHEDULERS.md) · [RELEASE_SMOKE.md](./RELEASE_SMOKE.md)

---

## A. Always-on VPS (PC can be off)

### Architecture

- VPS runs `docker compose` → **Postgres** + **API** ([`docker-compose.yml`](../docker-compose.yml)).
- In-app schedulers (API lifespan): weekday **16:15 IST** 1d `NSE_ALL`; market hours **1m** loop for `NSE_ALL`.
- Cron on VPS: **09:25** today 1m, **16:45** 1d safety net, **Sun 10:00** universe rebuild.
- Your laptop only runs the **UI**, pointed at the VPS API.

### Laptop UI

`frontend/.env.local`:

```env
VITE_API_BASE_URL=http://<VPS_PUBLIC_IP>:8001
```

Restart Vite after changing this.

### Token refresh (VPS)

1. Mint Upstox token → edit `/opt/tradepilot/.env`
2. `/opt/tradepilot/ops/vps/restart_api_token.sh`
3. Confirm `curl http://127.0.0.1:8001/api/v1/product/status` → `live_ready=true`

Calendar: [`ops/upstox-token-refresh-reminder.ics`](../ops/upstox-token-refresh-reminder.ics)

### Follow the provision checklist

**AWS:** [`ops/vps/terraform/README.md`](../ops/vps/terraform/README.md) (`terraform apply` → EC2 + Docker), then finish app steps in [`ops/vps/README.md`](../ops/vps/README.md).

Complete every box in [`ops/vps/README.md`](../ops/vps/README.md) §5 (VPS create → compose up → cron → initial catch-up → UI URL).

---

## B. Lock live data (any host)

```env
MARKET_DATA_SOURCE=upstox
UPSTOX_ACCESS_TOKEN=<current bearer token>

MARKET_DATA_REFRESH_ENABLED=true
MARKET_DATA_REFRESH_TIME=16:15
MARKET_DATA_REFRESH_UNIVERSE=NSE_ALL
MARKET_DATA_REFRESH_RUN_ON_STARTUP=false

INTRADAY_1M_REFRESH_ENABLED=true
INTRADAY_1M_REFRESH_INTERVAL_SEC=600
INTRADAY_1M_REFRESH_UNIVERSE=NSE_ALL
INTRADAY_1M_REFRESH_LIMIT=3000
```

VPS example file: [`ops/vps/env.vps.example`](../ops/vps/env.vps.example)

Never set `MARKET_DATA_SOURCE=demo` for live trading days.

**Verify:**

```bash
curl -s http://127.0.0.1:8001/api/v1/product/status
```

Expect `data_source=upstox` and `live_ready=true`. UI banner must say **Live**.

---

## C. Laptop-only market-hours habit (fallback)

Use only if you have **not** deployed the VPS yet.

| Time (IST) | Action |
|------------|--------|
| ~08:45 | Start Postgres + API + UI |
| 09:10–15:15 | Leave API running |
| ~16:15 | Keep API up for 1d watermark |
| After close | Optional stop |

When the PC is off, **no** ingest runs in this mode.

---

## D. Manual catch-up

On VPS (preferred):

```bash
/opt/tradepilot/ops/vps/run_initial_catchup.sh
# or individually:
/opt/tradepilot/ops/vps/run_1d_watermark.sh
/opt/tradepilot/ops/vps/run_1m_today.sh
```

On laptop `backend/`:

```bash
python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
python scripts/refresh_intraday_candles.py --mode today --universe NSE_ALL
python scripts/refresh_intraday_candles.py --mode watermark --universe NSE_ALL
```

---

## E. Acceptance

- Banner Live; `symbols_with_candles` ≈ NSE master size.
- After catch-up / market day: `symbols_with_1m` rises well above ~29.
- Intraday session no longer mass-**missing OR** for names that have 1m.
- Find setups claim stays Live Upstox.
