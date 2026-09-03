# TradePilot AI — Project Plan (from now onwards)

**Last updated:** 2026-09-03  
**Status:** North Star **demo path complete** on Dummy Nifty data. Ship includes multi-index scan (50/100/200/500), status ledger, detail overlay, menu navigation, ScanRun audit, and Upstox-like dark/light UI.  
**Next gated work:** Live Upstox (P1) when `UPSTOX_ACCESS_TOKEN` is set.

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
| Why eligible | `StrategyEvidence` (decision + structure) |

**Do not turn this into:** a generic screener, chatbot, autonomous trading bot, portfolio app, or broker OMS.

**Same rules for scan and backtest:** `BreakoutRetestConfirmationStrategy` with last-bar confirmation = “NOW”.

---

## 2. Where we are (baseline)

### Working end-to-end path (demo)

```text
get_universe(NIFTY_50|100|200|500)  → curated nested snapshots
        ↓
DemoMarketDataProvider → seed CLI → PostgreSQL
        ↓
MarketDataQueryService (persisted candles)
        ↓
StrategyEvaluationService
        ↓
BreakoutRetestConfirmationStrategy
        ↓
UniverseScanReportService (ELIGIBLE / NO_SETUP / UNAVAILABLE / ERROR)
        ↓
POST /api/v1/scan/opportunities (+ ScanRun)
        ↓
Frontend Watchlist scan (menu) → top-10 table → detail overlay
```

### Verified demo scan (persisted Postgres, NIFTY_500)

| Metric | Value |
|--------|------:|
| Symbols scanned | 498 |
| Eligible | 109 |
| No setup | 389 |
| Unavailable / errors | 0 (successful full run) |

### Completed building blocks

| Area | Done |
|------|------|
| Strategy + last-bar NOW contract | Yes |
| StrategyEvaluationService | Yes |
| OpportunityScanService (+ fail-fast `scan_universe`) | Yes |
| UniverseScanReportService (status ledger) | Yes |
| Nifty 50 / 100 / 200 / 500 curated snapshots | Yes (50 ⊂ 100 ⊂ 200 ⊂ 500) |
| Upstox instrument-key mapping (Slice A) | Yes |
| Multi-symbol ingest (Slice B) | Yes |
| DemoMarketDataProvider (Slice C) | Yes |
| Demo Nifty 500 seed (Slice D) | Yes |
| Scan API + `universe` request field | Yes |
| Scan UI + Research desk menu | Yes |
| Detail overlay, top-10 + See more, CSV | Yes |
| INR rounding + dark/light theme | Yes |
| ScanRun persistence (`scan_runs` migration) | Yes |
| Demo runbook | Yes |
| Backtest realism (compounding, DD, gaps, costs) | Yes |

### Explicitly not done

- Live Upstox candles for full Nifty 500 (parked — needs token)
- Ranking / scoring
- LLM explanations
- Scheduled scan job / alerts
- Auth, portfolio, broker execution
- SHORT setups
- Charts / TradingView embeds

---

## 2b. Clear use cases (demo path)

These are the only product use cases we claim as complete without live Upstox.

| ID | Actor | Use case | Success looks like |
|----|-------|----------|--------------------|
| UC1 | Trader | Scan a Nifty index for setups **RIGHT NOW** | Choose Nifty 50/100/200/500 → Scan → correct `symbols_scanned`; eligibles with Entry / SL / Target / R:R |
| UC2 | Trader | Understand **why** a name is eligible | Click a row → **overlay** with trade plan + evidence; NOW badge when confirmation date = scan end |
| UC3 | Trader | Browse long result lists without scroll fatigue | Table shows **top 10**; **See more** / **Show less** |
| UC4 | Trader | Export eligibles | **Export CSV** with rounded prices + confirmation date |
| UC5 | Trader | Trust partial data | Unavailable / Errors cards + issues list; scan does not abort; failures ≠ `NO_SETUP` |
| UC6 | Trader | Switch product areas | Top menu: **Watchlist scan** ↔ **Research desk** |
| UC7 | Trader | Evaluate / backtest one symbol | Research desk; same strategy; ₹ with 2 decimals |
| UC8 | Operator | Reproduce demo cold | [DEMO_RUNBOOK.md](./DEMO_RUNBOOK.md): migrate → seed → uvicorn → vite → scan |
| UC9 | Operator | Refresh demo candles | `python scripts/seed_demo_nifty500.py --to-today` then rescan |
| UC10 | Operator | Audit a scan | UI / API shows `scan_run_id`; row in `scan_runs` |

