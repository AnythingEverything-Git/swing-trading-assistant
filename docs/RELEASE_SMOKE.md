# Release smoke — Checkpoint I (practice trades)

Prerequisites: backend + frontend running, Alembic head includes `0005_paper_trades`, DB has recent candles. Prefer `NIFTY_50` for speed. Practice mode is **fake money only**.

## Checklist (map to PROJECT_PLAN Checkpoint I)

1. **Default off** — Find setups / Practice trades: practice checkbox unchecked until you enable it; set starting capital + risk %.
2. **Watches from scan** — Enable practice → Run scan → response / UI shows watches created (`PENDING` / `paper_opened_count` > 0 when qty > 0).
3. **Banner** — `PRACTICE TRADES ONLY — fake money, no real broker orders` visible.
4. **Waiting book** — Pending list shows buy/sell at, safety exit, profit goal, shares, live price; price ticks ~15s.
5. **Fill → In trade → exit** — When LTP reaches entry, status becomes In trade; auto-closes at Stop or Target (LONG and SHORT if available). If market will not hit during the session: call `POST /api/v1/paper/tick` after adjusting expectations, or use manual Close after a forced fill path.
6. **Cancel / Close / skip** — Cancel one PENDING watch; Close one OPEN trade; re-scan does not duplicate PENDING/OPEN symbols.
7. **Start real trade alert** — On entry fill: in-app alert; browser Notification if permission granted.
8. **Live practice strip** — Strip under data banner shows open P/L, remaining capital, live trades.
9. **Capital strip** — Starting / invested / remaining / account value; remaining updates after closes.
10. **Timer + ETA** — Open trades show running duration and estimated profit-by from `GET /api/v1/paper/outlook`.

## Pass criteria

All 10 items observed without blockers. Note date and environment (`MARKET_DATA_SOURCE`) in the project plan status line when claiming release readiness.

## Related ops

With `MARKET_DATA_SOURCE=upstox`, the API runs weekday watermark candle refresh at `MARKET_DATA_REFRESH_TIME` (default 16:15 IST). Keep the API process up for that job. Manual: `python scripts/refresh_market_data.py --mode watermark --universe NIFTY_50`.
