# Intraday ORB — Concrete Implementation Plan

**Strategy:** [`INTRADAY_STRATEGY_V1.md`](./INTRADAY_STRATEGY_V1.md) (`NSE_STOCKS_ETF_ORB_RVOL_5M_V1`)  
**Branch:** `feature/intraday-trading`  
**Principle:** Small deterministic stages. Swing desk (`1d` BreakoutRetest) stays untouched and default.

---

## 0. Current baseline (what we extend)

| Area | Today | Gap for V1 |
|------|-------|------------|
| Candles | Postgres `candles.timeframe`; scan uses **`1d` only** | Need `1m` + `5m` ingest + query |
| Upstox | V3 historical maps `1d/1w/1mo` only | Add `minutes/1`, `minutes/5`; intraday endpoint for today |
| Universe | Nifty 50/100/200/500 JSON | Broader NSE list + eligibility coverage report |
| Strategy | `BreakoutRetestConfirmationStrategy` | New strategy module; do not overload swing |
| Scan API | `_SUPPORTED_TIMEFRAMES = {"1d"}` | Parallel **intraday session** API/job, not silently reuse swing scan |
| Paper | LTP hit entry/stop/target | ORB: no target; 15:10 flatten; 1m path |
| Watermark | Day-granular | Minute watermark / session catch-up |

Upstox constraint to plan around: historical **1m** retrieval max **~1 month per request** (data from ~2022). Backtest ingest must chunk by month.

---

## 1. Delivery stages

### Stage A — Spec & project wiring (docs) ✅

- [x] Refined frozen V1 + CONFIG_V1 numerics  
- [x] This implementation plan  
- [x] Update `PROJECT_PLAN.md` Phase 10 pointer  
- [x] Smoke checklist stub `docs/INTRADAY_SMOKE.md`

**Exit:** Spec is the contract; no strategy code yet.

---

### Stage B — Market data: minute candles

**Goal:** Persist and query `1m` / `5m` like `1d`.

| Task | Detail | Status |
|------|--------|--------|
| B1 | Extend `UpstoxMarketDataProvider.timeframe_map`: `1m` → `minutes/1`, `5m` → `minutes/5` | ✅ |
| B2 | Wire V3 **intraday** candle endpoint for current session catch-up | ✅ `get_intraday_candles` + `--mode today` |
| B3 | Chunked historical backfill script (month windows for 1m) | ✅ `refresh_intraday_candles.py --mode range` |
| B4 | Watermark / session refresh for minute TFs (not `day+1` only) | ✅ minute bar advance + `--mode watermark` |
| B5 | Demo provider: synthesize OR + 1m path for session demos | ✅ |
| B6 | Unit tests: demo 1m OR alignment | ✅ |

**Exit (partial):** Demo + Upstox map + month-chunk backfill + today catch-up + minute watermark ✅.

---

### Stage C — Domain: ORB engine (pure functions) ✅

New package:

```text
backend/app/domain/intraday/
```

| Task | Status |
|------|--------|
| C1–C8 OR, direction, RVOL, rank, trigger, stops, sizing, portfolio, tests | ✅ |

---

### Stage D — Application services

| Task | Status |
|------|--------|
| D1 `IntradaySessionService` demo + persisted + DB save | ✅ |
| D2–D5 universe/eligibility hardening | ✅ NSE_CASH/ETF master + PIT eligibility files |

---

### Stage E — Backtest harness

| Task | Status |
|------|--------|
| E1 multi-day loop + net PnL report (`run_intraday_backtest.py`) | ✅ scaffold |
| E2–E4 stress / walk-forward / concentration flags | ✅ friction, IS/OOS, MFE/MAE, sector slice |

---

### Stage F — API

| Task | Status |
|------|--------|
| F1 `POST /sessions/run`, `GET /sessions/{id}`, `GET /sessions` | ✅ |
| F2–F3 deep links / hardening | 🔄 `?view=intraday` |

---

### Stage G — Paper / sim execution

| Task | Detail | Status |
|------|--------|--------|
| G1 | Dedicated `intraday_practice_trades` (stop-only + 15:10) | ✅ |
| G2 | Seed from session fills; one open/symbol/session | ✅ |
| G3 | Portfolio locks from CONFIG_V1 on live arm | ✅ practice seed uses `can_open` |
| G4 | Restart reconcile stub | ✅ `GET .../practice/reconcile` |

**Exit (partial):** Desk can practice fills with tick + simulate 15:10; live quote-driven morning sim still open.

