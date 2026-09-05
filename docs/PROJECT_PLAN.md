# TradePilot AI — Project Plan (from now onwards)

**Last updated:** 2026-09-05  
**Status:** Live Upstox data active (`MARKET_DATA_SOURCE=upstox`). Product features include: multi-index scan for LONG breakout and SHORT breakdown setups, ranked opportunities, forming watchlist, interactive charts, live prices, quality scoring, position sizing, **optional practice trading**, beginner-friendly labels, scan history, backtest, auto-refresh scan, SES email alerts (with UI deep links), **async scan jobs**, per-IP rate limits, stock-detail drawer, in-app watermark candle refresh, and **Phase B AI moat** (grounded why/invalidation polish, advisory quality critic, morning/EOD brief, severity-aware data-quality notes, backtest interpreter, similar-setup retrieval). Personal book remains **API-only** (`POST /api/v1/scan/book`) — Find setups UI focuses on Top-N ready ideas + tables (no “Your book” panel). **LLM never invents Entry / SL / Target** — strategy owns prices; `NARRATIVE_PROVIDER=template` keeps offline templates. **Still deferred:** auth, Razorpay billing, Telegram delivery.  
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
| Current price | Live Upstox quote (auto-refreshes every 15s; animated LTP) |
| Quality score | `QualityScore` (rules-based ranking) |
| Position size | Based on account equity + risk % |
| Why eligible | `StrategyEvidence` + template narrative; optional grounded LLM polish (`narrative_source`) |

**Do not turn this into:** a generic screener, chatbot, autonomous trading bot, portfolio app, or broker OMS.

**LLM contract (Phase B):** Strategy owns Entry / SL / Target / R:R. Narratives only rephrase grounded facts (numeric allowlist). Kill-switch: `NARRATIVE_PROVIDER=template` (default) or missing `GOOGLE_API_KEY`.

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
        ↓
