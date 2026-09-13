/** Portfolio capital buckets + absolute ₹ risk limits (TradePilot account profile). */

export const RISK_STORAGE_KEY = 'tradepilot-risk-profile'

/** TradePilot Split Strategy ratios (applied only when the user chooses that strategy). */
export const TRADEPILOT_SWING_PCT = 70
export const TRADEPILOT_INTRADAY_PCT = 20
export const TRADEPILOT_RESERVE_PCT = 10

/** Suggested absolute risk budgets (₹) — independent of total capital. */
export const DEFAULT_SWING_RISK_PER_TRADE_INR = 2500
export const DEFAULT_SWING_MAX_OPEN_RISK_INR = 10_000
export const DEFAULT_INTRADAY_RISK_PER_TRADE_INR = 1000
export const DEFAULT_INTRADAY_MAX_OPEN_RISK_INR = 3000
export const DEFAULT_INTRADAY_DAILY_LOSS_INR = 2500

export const DEFAULT_SWING_EQUITY = '200000'
export const DEFAULT_INTRADAY_EQUITY = '100000'
export const DEFAULT_RESERVE_EQUITY = '0'

export type AllocationMode = 'manual' | 'tradepilot_split'

export type RiskProfile = {
  /** manual = user-entered desk amounts; tradepilot_split = 70/20/10 of total */
  allocationMode: AllocationMode
  totalEquity: string
  swingPct: string
  intradayPct: string
  reservePct: string
  swingEquity: string
  intradayEquity: string
  reserveEquity: string
  /** Swing risk % of swing bucket (derived from absolute when absolute is primary). */
  riskPercent: string
  swingRiskPerTradeInr: string
  swingMaxOpenRiskInr: string
  intradayRiskPerTradeInr: string
  intradayMaxOpenRiskInr: string
  intradayDailyLossInr: string
}

export function bucketAmount(total: number, pct: number): number {
  if (!Number.isFinite(total) || total < 0 || !Number.isFinite(pct)) return 0
  return Math.round((total * pct) / 100)
}

export function deriveBuckets(
  totalRaw: string,
  swingPctRaw: string,
  intradayPctRaw: string,
  reservePctRaw: string,
): { swingEquity: string; intradayEquity: string; reserveEquity: string } {
  const total = Number(totalRaw)
  const swingPct = Number(swingPctRaw)
  const intradayPct = Number(intradayPctRaw)
  const reservePct = Number(reservePctRaw)
  return {
    swingEquity: String(bucketAmount(total, swingPct)),
    intradayEquity: String(bucketAmount(total, intradayPct)),
    reserveEquity: String(bucketAmount(total, reservePct)),
  }
}

/** Swing risk % of swing bucket from absolute ₹ per-trade cap. */
export function riskPercentFromAbsolute(swingEquity: string, riskInr: string): string {
  const equity = Number(swingEquity)
  const risk = Number(riskInr)
  if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(risk) || risk <= 0) return '0.5'
  const pct = (risk / equity) * 100
  return String(Math.round(pct * 1000) / 1000)
}

export function absoluteFromRiskPercent(swingEquity: string, riskPercent: string): string {
  const equity = Number(swingEquity)
  const pct = Number(riskPercent)
  if (!Number.isFinite(equity) || equity <= 0 || !Number.isFinite(pct) || pct <= 0) return '0'
  return String(Math.round((equity * pct) / 100))
}

function normalizePctTrio(
  swingPct: number,
  intradayPct: number,
  reservePct: number,
): { swingPct: string; intradayPct: string; reservePct: string } {
  const sum = swingPct + intradayPct + reservePct
  if (!Number.isFinite(sum) || sum <= 0) {
    return {
      swingPct: String(TRADEPILOT_SWING_PCT),
      intradayPct: String(TRADEPILOT_INTRADAY_PCT),
      reservePct: String(TRADEPILOT_RESERVE_PCT),
    }
  }
  if (Math.abs(sum - 100) < 0.05) {
    return {
      swingPct: String(swingPct),
      intradayPct: String(intradayPct),
      reservePct: String(reservePct),
    }
  }
  return {
    swingPct: String(Math.round((swingPct / sum) * 1000) / 10),
    intradayPct: String(Math.round((intradayPct / sum) * 1000) / 10),
    reservePct: String(Math.round((reservePct / sum) * 1000) / 10),
  }
}

