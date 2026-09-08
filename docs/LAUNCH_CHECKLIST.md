# TradePilot launch checklist (EP9)

Sign before marketing a sellable cut.

## Product

- [ ] Home Hub → capital → Guided desk path works without tribal knowledge
- [ ] NSE_ALL + Filter Builder on Swing and Intraday
- [ ] Coverage / skip reasons visible
- [ ] Practice book (swing + intraday) labeled fake money
- [ ] Research FA+TA loads NSE symbols
- [ ] Ask TradePilot guardrail tests green (`test_ai_copilot_guardrails.py`)
- [ ] Account shell: disclaimers + plan stubs (Razorpay live only when wired)

## Data / ops

- [ ] Weekly NSE master script documented / scheduled
- [ ] Weekday 16:15 1d watermark on `NSE_ALL`
- [ ] Market-hours 1m active-set refresh enabled when Upstox live
- [ ] Eligibility JSON refresh runbook owned

## Claims

- [ ] No guaranteed returns in UI copy
- [ ] No AI-invented levels (automated tests)
- [ ] Intraday strategy certification: assistant OK / multi-year edge **NO_GO** unless cert flips
- [ ] Wireframe QA vs `docs/wireframes/`

## Smoke

- [ ] [`SELLABLE_SMOKE.md`](./SELLABLE_SMOKE.md)
- [ ] [`RELEASE_SMOKE.md`](./RELEASE_SMOKE.md) practice path
- [ ] [`INTRADAY_SMOKE.md`](./INTRADAY_SMOKE.md) morning board

**Go / No-go:** ________  **Date:** ________  **Signer:** ________