Detail drawer tabs → /api/v1/research/{symbol}/… (+ optional Gemini insight)
```

### Completed building blocks

| Area | Done |
|------|------|
| Strategy + last-bar NOW contract (LONG + SHORT) | Yes |
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
| Scan UI + Research desk menu | Yes — Find setups / Stock research / Practice trades |
| Detail overlay, top-ranked cards, See more, CSV | Yes |
| INR rounding + dark/light theme | Yes |
| Demo runbook | Yes |
| Auto-refresh scan (default 5 min; user can change / Off) | Yes |
| Collapsible scan criteria (pause refresh while open) | Yes |
| Instant Qty / risk update when equity or risk % changes | Yes |
| Amazon SES email alerts (HTML + text template) | Yes (verified) |
| Pre-market daily email alert | Yes |
| Confirmation-watch email alert | Yes |
| SES test send script | Yes |
| Groww-style detail tabs (Overview / Setup / Technical / F&O / News) | Yes |
| Research APIs (overview, technical, F&O, news-events, insight) | Yes |
| MACD + technical snapshot from candles | Yes |
| Upstox option-chain F&O tab | Yes |
| NSE announcements / corporate events (fail-soft) | Yes |
| Grounded Gemini Flash insights (`NARRATIVE_PROVIDER=llm`) | Yes |
| Stable detail drawer (no refetch flicker on quote ticks) | Yes |
| Animated live LTP (`LiveValue`) + production UI motion polish | Yes |
| Paper trading agent (all eligible + live LTP MTM/exits) | Yes — **optional**; PENDING until entry; live strip; capital; alerts; timer + ETA |
| Phase B — `GroundedNarrator` facade | Yes |
| Phase B — scan why + invalidation polish (Top-N) | Yes |
| Phase B — advisory quality critic (`quality_critique` / flags) | Yes |
| Phase B — morning / EOD AI brief (email) | Yes |
| Phase B — data-quality copilot | Yes — severity-aware: quiet “Data note” for ≤5 UNAVAILABLE / no ERROR; loud issues box only when real |
| Phase B — backtest interpreter | Yes |
| Phase B — personal book (`POST /api/v1/scan/book`) | Yes — rules solver + LLM explain; **API retained, Find setups UI removed** (redundant with Top-N) |
| Phase B — similar-setup retrieval | Yes — ScanRun fingerprints + candle forward path; drawer dedupes peers (one per symbol) |
| Find setups Top-N + filter/sort toolbar | Yes — rank + strategy confidence on cards/table/CSV |
| Detail drawer tablist polish | Yes — Overview / Setup / Technical / F&O / News labels no longer clipped |

### Phase B checklist

- [x] B1 Shared grounded narrator
- [x] B2 Scan why eligible polish
- [x] B3 Invalidation coach
- [x] B4 Research insight in drawer (single card)
- [x] B5 Quality critic (advisory only — does not replace rules rank)
- [x] B6 Morning / EOD brief
- [x] B7 Data-quality copilot (severity UX so minor gaps do not dominate the desk)
- [x] B8 Backtest interpreter
- [x] B9 Personal book (rules + explain) — API only; UI panel removed after usability review
- [x] B10 Similar-setup retrieval (deduped peers in drawer)
- [x] Docs + smoke + unit tests (`test_phase_b_ai_moat.py`)
- [x] Post–Phase B UX polish — data-note quietness, similar-setups redundancy, drawer tabs, drop Your book UI

### Explicitly not done

- Auth, billing, real broker execution / OMS
- Telegram alert delivery (email SES is live; Telegram tokens remain optional)
- WebSocket live ticks (polling quotes every 15s instead)
- Multi-timeframe beyond `1d`

---

## 2b. Product use cases

| ID | Actor | Use case | Status |
|----|-------|----------|--------|
| UC1 | Trader | Scan a Nifty index for setups **RIGHT NOW** | ✅ Live (LONG + SHORT) |
| UC2 | Trader | See **current trading price** on every symbol | ✅ Live (auto-refreshes 15s; animated tick) |
| UC3 | Trader | Understand **why** a name is eligible | ✅ Detail overlay + narrative |
| UC4 | Trader | View **interactive chart** with S/R + volume | ✅ lightweight-charts |
| UC5 | Trader | See **forming setups** (not yet confirmed) | ✅ Forming watchlist |
| UC6 | Trader | **Rank** setups by quality score | ✅ Top-N cards + score column |
| UC7 | Trader | **Position sizing** per setup | ✅ Quantity + risk amount |
| UC8 | Trader | Browse long result lists | ✅ Top-10 + See more/less |
| UC9 | Trader | Export eligibles | ✅ CSV |
| UC10 | Trader | Trust partial data | ✅ Metric cards + severity-aware data note / issues (UNAVAILABLE ≠ no setup) |
| UC11 | Trader | Switch product areas | ✅ Find setups ↔ Stock research ↔ Practice trades |
| UC12 | Trader | Evaluate / backtest one symbol | ✅ Stock research + live quote |
| UC13 | Trader | Reload past scan results | ✅ Scan history dropdown |
| UC14 | Operator | Reproduce from checkout | ✅ Demo runbook |
| UC15 | Operator | Refresh market data | ✅ `refresh_market_data.py` |
| UC16 | Operator | Audit a scan | ✅ `scan_run_id` + full JSON payload |
| UC17 | Trader | Auto-refresh scan results | ✅ Default 5 min; Off / other rates; pauses when criteria open |
| UC18 | Operator | Email alerts via Amazon SES | ✅ Pre-market summary + confirmation watch; HTML template |
| UC19 | Trader | Research a symbol via **detail tabs** | ✅ Overview / Setup / Technical / F&O / News |
| UC20 | Trader | Read **grounded AI insight** on research tabs | ✅ Gemini Flash (facts-only; template fallback) |
| UC21 | Trader | **Optional practice trades** after scan | ✅ Opt-in; entry watch → fill; live strip; capital; start-trade alert; timer + ETA |
| UC22 | Trader | See **similar historical setups** for a symbol | ✅ Drawer Overview peers + measured forward outcomes |
| UC23 | Trader | Filter / sort ranked eligibles on Find setups | ✅ Column filters + strategy-confidence sort |

**Out of scope:** real broker orders, auth/billing, WebSocket ticks, in-app personal-book portfolio builder (API remains for later).

---

## 2c. UI / product checkpoints (run at http://127.0.0.1:5173)

### Checkpoint A — Scan North Star
1. Top menu switches **Find setups** ↔ **Stock research** ↔ **Practice trades**.
2. Theme toggle: **Dark ↔ Light**, persists after refresh.
3. Universe select: **Nifty 50 / 100 / 200 / 500**; defaults to Nifty 500.
4. Data banner shows source (demo or live Upstox) + last candle date + symbol count.
5. Scan → metrics show symbols scanned / eligible / forming / no setup / unavailable / errors.
6. **Current price** and **% change** columns in both eligible and forming tables.

### Checkpoint B — Ranked results + current price
1. **Top-N cards** show rank, symbol, current price, change %, entry, score, qty.
2. Table has **Rank, Current, Change** columns alongside Entry / SL / Target / R:R / Score / Qty.
3. Prices auto-refresh every 15 seconds with **smooth up/down flash** (no full-table flicker).

### Checkpoint C — Detail overlay + interactive chart
1. Click any symbol → detail drawer opens.
2. Tabs: **Overview | Setup | Technical | F&O | News & Events**.
3. **Setup** tab keeps Trade plan / Evidence / Forming + chart.
4. **Interactive chart** (TradingView-style): candlesticks + volume + levels + B/R/C markers; pan / zoom / crosshair.
5. Header LTP updates live **without** reloading tab data or blanking the panel.
6. NOW badge active when confirmation date matches scan end.

### Checkpoint D — Forming watchlist
1. Forming table shows stage, current price, change, resistance, bars remaining.
2. Click forming symbol → detail drawer with chart + forming evidence.

### Checkpoint E — Export, history & audit
1. Export CSV with rounded numeric columns.
2. Scan history dropdown: reload any past scan.
3. Alert preview in collapsible section.

### Checkpoint F — Research desk
1. Menu → Research desk; live quote shown below form (animated LTP).
2. Evaluate / backtest use same INR formatting.

### Checkpoint G — Ops cadence (P5)
1. After Scan, criteria collapse; toggle expands to edit anytime.
2. Auto-refresh defaults to **5 minutes**; Off / other intervals available.
3. Auto-refresh **pauses** while criteria is open; resumes when collapsed.
4. Changing Risk % / equity updates **Qty** immediately (does not change eligible set).
5. SES configured: `python scripts/send_test_alert_email.py` delivers HTML alert.

### Checkpoint H — Detail research tabs (P7)
1. Click any **stock name** (scan, forming, Practice book/strip, research) → detail drawer opens; closes **only via Close** (not outside click / Escape).
2. Overview: performance windows + 52W stats + chart (no per-tab AI cards in UI).
3. Setup: Trade plan + Evidence when a confirmed setup exists (from scan **or** on-demand `POST /api/v1/strategy/evaluate` when opened outside scan); forming state when applicable.
4. Technical: indicators (incl. ATR) with **Customize** prefs in `localStorage`; pivots.
5. F&O: expiry select + call/put option chain with ATM highlight (or clear unavailable state).
6. News & Events: announcements + events in a two-column card layout (fail-soft).
7. Leave drawer open across a 15s quote tick — panel must **not** flicker or refetch tab data.

### Checkpoint I — Practice trades (P9)
1. Practice mode is **off by default**; enable via checkbox on Find setups / Practice trades.
2. With practice on + capital + risk % (shares &gt; 0), scan reports `paper_opened_count` as **watches created** (`PENDING`).
3. Banner: `PRACTICE TRADES ONLY — fake money, no real broker orders`.
4. Waiting book lists Buy/sell at / Safety exit / Profit goal / Shares / Live price; tick ~15s.
5. Trade becomes **In trade** only when live price reaches entry; then auto-closes at Stop or Target (LONG and SHORT).
6. Cancel watch (before fill) and manual Close (after fill) work; skip symbols already PENDING/OPEN on the next scan.
7. **Start real trade** alert appears when entry is hit (in-app + optional browser notification).
8. Persistent **Live practice** strip under the data banner shows open P/L, remaining capital, and live trades.
9. Capital strip: starting / invested / remaining / account value (remaining updates when trades close).
10. Open trades show **running timer** and **estimated profit-by date** from candle drift + ATR outlook (`GET /api/v1/paper/outlook`).

Operator walkthrough: [RELEASE_SMOKE.md](RELEASE_SMOKE.md).
---

## 3. Guiding principles

1. **Thin slices** — one vertical capability at a time; reuse existing strategy/eval/scan.
2. **Persisted candles for research/scan** — evaluate/scan/backtest consume `MarketDataQueryService`.
3. **Never map data failures to `NO_SETUP`.**
4. **Demo vs live** — `MARKET_DATA_SOURCE` env var; plug-and-play switching.
5. **Label curated universe** — versioned snapshots; nested: 50 ⊂ 100 ⊂ 200 ⊂ 500.
6. **Grounded narratives** — strategy Entry/SL/Target never invented by LLM; research insights facts-only with numeric guardrails.
7. **Stable live UI** — quote ticks soft-update LTP only; do not remount research panels.
8. **Beginner-friendly copy** — prefer plain labels (buy/sell at, safety exit, profit goal) in the UI; keep API field names technical.

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

### Phase 5 — Operational cadence — **Done**

| ID | Task | Status |
|----|------|--------|
| P5.1 | Auto-refresh scan (default 5 min; user changeable / Off) | ✅ |
| P5.2 | Collapsible scan criteria (collapse after scan; pause refresh when open) | ✅ |
| P5.3 | Amazon SES email delivery (HTML + text template) | ✅ Verified |
| P5.4 | Pre-market daily email alert script | ✅ |
| P5.5 | Confirmation-watch alert (forming → confirmed email) | ✅ |
| P5.6 | Live watermark refresh | ✅ In-app IST schedule + CLI |
| P5.7 | Client-side Qty recompute on risk % / equity change | ✅ |

### Phase 6 — Explicitly deferred

Auth, billing, **real** broker execution / OMS, WebSocket ticks, multi-timeframe.

### Phase 7 — Groww-style stock detail tabs — **Done**

| ID | Task | Status |
|----|------|--------|
| P7.1 | Detail tabs: Overview / Setup / Technical / F&O / News & Events | ✅ |
| P7.2 | Preserve existing Trade plan + Evidence + Forming in **Setup** tab | ✅ |
| P7.3 | Technical snapshot (RSI, MACD, ATR, MAs, pivots) from candles | ✅ |
| P7.4 | Upstox option chain F&O tab | ✅ |
| P7.5 | NSE announcements + corporate events | ✅ |
| P7.6 | Grounded Gemini Flash insights API (`GOOGLE_API_KEY`) + template fallback | ✅ (API; not shown as per-tab UI cards) |
| P7.7 | Stable live detail UI (no tab refetch on quote ticks; drawer cache) | ✅ |
| P7.8 | Animated live LTP + theme polish | ✅ |
| P7.9 | Open details from any stock name (incl. Practice); Close-only dismiss | ✅ |
| P7.10 | On-demand evaluate for Setup when opened outside scan | ✅ |
| P7.11 | Clean detail UX: F&O chain + News & Events two-column layout | ✅ |

### Phase 8 — SHORT selling opportunities — **Done**

| ID | Task | Status |
|----|------|--------|
| P8.1 | SHORT breakdown → retest → confirmation (mirror of LONG thresholds) | ✅ |
| P8.2 | Forming detection for SHORT (AWAITING_RETEST / AWAITING_CONFIRMATION) | ✅ |
| P8.3 | Direction-aware quality score, narratives, invalidation | ✅ |
| P8.4 | Backtest SHORT exits / slippage / PnL | ✅ |
| P8.5 | Exhaustive unit tests (mirror suite + rejection paths) | ✅ |
| P8.6 | UI labels / chart levels for Support + Retest high | ✅ |

### Phase 9 — Practice (paper) trading agent — **Done**

| ID | Task | Status |
|----|------|--------|
| P9.1 | Domain MTM / exit rules (LONG+SHORT; both-hit → STOP) | ✅ |
| P9.2 | `paper_trades` table + Alembic `0005` + repository | ✅ |
| P9.3 | Opt-in scan seed → `PENDING` watches for eligible Qty&gt;0 | ✅ |
| P9.4 | Tick: fill when live price hits entry; MTM; Stop/Target exit; cancel/close | ✅ |
| P9.5 | REST `/api/v1/paper/*` + `enable_paper_trading` on scan | ✅ |
| P9.6 | Practice trades UI + 15s tick + PRACTICE banner + beginner labels | ✅ |
| P9.7 | Capital strip (invested / remaining) updates on close | ✅ |
| P9.8 | Start-trade alert + persistent live practice strip | ✅ |
| P9.9 | Live duration timer + candle/ATR profit ETA outlook | ✅ |

---

## 5. Status snapshot

```text
P0  Demo runbook + commit                 ✅
P1  Live Upstox data                      ✅
P2  Status ledger API+UI                  ✅
P3  Opportunity UX + menu + universes     ✅
P4  Product features (rank/chart/price)   ✅
P5  Ops cadence (auto-refresh+email)       ✅
P6  Deferred                              —
P7  Groww detail tabs + Gemini + UX polish ✅
P8  SHORT breakdown setups + tests        ✅
P9  Practice trades (opt-in, entry→exit)   ✅
```

| Phase | Status |
|-------|--------|
| P0 | Done |
| P1 | Done |
| P2 | Done |
| P3 | Done |
| P4 | Done |
| P5 | Done |
| P6 | Deferred |
| P7 | Done |
| P8 | Done |
| P9 | Done |

---

## 6. Definition of done (by phase)

| Phase | Done when |
|-------|-----------|
| P0 | Demo reproducible from checkout + runbook |
| P1 | Scan on Upstox-persisted 1d data; live quotes working |
| P2 | Partial data does not abort or fake `NO_SETUP` |
| P3 | Evidence in overlay; CSV; menu; universe select |
| P4 | Ranked results + chart + live prices + forming + narratives |
| P5 | Auto-refresh (5m default) + SES HTML email alerts (pre-market + confirmation) |
| P7 | Detail tabs + research APIs + Gemini insights; drawer stable under 15s quote poll |
| P8 | SHORT mirror of LONG strategy with forming + backtest + exhaustive unit tests |
| P9 | Opt-in practice: entry watch → fill → Stop/Target; live strip; capital; alerts; timer + ATR/drift ETA |

---

## 7. Open decisions

1. **WebSocket ticks:** Currently polling quotes every 15s; upgrade to Upstox WebSocket for real-time.
2. **LLM narratives:** Research tab insights support `NARRATIVE_PROVIDER=llm` via Gemini Flash (`GEMINI_MODEL`, default `gemini-flash-latest`) with grounding guardrails; setup Entry/SL/Target remain strategy-derived only. Template fallback when LLM off or unavailable.
3. **Universe files:** Curated static JSON nested under Nifty 500; replace when official NSE membership updates.

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
| Alerts | `backend/app/application/alerts/composer.py` + `delivery.py` + `email_delivery.py` |
| Pre-market / confirmation | `backend/scripts/run_premarket_alert.py` |
| SES test email | `backend/scripts/send_test_alert_email.py` |
| Product status | `backend/app/application/product/status_service.py` |
| Universe registry | `backend/app/infrastructure/universe/static_file_universe.py` |
| Query (persisted) | `backend/app/application/market_data/query_service.py` |
| Upstox provider | `backend/app/infrastructure/market_data/upstox_provider.py` |
| Demo provider | `backend/app/infrastructure/market_data/demo_provider.py` |
| Data source switch | `backend/app/infrastructure/market_data/source.py` |
| Market data refresh | `backend/scripts/refresh_market_data.py` (`--mode watermark\|full`) |
| In-app refresh schedule | `backend/app/application/market_data/refresh_scheduler.py` (lifespan) |
| Release smoke (Checkpoint I) | `docs/RELEASE_SMOKE.md` |
| Scheduled scan | `backend/scripts/run_scheduled_scan.py` |
| Scan API | `backend/app/api/routes/scan.py` |
| Quote API | `backend/app/api/routes/market_data.py` |
| Product API | `backend/app/api/routes/product.py` |
| UI | `frontend/src/main.tsx` |
| Chart component | `frontend/src/components/SetupChart.tsx` |
| Watermark ingest | `backend/app/application/market_data/watermark_ingestion_service.py` |
| Insight cache (API) | `backend/app/application/narrative/insight_cache.py` |
| Stock detail tabs | `frontend/src/components/StockDetailDrawer.tsx` |
| Live LTP animation | `frontend/src/components/LiveValue.tsx` |
| Paper domain / exits | `backend/app/domain/paper/` |
| Paper service | `backend/app/application/paper/service.py` |
| Paper outlook (ETA) | `backend/app/application/paper/outlook.py` |
| Paper API | `backend/app/api/routes/paper.py` |
| Beginner UI labels | `frontend/src/terminology.ts` |
| Trade duration timer | `frontend/src/components/TradeDurationTimer.tsx` |
| Research API | `backend/app/api/routes/research.py` |
| Overview / technical services | `backend/app/application/research/` |
| NSE news provider | `backend/app/infrastructure/news/nse_news_provider.py` |
| Gemini insights | `backend/app/application/narrative/gemini_narrator.py` |
| Gemini probe | `backend/scripts/probe_gemini.py` |
| Research tab tests | `backend/tests/unit/test_research_tabs.py` |
| Demo runbook | `docs/DEMO_RUNBOOK.md` |

---

## 9. One-line summary

**Now:** Full-featured product — live Upstox data, ranked LONG + SHORT scan, **async scan jobs** (202 + poll), charts, clean stock-detail drawer, optional practice trading, beginner labels, 5‑min auto-refresh, SES alerts with deep links, in-app IST watermark candle refresh, per-IP rate limits.  
**Next:** Deferred commercial shell (auth, Razorpay, Telegram); run [RELEASE_SMOKE.md](RELEASE_SMOKE.md) including async scan + deep-link checks.  
**Verify:** Checkpoints A–I in §2c plus RELEASE_SMOKE items 11–13 before claiming Phase A (excl. A6) sellable.
