# TradePilot — Sellable MVP checklist (EP0–EP9)

**Branch:** `feature/intraday-trading` (sellable work continues here; optional rename `feature/sellable-tradepilot` at merge)  
**Spec:** [`TRADEPILOT_PRODUCT_USE_CASES.md`](./TRADEPILOT_PRODUCT_USE_CASES.md)  
**Smoke:** [`SELLABLE_SMOKE.md`](./SELLABLE_SMOKE.md) · [`LAUNCH_CHECKLIST.md`](./LAUNCH_CHECKLIST.md)

## Frozen MVP cut (§8 use cases)

**In MVP**
- NSE_ALL + in-app filters (Swing + Intraday)
- Guided/Pro toggle
- Find setups, Morning board, Session ledger, Research FA+TA
- Unified practice book
- Grounded AI explain + Ask TradePilot (scoped) + briefs UI
- Coverage / skip reasons
- Schedulers for 1d full + 1m active set

**Later (EP8+ harden)**
- Production IdP / Razorpay live keys
- Broker OMS live orders
- Telegram
- Deep FA models
- Multi-strategy marketplace

## Immutable
- Do **not** retune `CONFIG_V1` or BreakoutRetest numerics to force PnL.
- LLM never invents Entry / SL / Target / OR levels.

## EP exit tracking
| EP | Status |
|----|--------|
| EP0 Foundation | ✅ |
| EP1 NSE_ALL + filters | ✅ |
| EP2 Swing sellable | ✅ |
| EP3 Intraday sellable | ✅ |
| EP4 Research | ✅ |
| EP5 AI Copilot | ✅ |
| EP6 Hub + Practice | ✅ |
| EP7 Schedulers | ✅ |
| EP8 Product shell | ✅ (stub auth/billing) |
| EP9 Launch | ✅ docs + guardrail tests |
