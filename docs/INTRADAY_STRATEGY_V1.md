# TradePilot AI — Frozen Intraday Strategy V1 (Refined)

**Strategy ID:** `NSE_STOCKS_ETF_ORB_RVOL_5M_V1`  
**Name:** NSE Stocks & ETFs — 5-Minute Stocks-in-Play ORB + RVOL  
**Status:** Locked for implementation. **Not certified profitable.**  
**Config hash label:** `CONFIG_V1` (any numeric change → new strategy id / version)  
**Branch:** `feature/intraday-trading`

This document supersedes the draft lock with clarifications from the V1 design review. It does **not** add RSI, VWAP, retest, trailing stops, or fixed R-multiples.

---

## 0. Non-goals (unchanged)

- Not a discretionary desk
- LLM never decides trades (explanation only)
- No overnight holdings
- No curve-fitting V1 until the backtest “works” — failures spawn `…_V2`

---

## 1. Universe

**Intent:** Scan eligible NSE cash equities and ETFs (broader than Nifty 500).

**V1 product reality gate:** An instrument is only **eligible to screen** if it has:

- Complete **first 5m bar** for the session
- **14 prior valid sessions** of first-5m volume (see §4)
- Stored **1m** bars covering at least OR + entry window for that session (live/backtest)

Otherwise: `INSUFFICIENT_HISTORY` (not `NO_SETUP`).

Report **coverage %** of the intended universe every session/backtest.

### Hard filters (must all pass) — CONFIG_V1 defaults

| Check | Reject reason | Locked default |
|-------|---------------|----------------|
| Trading status active | `NOT_TRADABLE` | Broker/exchange status ≠ active |
| Liquidity (prior 20 full sessions ADV value) | `INSUFFICIENT_LIQUIDITY` | ADV value ≥ ₹5 crore |
| Spread at arm/submit | `SPREAD_TOO_WIDE` | Spread ≤ max(0.05%, 2 ticks) of mid |
| Price band risk | `PRICE_BAND_RISK` | Not within 1% of upper/lower band at submit |
| ASM / GSM / ESM / T2T / auction | `SURVEILLANCE_BLOCKED` | On restricted list or auction mode |
| Corporate action day | `CORPORATE_ACTION_BLOCK` | Ex-date / split effective date = session |
| ETF liquidity / NAV sanity | `ETF_FILTER` | Same ADV/spread; \|premium/discount\| ≤ 1.0% vs last NAV when available; else skip premium check and keep liquidity gates |
| Short permission (shorts only) | `SHORT_NOT_PERMITTED` | See §11 |

**Re-validate** liquidity/spread/surveillance/band **immediately before order submit**, not only at 09:20 screen.

Every reject gets a deterministic reason (§22).

---

## 2. Opening range

**Session:** NSE continuous equity session (normally 09:15–15:30 IST).

**OR window:** `[09:15:00, 09:20:00)` IST — exactly one 5-minute bar.

Bar convention (locked):

- Timestamp = bar **open** time `09:15:00`
- Includes trades with exchange time `t` where `09:15:00 ≤ t < 09:20:00`
- Pre-open / call auction prints are **excluded**

Capture (immutable after 09:20:00):

```text
OR_OPEN, OR_HIGH, OR_LOW, OR_CLOSE, OR_VOLUME
```

Missing/incomplete OR bar → `DATA_STALE` / `INSUFFICIENT_HISTORY` for that symbol (no trade).

Special sessions (half-day, muhurat, early close):

- If continuous session length &lt; 4 hours → **skip symbol that day** (`SPECIAL_SESSION_SKIP`)
- Forced-exit clock becomes `session_close − 20 minutes` (still no overnight)

---

## 3. Direction (locked)

| Condition | Side |
|-----------|------|
| `OR_CLOSE > OR_OPEN` | Long only |
| `OR_CLOSE < OR_OPEN` | Short only |
| Doji (below) | No trade → `DOJI` |

