/** Plain-language labels for beginners. Keep API field names unchanged. */

export const PAPER_CLAIM =
  'PRACTICE TRADES ONLY — fake money, no real broker orders'

export function directionLabel(direction: string | null | undefined): string {
  return direction === 'SHORT' ? 'Sell short · expect fall' : 'Buy · expect rise'
}

export function exitReasonLabel(reason: string | null | undefined): string {
  switch (reason) {
    case 'STOP_LOSS':
      return 'Hit safety exit (cut loss)'
    case 'TARGET':
      return 'Hit profit goal'
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

