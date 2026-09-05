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

## Async scan + email deep links (Phase A)

11. **Async scan** — Click Scan on Nifty 50/500: button shows queued/scanning progress; HTTP returns quickly (202); results appear after poll without holding the POST open.
12. **Deep link** — Open `http://127.0.0.1:5173/?view=scan&run=<id>&symbol=<SYM>` for a completed run: Find setups loads that run and opens the symbol drawer.
13. **Email ops** — Schedule `python scripts/run_scheduled_scan.py` and `python scripts/run_premarket_alert.py` via Task Scheduler/cron (email only). Alerts include “Open this scan” when `FRONTEND_BASE_URL` is set.

## Phase B — AI moat

14. **Template mode** — With `NARRATIVE_PROVIDER=template` (or no `GOOGLE_API_KEY`), scan why/invalidation match deterministic templates; Entry/SL/Target unchanged.
15. **LLM mode Top-N why** — With `NARRATIVE_PROVIDER=llm` + key: Top cards/table show polished why; subtle **AI-polished** badge only when `narrative_source=llm`.
16. **Invalidation** — Visible on Top cards + Setup/Overview drawer; prices still strategy-only.
17. **Quality critic** — Advisory critique/flags appear; sort/rank still follows rules `quality_score`.
18. **Brief email** — Premarket/scheduled alert includes AI brief when LLM on; template body still sends when LLM off. EOD: `python scripts/run_scheduled_scan.py --brief eod --reuse-latest` or `run_premarket_alert.py --mode eod`.
19. **Data issues** — One UNAVAILABLE (e.g. HFCL) shows a quiet **Data note**, not a loud pink lecture; ERROR or many UNAVAILABLE still uses the issues box. UNAVAILABLE ≠ no setup.
20. **Backtest blurb** — Research desk metrics show interpretation under metrics; refuses overclaim when too few trades.
21. **Personal book API** — `POST /api/v1/scan/book` picks are reproducible without LLM; explanation optional. **Not shown on Find setups** (Top-N cards are the desk).
22. **Similar setups** — Drawer Overview shows deduped peers (prefer one per symbol) with measured forward N-bar outcomes (`GET /api/v1/research/{symbol}/similar-setups`).

## Pass criteria

All 10 items observed without blockers. Note date and environment (`MARKET_DATA_SOURCE`) in the project plan status line when claiming release readiness.

Items 11–13 required for Phase A (excl. auth/Telegram) sellable bar. Items 14–22 required for Phase B AI moat.

## Related ops

With `MARKET_DATA_SOURCE=upstox`, the API runs weekday watermark candle refresh at `MARKET_DATA_REFRESH_TIME` (default 16:15 IST). Keep the API process up for that job. Manual: `python scripts/refresh_market_data.py --mode watermark --universe NIFTY_50`.
