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
- In-app schedulers (API lifespan): weekday **16:15 IST** 1d `NSE_ALL`; market hours **light 1m** loop for `NIFTY_50` (Free Tier).
- Cron on VPS: **09:25** today 1m **`NIFTY_500`**, readiness checks **09:35/12:00/16:50**, **16:45** 1d safety net, **17:00** paced 1d N500, **\*/5** API watchdog, **Sun 10:00** universe+keys.
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
INTRADAY_1M_REFRESH_UNIVERSE=NIFTY_50
INTRADAY_1M_REFRESH_LIMIT=50
```

VPS example file: [`ops/vps/env.vps.example`](../ops/vps/env.vps.example)

On Free Tier `t3.micro`, do **not** set in-app 1m to `NSE_ALL` / 3000. Use cron `run_1m_today.sh` (default `NIFTY_500`) or `run_nifty500_perfect_today.sh` for bulk today.

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
/opt/tradepilot/ops/vps/run_1d_n500_paced.sh   # after watermark if symbols behind provider_max
UNIVERSE=NIFTY_500 /opt/tradepilot/ops/vps/run_1m_today.sh
# Free Tier perfect-today for the desk universe:
# nohup /opt/tradepilot/ops/vps/run_nifty500_perfect_today.sh &
/opt/tradepilot/ops/vps/smoke_nifty500_readiness.sh
```

On laptop `backend/`:

```bash
python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
python scripts/refresh_intraday_candles.py --mode today --universe NIFTY_500
python scripts/refresh_intraday_candles.py --mode watermark --universe NIFTY_500
```

---

## E. Acceptance (Nifty 500 operational desk)

| Check | Pass |
|-------|------|
| Banner / status | `live_ready=true`; readiness **green** or **amber** (provider lag OK) |
| Readiness API | `GET /api/v1/ops/readiness?universe=NIFTY_500` — ≥99% at `provider_1d_max` |
| Coverage | `POST /api/v1/universe/coverage` universe=`NIFTY_500` — near-zero UNAVAILABLE (keys include HEG/HFCL) |
| Today 1m | After ~09:25, today_1m gate green; desk universe **NIFTY_500** |
| Intraday | Morning board / session on **NIFTY_500** + **persisted** — not mass `INSUFFICIENT_HISTORY` |
| Swing | Find Setups on **NIFTY_500** with scan end = latest session |
| Free Tier | In-app 1m stays `NIFTY_50`/50; eligibility ASM/CA JSON may still be stubs |

**Always-ready (one trading week):** without manual SSH, readiness green/amber by 17:15 on ≥4/5 sessions; paced job + alert restore after 429/missed cron; watchdog recovers hung API within ~10 min.

Note: `stale_risk=Low` may wait on Upstox daily publish — readiness uses **provider-max alignment**, not wall-clock alone. Amber email is off by default (`EMAIL_ON_AMBER=1` to enable).

ASM / corporate-action files under `backend/app/infrastructure/universe/data/` are **PIT stubs** until refreshed — desk filters only what is in those files.
