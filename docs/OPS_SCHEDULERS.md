# Ops: NSE master + schedulers (EP7)

## Weekly — rebuild NSE master from Upstox

```bash
cd backend
python scripts/build_nse_universe_from_upstox.py
```

Writes cash EQ + ETF constituent JSON, sector map, instrument keys used by `NSE_ALL` / morning board.

## In-app (FastAPI lifespan)

| When (IST) | Job | Config |
|------------|-----|--------|
| Weekdays `MARKET_DATA_REFRESH_TIME` (default 16:15) | 1d watermark → `NSE_ALL` | `MARKET_DATA_REFRESH_UNIVERSE=NSE_ALL` |
| 09:10–15:15 every N sec | 1m watermark active set | `INTRADAY_1M_REFRESH_*` |
| Startup optional | 1d refresh | `MARKET_DATA_REFRESH_RUN_ON_STARTUP` |

Requires `MARKET_DATA_SOURCE=upstox` and refresh enabled.

## Manual ensure-1m

`POST /api/v1/intraday/ingest/ensure-1m` with `{ "symbols": ["RELIANCE", ...] }` after Morning board ranking.

## Eligibility JSON

Refresh surveillance / CA / short-allowed files per intraday cert runbook when ops updates them.