**Doji (CONFIG_V1):**

```text
abs(OR_CLOSE - OR_OPEN) <= max(1 tick, 0.05% of OR_OPEN)
```

No second interpretation.

---

## 4. Stocks-in-play — RVOL5

```text
RVOL5 = OR_VOLUME / mean(first_5m_volume of previous 14 valid sessions)
```

**Valid session** (locked): full equity continuous session with a complete first 5m bar and no `SPECIAL_SESSION_SKIP`.

If fewer than 14 valid observations → `INSUFFICIENT_HISTORY`.

**CONFIG_V1:**

```text
MIN_RVOL5 = 1.0
TOP_N = 20
```

Eligibility requires **both**:

1. `RVOL5 >= MIN_RVOL5`
2. Rank among symbols passing (1) and hard filters is `≤ TOP_N`

Screening/ranking runs **once** when OR is complete (~09:20). **No re-rank** later that day.

---

## 5. Deterministic ranking (frozen after screen)

Sort key (all descending except last):

1. `RVOL5` desc  
2. Opening-range expansion `%` = `(OR_HIGH - OR_LOW) / OR_OPEN` desc  
3. Average traded value (prior 20 sessions) desc  
4. `instrument_id` asc  

Same-bar capital contention: **higher rank gets capital first** (§9).

---

## 6. Breakout entry (clarified)

**Signal timeframe:** 5m (OR + direction + RVOL).  
**Trigger/execution timeframe:** **1-minute bars** (and live quotes for paper/live).

### Trigger (locked)

After `09:20:00`, on each completed 1m bar with open time `t` where `09:20 ≤ t < entry_cutoff`:

**Long:** `bar.high > OR_HIGH` → trigger  
**Short:** `bar.low < OR_LOW` → trigger  

No entry inside the range. No retest. No discretionary confirm.

### Fill model (backtest / paper)

- **Long fill price** = `max(OR_HIGH + entry_slippage, bar.open)` if gap-through at bar open above OR_HIGH; else `OR_HIGH + entry_slippage` when trade-through occurs inside the bar  
- **Short** mirror with `OR_LOW - entry_slippage`  
- Prefer conservative executable price; never assume perfect touch without slip

### Cancel if risk invalid (locked)

After modeled fill `entry`:

```text
planned_stop_distance = 0.10 * PriorDay_ATR14
effective_risk_per_share = |entry - stop| + entry_slippage + exit_slippage_estimate
```

Cancel (`RISK_INVALID`) if any:

- `effective_risk_per_share > 1.25 * planned_stop_distance`
- Stop fails §7 executability bounds
- Spread check fails at submit

`ORDER_REJECTED` / `RISK_INVALID` **consumes** the one-trade-per-symbol day slot (no retry). Backtests must not silently assume 100% accepts.

---

## 7. Stop loss (refined)

```text
Stop Distance = 0.10 × Prior-Day ATR14
```

ATR14 from **completed prior sessions only** (daily bars). Today’s developing bars never enter ATR.

```text
Long SL  = Entry - Stop Distance
Short SL = Entry + Stop Distance
```

Then snap to tick size **away from the market** (more conservative).

### Executability bounds (CONFIG_V1) — else `RISK_INVALID`

| Bound | Rule |
|-------|------|
| Min stop | `Stop Distance >= max(3 ticks, 0.10% of entry, 1.5 × spread_at_entry)` |
| OR sanity | `Stop Distance >= 0.25 × (OR_HIGH - OR_LOW)` |
| Max stop | `Stop Distance <= 1.50 × (OR_HIGH - OR_LOW)` |

Stop management uses **actual average fill price** and **filled quantity** only.

---

## 8. Position sizing

```text
Effective Risk/Share =
    Stop Distance
  + Expected Entry Slippage
  + Expected Exit Slippage

Quantity = floor(Allowed Risk / Effective Risk/Share)
```

