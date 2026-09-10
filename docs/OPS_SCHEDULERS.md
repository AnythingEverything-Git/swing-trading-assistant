# Ops: NSE master + schedulers (EP7)

Personal live-market checklist: **[LIVE_OPS.md](./LIVE_OPS.md)**.  
**Always-on VPS (PC off):** **[ops/vps/README.md](../ops/vps/README.md)** — Docker Compose API + cron.

## Weekly — rebuild NSE master from Upstox

```bash
cd backend
python scripts/build_nse_universe_from_upstox.py
```

On VPS cron: `ops/vps/run_universe_rebuild.sh` (Sunday 10:00 IST).

Writes cash EQ + ETF constituent JSON, sector map, instrument keys used by `NSE_ALL` / morning board.

## In-app (FastAPI lifespan)

| When (IST) | Job | Config |
|------------|-----|--------|
| Weekdays `MARKET_DATA_REFRESH_TIME` (default 16:15) | 1d watermark → `NSE_ALL` | `MARKET_DATA_REFRESH_UNIVERSE=NSE_ALL` |
| 09:10–15:15 every N sec | 1m watermark active set | `INTRADAY_1M_REFRESH_*` (VPS: `NSE_ALL`, limit 3000, 600s) |
| Startup optional | 1d refresh | `MARKET_DATA_REFRESH_RUN_ON_STARTUP` |

Requires `MARKET_DATA_SOURCE=upstox` and refresh enabled. **API process must stay up** or these jobs never fire.

Calendar nudges: import [`ops/upstox-token-refresh-reminder.ics`](../ops/upstox-token-refresh-reminder.ics).

## Manual catch-up (PC was off)

Prefer VPS scripts under `ops/vps/`. From `backend/` on any host:

```bash
python scripts/refresh_market_data.py --mode watermark --universe NSE_ALL
python scripts/refresh_intraday_candles.py --mode today --universe NSE_ALL
python scripts/refresh_intraday_candles.py --mode watermark --universe NSE_ALL
```

## Manual ensure-1m

`POST /api/v1/intraday/ingest/ensure-1m` with `{ "symbols": ["RELIANCE", ...] }` after Morning board ranking.

## Eligibility JSON

Refresh surveillance / CA / short-allowed files per intraday cert runbook when ops updates them.