function pctFromAmounts(swing: number, intra: number, reserve: number) {
  const total = Math.max(0, swing + intra + reserve)
  if (total <= 0) {
    return {
      swingPct: '100',
      intradayPct: '0',
      reservePct: '0',
    }
  }
  return normalizePctTrio((swing / total) * 100, (intra / total) * 100, (reserve / total) * 100)
}

/** Default profile — no forced ₹5L; user enters capital, split is opt-in. */
export function defaultManualProfile(): RiskProfile {
  const swingEquity = DEFAULT_SWING_EQUITY
  const intradayEquity = DEFAULT_INTRADAY_EQUITY
  const reserveEquity = DEFAULT_RESERVE_EQUITY
  const swing = Number(swingEquity)
  const intra = Number(intradayEquity)
  const reserve = Number(reserveEquity)
  const total = String(swing + intra + reserve)
  const pct = pctFromAmounts(swing, intra, reserve)
  const swingRisk = String(DEFAULT_SWING_RISK_PER_TRADE_INR)
  return {
    allocationMode: 'manual',
    totalEquity: total,
    ...pct,
    swingEquity,
    intradayEquity,
    reserveEquity,
    swingRiskPerTradeInr: swingRisk,
    swingMaxOpenRiskInr: String(DEFAULT_SWING_MAX_OPEN_RISK_INR),
    intradayRiskPerTradeInr: String(DEFAULT_INTRADAY_RISK_PER_TRADE_INR),
    intradayMaxOpenRiskInr: String(DEFAULT_INTRADAY_MAX_OPEN_RISK_INR),
    intradayDailyLossInr: String(DEFAULT_INTRADAY_DAILY_LOSS_INR),
    riskPercent: riskPercentFromAbsolute(swingEquity, swingRisk),
  }
}

/**
 * Apply TradePilot Split Strategy (70/20/10) to the capital the user entered.
 * Does not change total — only redistributes into buckets.
 */
export function applyTradepilotSplit(profile: RiskProfile): RiskProfile {
  const total = Number(profile.totalEquity)
  const safeTotal = Number.isFinite(total) && total > 0 ? String(total) : profile.totalEquity
  const swingPct = String(TRADEPILOT_SWING_PCT)
  const intradayPct = String(TRADEPILOT_INTRADAY_PCT)
  const reservePct = String(TRADEPILOT_RESERVE_PCT)
  const buckets = deriveBuckets(safeTotal, swingPct, intradayPct, reservePct)
  return {
    ...profile,
    allocationMode: 'tradepilot_split',
    totalEquity: safeTotal,
    swingPct,
    intradayPct,
    reservePct,
    ...buckets,
    riskPercent: riskPercentFromAbsolute(buckets.swingEquity, profile.swingRiskPerTradeInr),
  }
}

/** @deprecated use applyTradepilotSplit — kept for call-site renames */
export function applyStarter5L(): RiskProfile {
  return applyTradepilotSplit({
    ...defaultManualProfile(),
    totalEquity: '500000',
  })
}