Then apply, in order: available capital, broker limits, lot/tick, max position value, liquidity participation, portfolio exposure, margin.

**No leverage-dependent sizing.**

**CONFIG_V1 defaults:**

| Knob | Default |
|------|---------|
| Risk per trade | 0.5% of equity |
| Max position value | 10% of equity |
| Liquidity participation | ≤ 1% of prior-day total volume (estimate from 1d volume / session minutes × expected hold) — simpler V1: ≤ 2% of **first-5m volume** |

---

## 9. Portfolio risk controls (CONFIG_V1 numerics)

| Control | Default |
|---------|---------|
| Max concurrent positions | 3 |
| Max total open risk | 1.5% of equity |
| Max daily loss (realized) | 2.0% of equity → `DAILY_LOSS_LOCK` |
| Consecutive losing closed trades | 3 → `CONSECUTIVE_LOSS_LOCK` for rest of session |
| Sector concentration | max 2 positions in same GICS/NSE sector map |
| Max position value | 10% equity |
| Same-bar fill priority | rank order (§5) |

Daily loss lock uses **realized** closed-trade P&amp;L only (not MTM).  
On lock: **no new trades**; open positions still managed to stop / forced exit.

---

## 10. Trade frequency

**One trade per instrument per trading date** (strategy_id + date + instrument).

After close / reject / risk-invalid: **no re-entry**.  
No averaging, pyramiding, martingale, revenge trades, or repeated breakout attempts.

---

## 11. Short selling

Before short submit:

```text
short_allowed == true
```

**V1 definition:** instrument is on the **broker intraday/MIS shortable / product-allowed** list used by TradePilot’s execution adapter (point-in-time in backtests). Not “any NSE symbol.”

If false → `SHORT_NOT_PERMITTED` (long side still independently eligible if direction is long).

---

## 12. ETF protection

ETFs use §1 ETF row + same ORB/RVOL engine. Do not treat as identical to cash equity when NAV premium data exists.

---

## 13. Price-band / surveillance

As §1 + **continuous re-check at submit**. Mid-session circuit/ban → cancel arm / block submit with reason; slot consumed if order attempted and rejected.

---

## 14. Trading time (refined)

| Phase | Clock (IST, normal full session) |
|-------|----------------------------------|
| Opening range | 09:15–09:20 |
| Entry window | 09:20–**14:30** |
| Hard entry cutoff | **14:30** (`ENTRY_CUTOFF`) |
| Forced exit | **15:10** |

No new position after 14:30.  
At 15:10: cancel pendings, flatten all, no overnight.

Minimum hold to forced exit is therefore ≥ 40 minutes for any fill — removes 15:04 lottery entries.

---

## 15. Exits — still no profit target

Trade ends only via:

1. Stop loss  
2. Forced exit at 15:10 (or special-session analogue)

No trailing stop, VWAP exit, retest exit, or fixed R target in V1.

**Reporting must include:** MFE, MAE, giveback `(MFE − exit) / MFE` for winners, and buckets by entry time.

---

## 16. Indicators locked out

Unchanged: no RSI/MACD/Stochastic/Supertrend/arbitrary MAs/mandatory VWAP/retest/fixed target/trailing stop/discretionary chart or news LLM decisions.

---

## 17. News

News may drive RVOL; **not** an auto-reject. Optional `EVENT_RISK=true` for audit. LLM explains only.

---

## 18. Execution architecture

| Layer | Data |
|-------|------|
| Signal | 5m OR + RVOL5 + direction |
| Trigger / backtest path | 1m OHLC |
| Live arming | 1m bars + quotes |

Same 1m bar hits stop and favourable extreme and sequence unknown → **worse outcome** (stop).

---

## 19. Slippage & costs (CONFIG_V1)

Model **ticks + bps**, not a flat ₹ fantasy:

```text
entry_slippage = max(1 tick, 2 bps of price)
exit_slippage  = max(1 tick, 2 bps of price)
```

