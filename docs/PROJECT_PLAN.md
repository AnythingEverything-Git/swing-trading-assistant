# TradePilot AI — Project Plan (from now onwards)

**Last updated:** 2026-09-03  
**Status:** Live Upstox data active (`MARKET_DATA_SOURCE=upstox`). Product features include: multi-index scan, ranked opportunities, forming watchlist, interactive TradingView-style charts, live current prices, quality scoring, position sizing, narratives, alerts, scan history, and backtest realism.  
**Data:** 497 Nifty symbols ingested via Upstox 1d candles. Demo mode still available via `MARKET_DATA_SOURCE=demo`.

---

## 1. Product North Star (immutable)

TradePilot AI must answer:

> **Out of the selected Nifty universe (50 / 100 / 200 / 500), which stocks have a valid swing-trading opportunity RIGHT NOW?**

For every eligible stock, provide:

| Field | Source today |
|-------|----------------|
| Symbol | Universe + scan |
| Direction | `TradeCandidate.direction` |
| Entry | `TradeCandidate.entry_price` |
| Stop loss | `TradeCandidate.stop_loss` |
| Target | `TradeCandidate.target` |
| Risk / reward | `TradeCandidate.risk_reward_ratio` |
| Current price | Live Upstox quote (auto-refreshes every 15s) |
| Quality score | `QualityScore` (rules-based ranking) |
| Position size | Based on account equity + risk % |
| Why eligible | `StrategyEvidence` (decision + structure) + template narrative |

**Do not turn this into:** a generic screener, chatbot, autonomous trading bot, portfolio app, or broker OMS.

**Same rules for scan and backtest:** `BreakoutRetestConfirmationStrategy` with last-bar confirmation = "NOW".

---

## 2. Where we are (baseline)

### Working end-to-end path (live Upstox)

```text
get_universe(NIFTY_50|100|200|500)  → curated nested snapshots
        ↓
UpstoxMarketDataProvider → refresh_market_data.py → PostgreSQL
        ↓
MarketDataQueryService (persisted candles)
        ↓
StrategyEvaluationService (+ classify for forming)
        ↓
BreakoutRetestConfirmationStrategy
        ↓
UniverseScanReportService (ELIGIBLE / FORMING / NO_SETUP / UNAVAILABLE / ERROR)
        ↓
present_scan (rank + size + narrative)
        ↓
POST /api/v1/scan/opportunities (+ ScanRun + live quote enrichment)
        ↓
Frontend: ranked table + forming watchlist + interactive chart + live prices
```

### Completed building blocks

| Area | Done |
|------|------|
| Strategy + last-bar NOW contract | Yes |
| StrategyEvaluationService (+ classify) | Yes |
| OpportunityScanService (fail-fast) | Yes |
| UniverseScanReportService (status ledger + forming) | Yes |
| Nifty 50 / 100 / 200 / 500 curated snapshots | Yes (50 ⊂ 100 ⊂ 200 ⊂ 500) |
| Upstox instrument-key mapping (497 symbols) | Yes |
| UpstoxMarketDataProvider (historical candles) | Yes |
| Upstox live quotes (`get_last_traded_prices`) | Yes |
| DemoMarketDataProvider (fallback) | Yes |
| Market data source switching (plug-and-play) | Yes |
| Quality scoring (`score_opportunity`) | Yes |
| Position sizing (account equity + risk %) | Yes |
| Template narratives + invalidation copy | Yes |
| Forming setup detection (`inspect_forming`) | Yes |
| Scan presentation layer (`present_scan`) | Yes |
| Alert composer + delivery (Telegram-ready) | Yes |
| Product status service (data freshness) | Yes |
| Scan history (persist + reload) | Yes |
| Interactive chart (lightweight-charts: candles + volume + S/R + markers) | Yes |
| Live current price in scan results (auto-refresh 15s) | Yes |
| Quote API (`GET /api/v1/market-data/quotes`) | Yes |
| Backtest realism (compounding, DD, gaps, costs) | Yes |
| ScanRun persistence (+ `result_payload` JSON) | Yes |
| Volume BigInteger migration | Yes |
| Scan API + universe request field | Yes |
| Scan UI + Research desk menu | Yes |
| Detail overlay, top-ranked cards, See more, CSV | Yes |
| INR rounding + dark/light theme | Yes |
| Demo runbook | Yes |

### Explicitly not done

- Auth, billing, portfolio, broker execution
- SHORT setups
- LLM provider (template narratives ship now; `NARRATIVE_PROVIDER=template`)
- WebSocket live ticks (polling quotes every 15s instead)
- Multi-timeframe beyond `1d`

---

## 2b. Product use cases

