/** Plain-English invalidation from engine facts — panel only, not chat. */

export type InvalidationFacts = {
  symbol?: string | null
  reason_code?: string | null
  invalidation?: string | null
  detail?: string | null
  checklist?: string[] | null
}

export type InvalidationView = {
  title: string
  symbol: string
  reasonCode: string | null
  plainEnglish: string
  checklist: string[]
  configNote: string
}

function plainEnglish(reasonCode: string | null, invalidation: string | null, detail: string | null): string {
  const code = (reasonCode || '').toUpperCase()
  if (code.includes('SURVEILLANCE')) {
    return 'This name is on surveillance — TradePilot will not arm a trade.'
  }
  if (code.includes('CORPORATE') || code.includes('CA_')) {
    return 'A corporate-action window blocks this name for the session — TradePilot will not arm a trade.'
  }
  if (code.includes('SHORT') && code.includes('NOT')) {
    return 'Shorts are not permitted for this name — the engine will not arm a short.'
  }
  if (code.includes('PRICE_BAND')) {
    return 'Price is too close to the band — TradePilot will not arm a trade.'
  }
  if (code.includes('RISK_INVALID')) {
    return 'Stop distance is not valid for sizing — TradePilot will not arm a trade.'
  }
  if (invalidation) return invalidation
  if (detail) return detail
  if (reasonCode) return `Engine reason code ${reasonCode} — TradePilot will not override CONFIG_V1.`
  return 'No block or invalidation facts yet. Select a setup or skipped name first.'
}

export function buildInvalidationView(facts: InvalidationFacts): InvalidationView {
  const reasonCode = facts.reason_code ? String(facts.reason_code) : null
  const invalidation = facts.invalidation ? String(facts.invalidation) : null
  const detail = facts.detail ? String(facts.detail) : null
  const checklist =
    facts.checklist && facts.checklist.length
      ? facts.checklist.map(String)
      : invalidation
        ? [invalidation]
        : reasonCode
          ? [`Engine blocked with ${reasonCode}`]
          : ['Select a name with invalidation or a block reason']

  return {
    title: reasonCode ? 'Setup blocked' : 'Invalidation',
    symbol: facts.symbol || '—',
    reasonCode,
    plainEnglish: plainEnglish(reasonCode, invalidation, detail),
    checklist,
    configNote: 'Cannot override CONFIG_V1',
  }
}
