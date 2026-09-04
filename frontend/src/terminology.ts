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
