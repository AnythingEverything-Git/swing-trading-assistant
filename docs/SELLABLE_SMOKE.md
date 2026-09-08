# Sellable smoke (EP9)

Prerequisites: API on `8001` (or `VITE_API_BASE_URL`), UI on `5173`, Alembic head, demo or Upstox data.

## Filters + NSE_ALL

1. `GET /api/v1/universe/supported` → includes `NSE_ALL`, default `NSE_ALL`.
2. `GET /api/v1/universe/presets` → liquid / ETF presets.
3. `POST /api/v1/universe/preview` with `{ "universe": "NSE_ALL", "filters": { "asset_class": "ETF" } }` → `output_count` ≪ cash total.
4. Find setups: universe **NSE all**, Guided on → Scan (prefer short date + filters). Progress/cancel works; `filter_coverage` in result when filters applied.

## Desks

5. Home → Swing / Intraday / Research / Practice book navigation works.
6. Intraday: Morning board with filters; stocks vs ETFs tables; optional **Ensure 1m**.
7. Research: load any NSE symbol; dual fit badges visible.
8. Ask TradePilot: without evidence, inventing entry is refused; with evidence, levels repeated only.
9. Account: signup stub, plans, legal, alert preferences.
10. Practice book: swing + intraday tabs load.

## Claims QA

- Banner / paper claim: practice = fake money.
- AI claim: never invents Entry/SL/Target/OR.
- Marketing: assistant product — multi-year 1m cert still **NO_GO** for strategy edge claims ([`INTRADAY_CERTIFICATION_V1.md`](./INTRADAY_CERTIFICATION_V1.md)).

## Ops

- 1d watermark universe default `NSE_ALL` (`MARKET_DATA_REFRESH_UNIVERSE`).
- 1m active-set loop: `INTRADAY_1M_REFRESH_*` during 09:10–15:15 IST.
- Weekly master: `python backend/scripts/build_nse_universe_from_upstox.py` (ops runbook).

See also [`RELEASE_SMOKE.md`](./RELEASE_SMOKE.md), [`INTRADAY_SMOKE.md`](./INTRADAY_SMOKE.md), [`LAUNCH_CHECKLIST.md`](./LAUNCH_CHECKLIST.md).