export function readStoredRisk(): RiskProfile {
  try {
    const raw = localStorage.getItem(RISK_STORAGE_KEY)
    if (!raw) return defaultManualProfile()
    const parsed = JSON.parse(raw) as Partial<RiskProfile> & { equity?: string }
    const mode: AllocationMode =
      parsed.allocationMode === 'tradepilot_split' ? 'tradepilot_split' : 'manual'

    if (parsed.swingEquity != null || parsed.intradayEquity != null || parsed.totalEquity) {
      const swing = Number(parsed.swingEquity ?? DEFAULT_SWING_EQUITY)
      const intra = Number(parsed.intradayEquity ?? DEFAULT_INTRADAY_EQUITY)
      const reserve = Number(parsed.reserveEquity ?? 0)
      const totalFromParts = Math.max(0, (Number.isFinite(swing) ? swing : 0) + (Number.isFinite(intra) ? intra : 0) + (Number.isFinite(reserve) ? reserve : 0))
      const totalStr =
        parsed.totalEquity != null && Number(parsed.totalEquity) > 0
          ? String(parsed.totalEquity)
          : String(totalFromParts || Number(DEFAULT_SWING_EQUITY) + Number(DEFAULT_INTRADAY_EQUITY))

      if (mode === 'tradepilot_split') {
        const buckets = deriveBuckets(
          totalStr,
          String(TRADEPILOT_SWING_PCT),
          String(TRADEPILOT_INTRADAY_PCT),
          String(TRADEPILOT_RESERVE_PCT),
        )
        const swingRisk =
          parsed.swingRiskPerTradeInr ||
          absoluteFromRiskPercent(buckets.swingEquity, parsed.riskPercent || '0.5')
        return {
          allocationMode: 'tradepilot_split',
          totalEquity: totalStr,
          swingPct: String(TRADEPILOT_SWING_PCT),
          intradayPct: String(TRADEPILOT_INTRADAY_PCT),
          reservePct: String(TRADEPILOT_RESERVE_PCT),
          ...buckets,
          swingRiskPerTradeInr: String(swingRisk),
          swingMaxOpenRiskInr: String(parsed.swingMaxOpenRiskInr || DEFAULT_SWING_MAX_OPEN_RISK_INR),
          intradayRiskPerTradeInr: String(
            parsed.intradayRiskPerTradeInr || DEFAULT_INTRADAY_RISK_PER_TRADE_INR,
          ),
          intradayMaxOpenRiskInr: String(
            parsed.intradayMaxOpenRiskInr || DEFAULT_INTRADAY_MAX_OPEN_RISK_INR,
          ),
          intradayDailyLossInr: String(parsed.intradayDailyLossInr || DEFAULT_INTRADAY_DAILY_LOSS_INR),
          riskPercent: riskPercentFromAbsolute(buckets.swingEquity, String(swingRisk)),
        }
      }

      // Manual: trust desk amounts; derive total + % for display
      const swingEq = String(Number.isFinite(swing) ? swing : Number(DEFAULT_SWING_EQUITY))
      const intraEq = String(Number.isFinite(intra) ? intra : Number(DEFAULT_INTRADAY_EQUITY))
      const reserveEq = String(Number.isFinite(reserve) ? reserve : 0)
      const total = String(Number(swingEq) + Number(intraEq) + Number(reserveEq))
      const pct = pctFromAmounts(Number(swingEq), Number(intraEq), Number(reserveEq))
      const swingRisk =
        parsed.swingRiskPerTradeInr ||
        absoluteFromRiskPercent(swingEq, parsed.riskPercent || '1')
      return {
        allocationMode: 'manual',
        totalEquity: total,
        ...pct,
        swingEquity: swingEq,
        intradayEquity: intraEq,
        reserveEquity: reserveEq,
        swingRiskPerTradeInr: String(swingRisk),
        swingMaxOpenRiskInr: String(parsed.swingMaxOpenRiskInr || DEFAULT_SWING_MAX_OPEN_RISK_INR),
        intradayRiskPerTradeInr: String(
          parsed.intradayRiskPerTradeInr || DEFAULT_INTRADAY_RISK_PER_TRADE_INR,
        ),
        intradayMaxOpenRiskInr: String(
          parsed.intradayMaxOpenRiskInr || DEFAULT_INTRADAY_MAX_OPEN_RISK_INR,
        ),
        intradayDailyLossInr: String(parsed.intradayDailyLossInr || DEFAULT_INTRADAY_DAILY_LOSS_INR),
        riskPercent: riskPercentFromAbsolute(swingEq, String(swingRisk)),
      }
    }

    // Legacy dual-equity only
    const legacy = parsed.equity || DEFAULT_SWING_EQUITY
    const swingEq = String(parsed.swingEquity || legacy)
    const intraEq = String(parsed.intradayEquity || legacy)
    const reserveEq = '0'
    const total = String(Number(swingEq) + Number(intraEq))
    const pct = pctFromAmounts(Number(swingEq), Number(intraEq), 0)
    const riskPercent = parsed.riskPercent || '1'
    const swingRisk = absoluteFromRiskPercent(swingEq, riskPercent)
    return {
      allocationMode: 'manual',
      totalEquity: total,
      ...pct,
      swingEquity: swingEq,
      intradayEquity: intraEq,
      reserveEquity: reserveEq,
      riskPercent: riskPercentFromAbsolute(swingEq, swingRisk),
      swingRiskPerTradeInr: swingRisk,
      swingMaxOpenRiskInr: String(DEFAULT_SWING_MAX_OPEN_RISK_INR),
      intradayRiskPerTradeInr: String(DEFAULT_INTRADAY_RISK_PER_TRADE_INR),
      intradayMaxOpenRiskInr: String(DEFAULT_INTRADAY_MAX_OPEN_RISK_INR),
      intradayDailyLossInr: String(DEFAULT_INTRADAY_DAILY_LOSS_INR),
    }
  } catch {
    return defaultManualProfile()
  }
}