| ID | Actor | Use case | Status |
|----|-------|----------|--------|
| UC1 | Trader | Scan a Nifty index for setups **RIGHT NOW** | ✅ Live |
| UC2 | Trader | See **current trading price** on every symbol | ✅ Live (auto-refreshes 15s) |
| UC3 | Trader | Understand **why** a name is eligible | ✅ Detail overlay + narrative |
| UC4 | Trader | View **interactive chart** with S/R + volume | ✅ lightweight-charts |
| UC5 | Trader | See **forming setups** (not yet confirmed) | ✅ Forming watchlist |
| UC6 | Trader | **Rank** setups by quality score | ✅ Top-N cards + score column |
| UC7 | Trader | **Position sizing** per setup | ✅ Quantity + risk amount |
| UC8 | Trader | Browse long result lists | ✅ Top-10 + See more/less |
| UC9 | Trader | Export eligibles | ✅ CSV |
| UC10 | Trader | Trust partial data | ✅ Unavailable/Error cards + issues |
| UC11 | Trader | Switch product areas | ✅ Watchlist scan ↔ Research desk |
| UC12 | Trader | Evaluate / backtest one symbol | ✅ Research desk + live quote |
| UC13 | Trader | Reload past scan results | ✅ Scan history dropdown |
| UC14 | Operator | Reproduce from checkout | ✅ Demo runbook |
| UC15 | Operator | Refresh market data | ✅ `refresh_market_data.py` |
| UC16 | Operator | Audit a scan | ✅ `scan_run_id` + full JSON payload |

**Out of scope:** broker orders, portfolio tracking, WebSocket live ticks, auth/billing.

---

## 2c. UI / product checkpoints (run at http://127.0.0.1:5173)

### Checkpoint A — Scan North Star
1. Top menu switches **Watchlist scan** ↔ **Research desk**.
2. Theme toggle: **Dark ↔ Light**, persists after refresh.
3. Universe select: **Nifty 50 / 100 / 200 / 500**; defaults to Nifty 500.
4. Data banner shows source (demo or live Upstox) + last candle date + symbol count.
5. Scan → metrics show symbols scanned / eligible / forming / no setup / unavailable / errors.
6. **Current price** and **% change** columns in both eligible and forming tables.

### Checkpoint B — Ranked results + current price
1. **Top-N cards** show rank, symbol, current price, change %, entry, score, qty.
2. Table has **Rank, Current, Change** columns alongside Entry / SL / Target / R:R / Score / Qty.
3. Prices auto-refresh every 15 seconds.

### Checkpoint C — Detail overlay + interactive chart
1. Click any symbol → detail drawer opens.
2. **Interactive chart** (TradingView-style): candlesticks + volume bars + Resistance/Support/Entry/SL/Target lines + B/R/C markers.
3. Chart supports **pan, zoom, crosshair**.
4. Trade plan shows current price + change %.
5. NOW badge active when confirmation date matches scan end.

### Checkpoint D — Forming watchlist
1. Forming table shows stage, current price, change, resistance, bars remaining.
2. Click forming symbol → detail drawer with chart + forming evidence.

### Checkpoint E — Export, history & audit
1. Export CSV with rounded numeric columns.
2. Scan history dropdown: reload any past scan.
3. Alert preview in collapsible section.

### Checkpoint F — Research desk
1. Menu → Research desk; live quote shown below form.
2. Evaluate / backtest use same INR formatting.

---

## 3. Guiding principles

1. **Thin slices** — one vertical capability at a time; reuse existing strategy/eval/scan.
2. **Persisted candles for research/scan** — evaluate/scan/backtest consume `MarketDataQueryService`.
3. **Never map data failures to `NO_SETUP`.**
4. **Demo vs live** — `MARKET_DATA_SOURCE` env var; plug-and-play switching.
5. **Label curated universe** — versioned snapshots; nested: 50 ⊂ 100 ⊂ 200 ⊂ 500.
6. **Grounded narratives** — template-based from strategy evidence; no LLM-invented prices.

---

## 4. Roadmap

### Phase 0 — Demo milestone — **Done**

| ID | Task | Status |
|----|------|--------|
| P0.1 | Demo UI + backend slices | ✅ |
| P0.2 | Demo checklist | ✅ |
| P0.3 | Demo runbook | ✅ |

### Phase 1 — Live Upstox data — **Done**

| ID | Task | Status |
|----|------|--------|
| P1.1 | Upstox token + base URL configured | ✅ |
| P1.2 | Full NSE → `instrument_key` for 497 symbols | ✅ |
| P1.3 | Bulk ingest `1d` candles | ✅ |
| P1.4 | Plug-and-play `MARKET_DATA_SOURCE` switching | ✅ |
| P1.5 | Live quotes API (`get_last_traded_prices`) | ✅ |
| P1.6 | Volume BigInteger migration | ✅ |

### Phase 2 — Scan result robustness — **Done**

`UniverseScanReportService` + API counts + UI metrics/issues.

### Phase 3 — North Star UI depth — **Done**