**Out of scope use cases (do not build yet):** rank/sort by quality, LLM narrative, charts, alerts, portfolio, broker orders, live ticks.

---

## 2c. UI / product checkpoints (run at http://127.0.0.1:5173)

### Checkpoint A — Scan North Star
1. Top menu switches **Watchlist scan** ↔ **Research desk** (one view at a time).
2. Theme toggle switches **Dark ↔ Light** and persists after refresh.
3. Universe select: **Nifty 50 / 100 / 200 / 500**; defaults to Nifty 500.
4. Defaults: start `2025-12-07`, end `2026-09-03`.
5. Scan Nifty 500 → metrics ≈ **498 / 109 / 389 / 0 / 0** on healthy demo DB.
6. Scan Nifty 50 → symbols scanned = **50** (eligible count smaller).
7. Table shows **top 10** eligibles; **See more** reveals the rest.
8. Table prices are **₹ with 2 decimals**; R:R like `2.00x`.

### Checkpoint B — Opportunity detail overlay
1. Click e.g. `ZYDUSLIFE` → detail opens as a **modal overlay**.
2. Trade plan Entry / SL / Target are rounded INR.
3. Evidence bar refs show `#index` plus a readable date below.
4. NOW badge active when confirmation date matches scan end.
5. Close via **Close**, backdrop click, or **Escape**.

### Checkpoint C — Export & audit
1. Export CSV opens a file with rounded numeric columns.
2. Scan run id visible in result metadata.

### Checkpoint D — Research desk
1. Menu → Research desk only (scan panel hidden).
2. Evaluate / backtest use same INR formatting.

### Checkpoint E — Ops (demo)
1. From repo root: `python -m alembic upgrade head`.
2. Seed / `--to-today` succeeds.
3. Optional: remove one symbol’s candles → rescan shows **Unavailable ≥ 1**.

### Checkpoint F — Parked until token
1. Empty `UPSTOX_ACCESS_TOKEN` → do **not** claim live market “RIGHT NOW”.
2. When token arrives: staged ingest 50 → 200 → 498, then re-run Checkpoint A (eligible ≠ 109).

---

## 3. Guiding principles for upcoming work

1. **Thin slices** — one vertical capability at a time; reuse existing strategy/eval/scan.
2. **Persisted candles for research/scan** — evaluate/scan/backtest consume `MarketDataQueryService`.
3. **Never map data failures to `NO_SETUP`.**
4. **Demo vs live** — keep Demo provider explicit; never silently replace Upstox in production wiring.
5. **No premature ranking, LLM, or new frameworks.**
6. **Label curated universe** — versioned snapshots; not a live NSE feed. Nested: 50 ⊂ 100 ⊂ 200 ⊂ 500.

---

## 4. Roadmap

### Phase 0 — Demo milestone — **Done**

| ID | Task | Status |
|----|------|--------|
| P0.1 | Commit demo UI + backend slices | Done (this ship) |
| P0.2 | Demo checklist | Done — §2c |
| P0.3 | Demo runbook | Done — `docs/DEMO_RUNBOOK.md` |

### Phase 1 — Live “RIGHT NOW” data — **Parked (token)**