Plus brokerage, STT, exchange, GST, SEBI, stamp (cash intraday schedule).

Stress gates: costs and slippage ×1.25 / ×1.50 / ×2.00.

---

## 20. Failure handling

| Event | Behaviour |
|-------|-----------|
| Stale/missing data | `DATA_STALE` — no new trades; manage opens |
| Order rejected | No phantom position; **slot consumed** |
| Partial fill | Manage filled qty; cancel remainder when appropriate |
| Duplicate | Idempotency: `strategy_id + trading_date + instrument_id + signal_version` |
| Restart | DB ↔ broker reconcile; fail → **trading halted** |

---

## 21. State machine

```text
PRE_MARKET → UNIVERSE_READY → WAITING_FOR_OPENING_RANGE
  → OPENING_RANGE_COMPLETE → SCREENED → RANKED → ARMED
  → BREAKOUT_TRIGGERED → ORDER_SUBMITTED
  → PARTIALLY_FILLED | FILLED | REJECTED | RISK_INVALID
  → POSITION_OPEN → STOP | EOD_EXIT → CLOSED → RECONCILED
```

---

## 22. Per-symbol outcomes (audit)

`TRADED` or one of:

`NO_SETUP`, `DOJI`, `INSUFFICIENT_RVOL`, `INSUFFICIENT_HISTORY`, `INSUFFICIENT_LIQUIDITY`, `SPREAD_TOO_WIDE`, `SURVEILLANCE_BLOCKED`, `PRICE_BAND_RISK`, `CORPORATE_ACTION_BLOCK`, `SHORT_NOT_PERMITTED`, `ETF_FILTER`, `SPECIAL_SESSION_SKIP`, `BREAKOUT_NOT_TRIGGERED`, `ENTRY_CUTOFF`, `RISK_INVALID`, `PORTFOLIO_RISK_LIMIT`, `DAILY_LOSS_LOCK`, `CONSECUTIVE_LOSS_LOCK`, `DATA_STALE`, `ORDER_REJECTED`, …

---

## 23. Backtest acceptance gate

Unchanged in spirit: PIT universe, CA, delistings, realistic fills, walk-forward, OOS, untouched holdout, cost/slippage stress, Monte Carlo sequence.

Mandatory slices: long/short, equity/ETF, year/month, RVOL bucket, **entry time**, sector, regime, worst day/month, streaks, **EOD giveback**.

---

## 24. Automatic rejection of V1

Unchanged: concentration in year/stock/handful of trades; cost fragility; OOS collapse; impossible fills; bypassable risk; bad restart; paper ≪ model.

**Do not mutate V1 to pass.** Ship `…_V2` instead.

---

## CONFIG_V1 quick reference

```text
OR:                 [09:15, 09:20)
DOJI:               max(1 tick, 0.05% OR_OPEN)
MIN_RVOL5:          1.0
TOP_N:              20
RVOL lookback:      14 valid sessions
Trigger:            1m high > OR_HIGH / low < OR_LOW
Entry cutoff:       14:30 IST
Forced exit:        15:10 IST
Stop:               0.10 * prior ATR14
Stop min:           max(3 ticks, 0.10% entry, 1.5*spread)
Stop vs OR:         in [0.25, 1.50] * OR range
Risk invalid:       effective risk > 1.25 * planned stop distance
Risk/trade:         0.5% equity
Max concurrent:     3
Max open risk:      1.5% equity
Daily loss lock:    2.0% realized
Consecutive losses: 3
ADV min:            ₹5 crore
Spread max:         max(0.05%, 2 ticks)
Slippage:           max(1 tick, 2 bps) entry and exit
```

---

## Final lock

Clarifications above are part of **V1**, not discretionary add-ons. Adding VWAP/RSI/retest/trailing/1R targets requires **`NSE_STOCKS_ETF_ORB_RVOL_5M_V2`**.