export function serializeRiskProfile(profile: RiskProfile): string {
  return JSON.stringify({
    allocationMode: profile.allocationMode,
    totalEquity: profile.totalEquity,
    swingPct: profile.swingPct,
    intradayPct: profile.intradayPct,
    reservePct: profile.reservePct,
    swingEquity: profile.swingEquity,
    intradayEquity: profile.intradayEquity,
    reserveEquity: profile.reserveEquity,
    riskPercent: profile.riskPercent,
    swingRiskPerTradeInr: profile.swingRiskPerTradeInr,
    swingMaxOpenRiskInr: profile.swingMaxOpenRiskInr,
    intradayRiskPerTradeInr: profile.intradayRiskPerTradeInr,
    intradayMaxOpenRiskInr: profile.intradayMaxOpenRiskInr,
    intradayDailyLossInr: profile.intradayDailyLossInr,
    equity: profile.swingEquity,
  })
}

export function rebuildProfile(partial: {
  allocationMode?: AllocationMode
  totalEquity: string
  swingPct: string
  intradayPct: string
  reservePct: string
  swingEquity?: string
  intradayEquity?: string
  reserveEquity?: string
  swingRiskPerTradeInr: string
  swingMaxOpenRiskInr: string
  intradayRiskPerTradeInr: string
  intradayMaxOpenRiskInr: string
  intradayDailyLossInr: string
}): RiskProfile {
  const mode: AllocationMode =
    partial.allocationMode === 'tradepilot_split' ? 'tradepilot_split' : 'manual'

  if (mode === 'tradepilot_split') {
    const swingPct = String(TRADEPILOT_SWING_PCT)
    const intradayPct = String(TRADEPILOT_INTRADAY_PCT)
    const reservePct = String(TRADEPILOT_RESERVE_PCT)
    const buckets = deriveBuckets(partial.totalEquity, swingPct, intradayPct, reservePct)
    return {
      allocationMode: 'tradepilot_split',
      totalEquity: partial.totalEquity,
      swingPct,
      intradayPct,
      reservePct,
      ...buckets,
      swingRiskPerTradeInr: partial.swingRiskPerTradeInr,
      swingMaxOpenRiskInr: partial.swingMaxOpenRiskInr,
      intradayRiskPerTradeInr: partial.intradayRiskPerTradeInr,
      intradayMaxOpenRiskInr: partial.intradayMaxOpenRiskInr,
      intradayDailyLossInr: partial.intradayDailyLossInr,
      riskPercent: riskPercentFromAbsolute(buckets.swingEquity, partial.swingRiskPerTradeInr),
    }
  }

  const swingEquity = String(partial.swingEquity ?? '0')
  const intradayEquity = String(partial.intradayEquity ?? '0')
  const reserveEquity = String(partial.reserveEquity ?? '0')
  const total = String(Number(swingEquity) + Number(intradayEquity) + Number(reserveEquity))
  const pct = pctFromAmounts(Number(swingEquity), Number(intradayEquity), Number(reserveEquity))
  return {
    allocationMode: 'manual',
    totalEquity: total,
    ...pct,
    swingEquity,
    intradayEquity,
    reserveEquity,
    swingRiskPerTradeInr: partial.swingRiskPerTradeInr,
    swingMaxOpenRiskInr: partial.swingMaxOpenRiskInr,
    intradayRiskPerTradeInr: partial.intradayRiskPerTradeInr,
    intradayMaxOpenRiskInr: partial.intradayMaxOpenRiskInr,
    intradayDailyLossInr: partial.intradayDailyLossInr,
    riskPercent: riskPercentFromAbsolute(swingEquity, partial.swingRiskPerTradeInr),
  }
}

/** Allocated desk capital + closed realized PnL (for sizing after trade closes). */
export function liveDeskCapital(
  allocated: number,
  trades: Array<{ status: string; realized_pnl?: string | number | null; unrealized_pnl?: string | number | null }>,
): number {
  const start = Number.isFinite(allocated) && allocated > 0 ? allocated : 0
  let realized = 0
  for (const trade of trades) {
    const status = String(trade.status || '').toUpperCase()
    if (status === 'CLOSED') {
      const pnl = Number(trade.realized_pnl ?? trade.unrealized_pnl ?? 0)
      if (Number.isFinite(pnl)) realized += pnl
    }
  }
  return Math.max(0, start + realized)
}