---

### Stage H — Frontend ✅ MVP

| Task | Status |
|------|--------|
| H1 Nav **Intraday** desk | ✅ |
| H2 Session run → ledger / fills / closes + recent list | ✅ beginner labels, Top ideas, Strategy Steps, CSV, universe presets |
| H3 Charts 1m/5m OR levels | ✅ 1m + 5m evidence chart |
| G1–G2 Practice | ✅ + live LTP tick + divergence |
| J2 Walk-forward + MFE/MAE | ✅ CLI + engine |
| Morning one-click | ✅ `POST /sessions/morning` |
| Morning board | ✅ `GET /morning-board` — NSE morning universe, stocks vs ETFs ranked separately, phase-aware auto-refresh |

---

### Stage I — Universe & surveillance hardening

| Task | Detail | Status |
|------|--------|--------|
| I1 | Expand beyond Nifty toward NSE cash+ETF master | ✅ `NSE_CASH` + expanded `NSE_ETF` via Upstox master |
| I2 | Point-in-time surveillance/CA feeds | ✅ dated JSON loaders (+ sample dumps) |
| I3 | Real short-allow list | ✅ allowlist + denylist files |
| I4 | Coverage % dashboard | ✅ `coverage_pct` + reason_counts on session + desk |

**Exit:** Spec §1 filters are real, not stubs — required before claiming validation.

---

### Stage J — Validation & go/no-go

| Task | Detail | Status |
|------|--------|--------|
| J1 | Multi-year 1m backfill | 🔄 script ready; operator Upstox range |
| J2 | Walk-forward + holdout + stress | ✅ CLI + cert package; needs persisted multi-year |
| J3 | Paper vs backtest divergence | ✅ endpoint + reconcile; live-day evidence open |
| J4 | Written certification memo | 🔄 memo updated — **NO_GO until multi-year artifact** |

**Exit:** Written certification memo (pass/fail). Profitability not assumed.

---

## 2. Sequencing & parallelization

```text
A (docs)
  → B (minute data) ──┬→ C (pure engine) → D (services) → E (backtest)
                      └→ F/G/H after D can run one session
  → I when data/feeds ready
  → J last
```

**Do not** start UI (H) before C+D.  
**Do not** claim NSE-wide scan before B works on NIFTY_50 and I exists.

---

## 3. Explicit non-goals for first merge

- Broker OMS / real orders (still paper/sim)  
- WebSocket ticks (poll 1m + quotes OK for V1 paper)  
- Mutating swing BreakoutRetest rules  
- Re-introducing “Your book” UI  
- Tuning CONFIG_V1 after seeing backtest PnL (that is V2)

---

## 4. Test plan (minimum)

| Layer | Must cover |
|-------|------------|
| Unit | OR bounds, doji, RVOL&lt;14, rank ties, trigger, risk invalid, stop bounds, 14:30 cutoff, forced exit, one-trade/day |
| Integration | Ingest 1m → session run → symbol reasons persisted |
| API | Run + get session on demo |
| UI smoke | Intraday desk loads Top-N armed list |

---

## 5. Suggested first coding milestone (MVP-0)

**MVP-0 = Stages B (demo 1m/5m) + C + D (NIFTY_50 demo session) + minimal F.**

Deliverable:

> “On demo data, after fake 09:20, show ranked Top ≤20 with reasons; on replayed 1m bars, emit fills/cancels with CONFIG_V1 stops and 15:10 flatten.”

Everything else builds on that spine.

---

## 6. Effort sketch (indicative)

| Stage | Relative effort |
|-------|-----------------|
| A | Small |
| B | Medium–Large (Upstox chunking + watermark) |
| C | Medium (high test density) |
| D | Medium |
| E | Medium–Large |
| F | Small–Medium |
| G | Medium |
| H | Medium |
| I | Large (data/ops) |
| J | Large (compute + analysis) |

---

## 7. Open decisions (do not block MVP-0)

1. Store native `5m` from Upstox vs aggregate from `1m` only (prefer **aggregate OR from 1m** for consistency; optional persist `5m`).  
2. Sector map source for concentration.  
3. Whether intraday shares `paper_trades` table or gets `intraday_positions`.

Defaults for MVP-0: aggregate OR from 1m; sector stub (allow all); separate `intraday_*` tables.

---

## 8. Next action

Implement **MVP-0** on `feature/intraday-trading` starting with Stage B demo candles + Stage C `config_v1.py` + opening range/RVOL unit tests.
