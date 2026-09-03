# TradePilot AI — Demo Runbook

Reproduce the North Star demo on **persisted demo candles** (not live Upstox).

## Prerequisites

- Python 3.12+
- Node.js 18+ (for Vite frontend)
- Local PostgreSQL with a database matching `DATABASE_URL`
- Repo checkout at the project root

## 1. Environment

Root `.env` (example):

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/swingdb
ENVIRONMENT=development
MARKET_DATA_SOURCE=demo
UPSTOX_API_BASE_URL=https://api.upstox.com
UPSTOX_ACCESS_TOKEN=
```

Frontend (optional `frontend/.env`):

```env
VITE_API_BASE_URL=http://localhost:8000
```

If unset, the UI defaults to `http://localhost:8000`.

**Note:** Leave `UPSTOX_ACCESS_TOKEN` empty and `MARKET_DATA_SOURCE=demo` for the demo path. Scan/evaluate/backtest read **PostgreSQL** via `MarketDataQueryService`, not Upstox. The UI banner will say demo candles are not live.

When the token arrives:

```env
MARKET_DATA_SOURCE=upstox
UPSTOX_ACCESS_TOKEN=<token>
```

Restart the API, then from `backend/`:

```bash
python scripts/refresh_market_data.py --universe NIFTY_50
```

## 2. Migrate schema

From the **repo root**:

```bash
python -m alembic upgrade head
```

Uses `DATABASE_URL` from the environment or app `.env`. Creates `instruments`, `candles`, and `scan_runs` (scan audit + ranked result payload).

## 3. Seed demo Nifty 500 candles (once, or after DB wipe)

From `backend/`:

```bash
python scripts/seed_demo_nifty500.py --start 2025-12-07 --end 2026-09-03
```

Expected (healthy run):

- symbols attempted ≈ 498  
- success ≈ 498  
- failures = 0  
- candles persisted in the tens/hundreds of thousands  

Re-runs are idempotent (duplicate bars are skipped).

### Refresh without DB wipe (demo)

Demo OHLC is generated for the **requested window**, so do **not** watermark-append partial ranges. Refresh by re-seeding the full window:

```bash
python scripts/seed_demo_nifty500.py --to-today
```

Or pin the same demo window again:

```bash
python scripts/seed_demo_nifty500.py --start 2025-12-07 --end 2026-09-03
```

Then scan with matching start/end in the UI.

## 4. Start backend

From `backend/`:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check:

- http://127.0.0.1:8000/health → `{"status":"ok"}`  
- http://127.0.0.1:8000/health/db → database ok  

## 5. Start frontend

From `frontend/`:

```bash
npm install
npm run dev
```

Open: http://127.0.0.1:5173

## 6. UI smoke test — Nifty 500 scan

1. Scroll to **Nifty 500 Swing Opportunities**.
2. Keep defaults: start `2025-12-07`, end `2026-09-03`, timeframe `1d`.
3. Click **Scan Nifty 500** (may take several seconds).
4. Expect on demo data (approximate):

| Metric | Expected |
|--------|----------|
| Stocks scanned | 498 |
| Eligible | ~109 |
| No setup | ~389 |
| Unavailable / Errors | 0 on a healthy demo seed |

5. Opportunity table lists eligible symbols ranked by quality, with Entry / SL / Target / R:R / score / size.
6. Click a row (or a Top-5 card) to open trade plan, grounded narrative, invalidation, and chart with levels.
7. Metric cards also show Forming / Unavailable / Errors.
8. **Export CSV** downloads the ranked eligible list.
9. Result metadata shows a **Scan run** id; previous runs can be reloaded from the history select.
10. The data banner must say **Demo candles — not live market data** until Upstox is wired.

Optional post-close job (same demo candles):

```bash
python scripts/run_scheduled_scan.py --universe NIFTY_50 --start 2025-12-07 --end 2026-09-03
```

## 7. Optional API check

```bash
curl -X POST http://127.0.0.1:8000/api/v1/scan/opportunities ^
  -H "Content-Type: application/json" ^
  -d "{\"timeframe\":\"1d\",\"start\":\"2025-12-07T00:00:00Z\",\"end\":\"2026-09-03T00:00:00Z\"}"
```

## 8. What this demo proves

```text
Nifty500Universe → PostgreSQL demo candles → StrategyEvaluationService
  → BreakoutRetestConfirmationStrategy → UniverseScanReportService
  → POST /api/v1/scan/opportunities (+ ScanRun) → Frontend
```

Eligible names are demo-regime setups (deterministic). Live market counts will differ after Upstox ingest (when a token is available).

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Scan 500 / connection error | Backend on :8000; `VITE_API_BASE_URL` |
| 0 opportunities / errors | DB seeded? `/health/db` |
| Unavailable &gt; 0 after seed | Re-run `seed_demo_nifty500.py`; check issues list in UI |
| `scan_runs` / relation missing | `python -m alembic upgrade head` |
| Frontend looks old | Hard-refresh Vite page |
