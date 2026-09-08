# Intraday smoke (Phase 10)

Prerequisites: branch `feature/intraday-trading`; demo minute fixtures or Upstox `1m` for a small universe.

## MVP-0 checklist (fill as stages land)

1. **Spec** — CONFIG_V1 matches [`INTRADAY_STRATEGY_V1.md`](./INTRADAY_STRATEGY_V1.md). ✅
2. **Minute data** — Demo provider / Upstox map ✅; backfill script ✅; seed demo minutes locally ✅; full Nifty-50 Upstox range still operator-run.
3. **OR** — System builds immutable OR from `[09:15,09:20)`. ✅
4. **Screen** — RVOL5 + TOP_N=20 ranking deterministic; reasons on rejects. ✅
5. **Trigger** — 1m high/low beyond OR; no entry after 14:30. ✅
6. **Risk** — Stop bounds + RISK_INVALID cancel; one trade/symbol/day. ✅
7. **Flatten** — 15:10 exits; no overnight. ✅ (engine)
8. **API/UI** — beginner desk ✅; **OR evidence chart** via `GET .../sessions/{id}/chart/{symbol}` ✅
9. **Persist** — `intraday_sessions` + recent list ✅
10. **Not yet** — walk-forward/OOS certification; live quote-driven morning practice; surveillance hardening.