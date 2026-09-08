# Intraday ORB V1 — Certification memo

**Strategy:** `NSE_STOCKS_ETF_ORB_RVOL_5M_V1` / `CONFIG_V1`  
**Status:** **NOT CERTIFIED (NO_GO)** — product + file-backed eligibility complete; multi-year live 1m OOS still required.  
**Branch:** `feature/intraday-trading`  
**Spec gates:** [`INTRADAY_STRATEGY_V1.md`](./INTRADAY_STRATEGY_V1.md) §§23–24

---

## 1. Product use cases (implemented)

| Use case | Status |
|----------|--------|
| Demo / persisted ORB session run | ✅ |
| Beginner + power desk (labels, Top ideas, How decided, CSV) | ✅ |
| OR evidence chart 1m + 5m | ✅ |
| Intraday practice (seed / live LTP tick / 15:10 flatten) | ✅ |
| Practice seed respects CONFIG_V1 portfolio locks | ✅ |
| Practice restart reconcile stub | ✅ `GET .../practice/reconcile` |
| Morning board (stocks vs ETFs, auto-refresh) | ✅ |
| Full NSE cash + ETF master (Upstox dump) | ✅ `build_nse_universe_from_upstox.py` |
| PIT surveillance / short-allow / corporate actions | ✅ file-backed loaders |
| Spread-too-wide gate | ✅ `max_spread_pct` |
| Coverage % + reason mix | ✅ |
| Backtest friction + walk-forward + MFE/MAE + sector slice | ✅ |
| Certification package runner | ✅ `run_intraday_certification.py` |
| Minute watermark / today / range ingest scripts | ✅ |

---

## 2. Certification gates

| Gate | Required | Status |
|------|----------|--------|
| Full NSE cash+ETF universe file | Yes | ✅ ~2.5k EQ + ~100 ETFs from Upstox master |
| Point-in-time CA / surveillance / short lists | Yes | ✅ JSON PIT loaders (replace dumps with official exports) |
| Multi-year Nifty/NSE 1m backfill | Yes | 🔄 Scripts ready; **operator must run Upstox range** |
| Walk-forward on multi-year | Yes | 🔄 CLI + cert package; needs persisted data |
| Cost stress ×1.25–×2 | Yes | ✅ CLI |
| MFE/MAE/giveback/entry/sector buckets | Yes | ✅ |
| Paper ≪ model over live mornings | Yes | 🔄 Endpoint ready; need live day evidence |
| Written go decision | Yes | ⬜ **No-go until multi-year artifact attached** |

---

## 3. Commands

```bash
cd backend

# Refresh NSE cash + ETF master + instrument keys
python scripts/build_nse_universe_from_upstox.py

# Multi-year 1m (example — Nifty 50 first)
python scripts/refresh_intraday_candles.py --mode range --universe NIFTY_50 \
  --start 2022-01-01 --end 2026-09-01

# Certification package (persisted)
python scripts/run_intraday_certification.py --source persisted \
  --start 2024-01-01 --end 2025-12-31 --holdout-frac 0.3 --cost-mult 2
```

Demo package (always NO_GO):

```bash
python scripts/run_intraday_certification.py --source demo \
  --start 2026-09-01 --end 2026-09-07
```

---

## 4. Decision log

| Date | Decision | Notes |
|------|----------|-------|
| 2026-09-08 | **No-go (product ready, not certified)** | Do not retune CONFIG_V1. |
| 2026-09-08 | Eligibility + NSE master wired | File-backed PIT; still need multi-year OOS + live paper evidence for go. |

---

## 5. Rule

**Do not mutate V1 to pass.** Failures → `NSE_STOCKS_ETF_ORB_RVOL_5M_V2`.