| ID | Task | Notes |
|----|------|-------|
| P1.1 | Confirm Upstox token + base URL | No silent mock fallback for live claims |
| P1.2 | Full NSE → `instrument_key` for 498 | |
| P1.3 | Bulk ingest `1d` (~9 months) | Staged **50 → 200 → 498** |
| P1.4 | Idempotent / incremental refresh | Watermark later |
| P1.5 | Re-verify scan API + UI on live bars | Eligible count ≠ demo 109 |
| P1.6 | Ops notes | Runtime, failures, rate limits |

### Phase 2 — Scan result robustness — **Done**

`UniverseScanReportService` + API counts + UI metrics/issues. Fail-fast `OpportunityScanService` unchanged.

### Phase 3 — North Star UI depth — **Done**

Detail overlay, NOW cue, loading copy, CSV, top-10 + See more, menu, multi-universe select, INR + theme.

### Phase 4 — Operational cadence

| ID | Task | Status |
|----|------|--------|
| P4.1 | Demo refresh = full-range re-seed (`--to-today`) | Done |
| P4.2 | ScanRun persistence | Done |
| P4.3 | Scheduled scan job | Deferred |
| P4.4 | Live watermark refresh | After P1 |

### Phase 5 — Explicitly deferred

Ranking, LLM, charts, auth, portfolio, broker, websockets, SHORT, new UI frameworks, multi-timeframe Upstox beyond `1d`.

---

## 5. Status snapshot

```text
P0  Demo runbook + commit                 ✓
P3  Opportunity UX + menu + universes     ✓
P2  Status ledger API+UI                  ✓
P4  Demo refresh + ScanRun                ✓ (demo-shaped)
P1  Live Upstox                           parked (token)
P4.4 Live watermark                       after P1
```

| Phase | Status |
|-------|--------|
| P0 | Done |
| P2 | Done |
| P3 | Done |
| P4 (demo) | Done |
| UI polish | Done — menu, overlay, top-10, INR, dark/light, multi-index |
| P1 | Parked until `UPSTOX_ACCESS_TOKEN` |
| P5 | Deferred |

See: [Demo Runbook](./DEMO_RUNBOOK.md).

---

## 6. Definition of done (by phase)

| Phase | Done when |
|-------|-----------|
| P0 | Demo reproducible from checkout + runbook |
| P1 | Scan on Upstox-persisted 1d data; UI still works |
| P2 | Partial data does not abort or fake `NO_SETUP` |
| P3 | Evidence in overlay; CSV; menu; universe select |
| P4 | Demo refresh documented; ScanRun written per scan |

---

## 7. Open decisions

1. **P1 scope:** staged **50 → 200 → 498** (default).  
2. **P2 ownership:** thin **UniverseScanReportService**; leave fail-fast `OpportunityScanService` unchanged.  
3. **“NOW” bar:** confirmation on last candle of the evaluated series.  
4. **Universe files:** curated static JSON nested under Nifty 500; replace when official NSE membership is updated.

---

## 8. Quick reference — key entry points

| Concern | Location |
|---------|----------|
| Strategy | `backend/app/domain/strategy/strategy.py` |
| Evaluate | `backend/app/application/strategy/strategy_evaluation_service.py` |
| Fail-fast scan | `backend/app/application/scan/opportunity_scan_service.py` |
| Status ledger | `backend/app/application/scan/universe_scan_report_service.py` |
| Universe registry | `backend/app/infrastructure/universe/static_file_universe.py` (`get_universe`) |
| Query (persisted) | `backend/app/application/market_data/query_service.py` |
| Demo provider | `backend/app/infrastructure/market_data/demo_provider.py` |
| Demo seed | `backend/scripts/seed_demo_nifty500.py` |
| Scan API | `backend/app/api/routes/scan.py` |
| UI | `frontend/src/main.tsx` |
| Demo runbook | `docs/DEMO_RUNBOOK.md` |

---

## 9. One-line summary

**Now:** Demo-complete North Star — multi-index scan, ledger, overlay detail, menu, ScanRun, trading-desk UI.  
**Next:** Live Upstox (P1) when `UPSTOX_ACCESS_TOKEN` is available.  
**Verify:** Checkpoints A–E in §2c before claiming a release.
