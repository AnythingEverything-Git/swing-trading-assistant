# Ops: NSE master + schedulers (EP7)

Personal live-market checklist: **[LIVE_OPS.md](./LIVE_OPS.md)**.  
**Always-on VPS (PC off):** **[ops/vps/README.md](../ops/vps/README.md)** — Docker Compose API + cron.

## Live status dashboard

In the UI: **Account → Ops** (deep link `?view=account&tab=ops`).

API:

- `GET /api/v1/ops/schedulers` — in-app job telemetry + cron/host heartbeats + candle freshness
- `GET /api/v1/ops/readiness?universe=NIFTY_500` — desk SLOs (provider-max 1d, 1m history, today 1m, keys, mutex); `status` green/amber/red
- `GET /api/v1/ops/schedulers/{job_id}` — one job (used by cron enable checks)
- `PATCH /api/v1/ops/schedulers/{job_id}` — `{ "enabled": true|false }` (Ops toggle; in-memory until API restart)
- `POST /api/v1/ops/schedulers/{job_id}/run` — manual start for `inapp_1d`, `inapp_1m`, `cron_1d`, `cron_1m_today`, `host_1m_history`
  - History body (optional): `{ "stage": "NIFTY_50", "lookback_days": 28 }` (also `NIFTY_100_REMAINING` / `NIFTY_500_REMAINING`). Prefer ephemeral worker for large stages.
  - Progress fields on the job: `progress_done` / `progress_total` / `progress_current` / `progress_pct`
- `POST /api/v1/ops/schedulers/heartbeat` — VPS scripts (`ops/vps/common.sh` `scheduler_heartbeat`) report start/done

Cron wrappers call `scheduler_job_enabled` and skip when disabled in Ops.

Host keep-alive (Free Tier): `run_1d_n500_paced.sh` (17:00), `check_nifty500_readiness.sh` (email on red via SES), `watchdog_api_health.sh` (restart api).

In-memory only while the API process is up; heartbeats are best-effort.

## Weekly — rebuild NSE master from Upstox

```bash
cd backend
python scripts/build_nse_universe_from_upstox.py
```

On VPS cron: `ops/vps/run_universe_rebuild.sh` (Sunday 10:00 IST) — also runs `refresh_instrument_key_map.py` (EQ+BE for HEG/HFCL-class).

Writes cash EQ + ETF constituent JSON, sector map, instrument keys used by `NSE_ALL` / morning board.

## In-app (FastAPI lifespan)

| When (IST) | Job | Config |
|------------|-----|--------|
| Weekdays `MARKET_DATA_REFRESH_TIME` (default 16:15) | 1d watermark → `NSE_ALL` | `MARKET_DATA_REFRESH_UNIVERSE=NSE_ALL` |
| 09:10–15:15 every N sec | 1m watermark active set | Free Tier: `INTRADAY_1M_REFRESH_UNIVERSE=NIFTY_50`, `LIMIT=50`, `INTERVAL_SEC=600` |
| Startup optional | 1d refresh | `MARKET_DATA_REFRESH_RUN_ON_STARTUP` |

Requires `MARKET_DATA_SOURCE=upstox` and refresh enabled. **API process must stay up** or these jobs never fire.

**Cron today 1m** defaults to **`NIFTY_500`** (`ops/vps/run_1m_today.sh`). Override with `UNIVERSE=NSE_ALL` only on larger hosts.

Calendar nudges: import [`ops/upstox-token-refresh-reminder.ics`](../ops/upstox-token-refresh-reminder.ics).

## Manual catch-up (PC was off)

Prefer VPS scripts under `ops/vps/`. From `backend/` on any host:

```bash
python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
python scripts/refresh_intraday_candles.py --mode today --universe NIFTY_500
python scripts/refresh_intraday_candles.py --mode watermark --universe NIFTY_500
```

## Manual ensure-1m

`POST /api/v1/intraday/ingest/ensure-1m` with `{ "symbols": ["RELIANCE", ...] }` after Morning board ranking.

## Eligibility JSON

Surveillance / CA / short-allowed files under `backend/app/infrastructure/universe/data/` are **stub PIT dumps** until ops refreshes official exports. The desk filters only what is present in those files — not a live NSE feed.