Detail overlay, NOW cue, loading copy, CSV, top-10 + See more, menu, multi-universe select, INR + theme.

### Phase 4 — Product features — **Done**

| ID | Task | Status |
|----|------|--------|
| P4.1 | Quality scoring + ranking | ✅ |
| P4.2 | Position sizing | ✅ |
| P4.3 | Template narratives + invalidation | ✅ |
| P4.4 | Forming setup detection | ✅ |
| P4.5 | Interactive TradingView-style chart | ✅ |
| P4.6 | Live current price (auto-refresh 15s) | ✅ |
| P4.7 | Scan history + replay | ✅ |
| P4.8 | Alert composer + Telegram delivery | ✅ |
| P4.9 | Product status banner | ✅ |
| P4.10 | ScanRun persistence with full payload | ✅ |
| P4.11 | Backtest realism (compounding, DD, costs) | ✅ |

### Phase 5 — Operational cadence

| ID | Task | Status |
|----|------|--------|
| P5.1 | Scheduled scan job | Ready (script exists) |
| P5.2 | Live watermark refresh | Ready (incremental ingest) |
| P5.3 | Telegram alert delivery | Ready (needs bot token) |

### Phase 6 — Explicitly deferred

Auth, billing, portfolio, broker execution, WebSocket ticks, SHORT setups, LLM narratives, multi-timeframe.

---

## 5. Status snapshot

```text
P0  Demo runbook + commit                 ✅
P1  Live Upstox data                      ✅
P2  Status ledger API+UI                  ✅
P3  Opportunity UX + menu + universes     ✅
P4  Product features (rank/chart/price)   ✅
P5  Ops cadence                           Ready
P6  Deferred                              —
```

| Phase | Status |
|-------|--------|
| P0 | Done |
| P1 | Done |
| P2 | Done |
| P3 | Done |
| P4 | Done |
| P5 | Ready |
| P6 | Deferred |

---

## 6. Definition of done (by phase)

| Phase | Done when |
|-------|-----------|
| P0 | Demo reproducible from checkout + runbook |
| P1 | Scan on Upstox-persisted 1d data; live quotes working |
| P2 | Partial data does not abort or fake `NO_SETUP` |
| P3 | Evidence in overlay; CSV; menu; universe select |
| P4 | Ranked results + chart + live prices + forming + narratives |
| P5 | Scheduled scan + watermark refresh + Telegram alerts |

---

## 7. Open decisions

1. **WebSocket ticks:** Currently polling quotes every 15s; upgrade to Upstox WebSocket for real-time.
2. **LLM narratives:** Template narratives ship now; `NARRATIVE_PROVIDER=llm` deferred.
3. **SHORT setups:** Strategy supports LONG only; SHORT detection deferred.
4. **Universe files:** Curated static JSON nested under Nifty 500; replace when official NSE membership updates.

---

## 8. Quick reference — key entry points

| Concern | Location |
|---------|----------|
| Strategy | `backend/app/domain/strategy/strategy.py` |
| Evaluate | `backend/app/application/strategy/strategy_evaluation_service.py` |
| Fail-fast scan | `backend/app/application/scan/opportunity_scan_service.py` |
| Status ledger | `backend/app/application/scan/universe_scan_report_service.py` |
| Quality scoring | `backend/app/application/scan/quality_score.py` |
| Scan presentation | `backend/app/application/scan/scan_presentation.py` |
| Narratives | `backend/app/application/narrative/template_narrator.py` |
| Alerts | `backend/app/application/alerts/composer.py` + `delivery.py` |
| Product status | `backend/app/application/product/status_service.py` |
| Universe registry | `backend/app/infrastructure/universe/static_file_universe.py` |
| Query (persisted) | `backend/app/application/market_data/query_service.py` |
| Upstox provider | `backend/app/infrastructure/market_data/upstox_provider.py` |
| Demo provider | `backend/app/infrastructure/market_data/demo_provider.py` |
| Data source switch | `backend/app/infrastructure/market_data/source.py` |
| Market data refresh | `backend/scripts/refresh_market_data.py` |
| Scheduled scan | `backend/scripts/run_scheduled_scan.py` |
| Scan API | `backend/app/api/routes/scan.py` |
| Quote API | `backend/app/api/routes/market_data.py` |
| Product API | `backend/app/api/routes/product.py` |
| UI | `frontend/src/main.tsx` |
| Chart component | `frontend/src/components/SetupChart.tsx` |
| Demo runbook | `docs/DEMO_RUNBOOK.md` |

---

## 9. One-line summary

**Now:** Full-featured product — live Upstox data, ranked scan, interactive charts, live prices, forming watchlist, position sizing, narratives, alerts, scan history, backtest.  
**Next:** Operational cadence (scheduled scans, watermark refresh, Telegram alerts).  
**Verify:** Checkpoints A–F in §2c before claiming a release.
