/** Plain-language labels for beginners. Keep API field names unchanged. */

export const PAPER_CLAIM =
  'PRACTICE TRADES ONLY — fake money, no real broker orders'

export function directionLabel(direction: string | null | undefined): string {
  return direction === 'SHORT' ? 'Sell short · expect fall' : 'Buy · expect rise'
}

export function exitReasonLabel(reason: string | null | undefined): string {
  switch (reason) {
    case 'STOP_LOSS':
    case 'STOP':
      return 'Hit safety exit (cut loss)'
    case 'TARGET':
      return 'Hit profit goal'
    case 'EOD_EXIT':
      return 'Forced flatten at 15:10 (same-day exit)'
    case 'MANUAL':
      return 'Closed by you'
    case 'CANCELLED':
      return 'Cancelled before buy/sell price'
    case 'SUPERSEDED':
      return 'Replaced by a newer plan'
    default:
      return reason?.replace(/_/g, ' ') || '—'
  }
}

/** Intraday ORB V1 — plain-language outcome for every symbol reason code. */
export function orbReasonLabel(reason: string | null | undefined): string {
  switch (reason) {
    case 'TRADED':
      return 'Took the trade'
    case 'RANKED_ARMED':
      return 'In Top 20 · waiting for breakout'
    case 'BREAKOUT_NOT_TRIGGERED':
      return 'Armed · breakout never printed'
    case 'NOT_IN_TOP_N':
      return 'Passed screen · outside Top 20'
    case 'DOJI':
      return 'Skipped · opening range too tight (doji)'
    case 'INSUFFICIENT_RVOL':
      return 'Skipped · relative volume too low'
    case 'INSUFFICIENT_HISTORY':
      return 'Skipped · not enough history'
    case 'INSUFFICIENT_LIQUIDITY':
      return 'Skipped · liquidity too thin'
    case 'SPREAD_TOO_WIDE':
      return 'Skipped · spread too wide'
    case 'SURVEILLANCE_BLOCKED':
      return 'Blocked · surveillance / ban list'
    case 'PRICE_BAND_RISK':
      return 'Blocked · near price band'
    case 'CORPORATE_ACTION_BLOCK':
      return 'Blocked · corporate action'
    case 'SHORT_NOT_PERMITTED':
      return 'Blocked · short not allowed'
    case 'ETF_FILTER':
      return 'Skipped · ETF filter'
    case 'SPECIAL_SESSION_SKIP':
      return 'Skipped · special session'
    case 'ENTRY_CUTOFF':
      return 'No new entries after 14:30'
    case 'RISK_INVALID':
      return 'Blocked · stop distance not valid'
    case 'PORTFOLIO_RISK_LIMIT':
      return 'Blocked · portfolio risk / slot limit'
    case 'DAILY_LOSS_LOCK':
      return 'Blocked · daily loss lock'
    case 'CONSECUTIVE_LOSS_LOCK':
      return 'Blocked · consecutive loss lock'
    case 'DATA_STALE':
      return 'Skipped · data stale'
    case 'ORDER_REJECTED':
      return 'Order rejected'
    case 'NO_SETUP':
      return 'No setup'
    default:
      return reason?.replace(/_/g, ' ') || '—'
  }
}

export function orbReasonHint(reason: string | null | undefined): string {
  switch (reason) {
    case 'TRADED':
      return 'Rules sized shares after a 1-minute opening-range breakout.'
    case 'RANKED_ARMED':
      return 'High relative volume and a clear OR direction — watching for a breakout before 14:30.'
    case 'BREAKOUT_NOT_TRIGGERED':
      return 'It ranked in the Top 20, but price never broke the opening range on a 1m close.'
    case 'NOT_IN_TOP_N':
      return 'Only the Top 20 by RVOL5 (with OR expansion) are armed each day.'
    case 'DOJI':
      return 'Opening range high≈low — direction is unclear, so V1 skips the name.'
    case 'INSUFFICIENT_RVOL':
      return 'First 5 minutes were quieter than the lookback average (needs RVOL5 ≥ 1.0).'
    case 'DAILY_LOSS_LOCK':
    case 'CONSECUTIVE_LOSS_LOCK':
    case 'PORTFOLIO_RISK_LIMIT':
      return 'CONFIG_V1 risk locks protect the account — not a bad chart, a portfolio rule.'
    default:
      return ''
  }
}

/** CONFIG_V1 facts shown on the Intraday desk (frozen — do not invent levels). */
export const ORB_V1_RULES = {
  strategyId: 'NSE_STOCKS_ETF_ORB_RVOL_5M_V1',
  configHash: 'CONFIG_V1',
  orWindow: '09:15–09:20 IST',
  entryCutoff: '14:30 IST',
  flatten: '15:10 IST',
  riskPerTradePct: 0.5,
  maxConcurrent: 3,
  topN: 20,
  minRvol5: 1.0,
  stopAtrMult: 0.1,
  noProfitGoal: true,
} as const

export function orbPaperClaim(): string {
  return 'Practice is fake money — not a brokerage order.'
}

export function paperStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'PENDING':
      return 'Waiting for buy/sell price'
    case 'OPEN':
      return 'In trade'
    case 'CLOSED':
      return 'Finished'
    default:
      return status || '—'
  }
}

export function formingStageLabel(stage: string | null | undefined): string {
  switch (stage) {
    case 'AWAITING_RETEST':
      return 'Waiting for price to retest'
    case 'AWAITING_CONFIRMATION':
      return 'Waiting for final confirmation'
    default:
      return (stage || '—').replace(/_/g, ' ').toLowerCase()
  }
}

/** Rules-based setup quality as a beginner-facing confidence percent (not win odds). */
export function strategyConfidenceLabel(qualityScore: string | number | null | undefined): string {
  if (qualityScore == null || qualityScore === '') return '—'
  const numeric = Number(qualityScore)
  if (!Number.isFinite(numeric)) return '—'
  const pct = Math.max(0, Math.min(100, Math.round(numeric)))
  return `${pct}%`
}

export function strategyConfidenceHint(): string {
  return 'Rules-based setup quality (0–100%), not a predicted win rate'
}

/** Practice-account snapshot from open/closed trades + starting capital. */
export function computePaperCapital(
  trades: Array<{
    status: string
    entry_price: string | number
    quantity: number
    unrealized_pnl?: string | number | null
    realized_pnl?: string | number | null
  }>,
  startingCapital: number,
): {
  starting: number
  invested: number
  remaining: number
  realized: number
  unrealized: number
  accountValue: number
} {
  const start = Number.isFinite(startingCapital) && startingCapital > 0 ? startingCapital : 0
  let invested = 0
  let unrealized = 0
  let realized = 0
  for (const trade of trades) {
    if (trade.status === 'OPEN') {
      invested += Number(trade.entry_price) * trade.quantity
      unrealized += Number(trade.unrealized_pnl ?? 0)
    } else if (trade.status === 'CLOSED') {
      realized += Number(trade.realized_pnl ?? 0)
    }
  }
  const remaining = start + realized - invested
  return {
    starting: start,
    invested,
    remaining,
    realized,
    unrealized,
    accountValue: remaining + invested + unrealized,
  }
}

